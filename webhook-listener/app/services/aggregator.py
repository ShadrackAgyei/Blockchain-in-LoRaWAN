"""Event aggregator for batching webhook events before blockchain submission."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
import structlog

from ..config import get_settings
from ..models.ttn_events import WebhookEvent

logger = structlog.get_logger()


@dataclass
class GatewayBuffer:
    """Buffer for events from a single gateway."""
    gateway_eui: str
    events: List[WebhookEvent] = field(default_factory=list)
    period_start: datetime = field(default_factory=datetime.utcnow)
    uplink_count: int = 0
    downlink_count: int = 0
    join_count: int = 0
    error_count: int = 0
    rssi_sum: float = 0.0
    snr_sum: float = 0.0
    signal_count: int = 0

    def add_event(self, event: WebhookEvent):
        """Add an event to the buffer."""
        self.events.append(event)

        if event.event_type == "UPLINK":
            self.uplink_count += 1
        elif event.event_type == "DOWNLINK":
            self.downlink_count += 1
        elif event.event_type == "JOIN":
            self.join_count += 1
        elif event.event_type == "ERROR":
            self.error_count += 1

        if event.rssi is not None:
            self.rssi_sum += event.rssi
            self.signal_count += 1
        if event.snr is not None:
            self.snr_sum += event.snr

    @property
    def total_packets(self) -> int:
        """Total packet count."""
        return self.uplink_count + self.downlink_count + self.join_count

    @property
    def avg_rssi(self) -> Optional[float]:
        """Average RSSI across events."""
        if self.signal_count == 0:
            return None
        return self.rssi_sum / self.signal_count

    @property
    def avg_snr(self) -> Optional[float]:
        """Average SNR across events."""
        if self.signal_count == 0:
            return None
        return self.snr_sum / self.signal_count

    def reset(self):
        """Reset the buffer for a new period."""
        self.events = []
        self.period_start = datetime.utcnow()
        self.uplink_count = 0
        self.downlink_count = 0
        self.join_count = 0
        self.error_count = 0
        self.rssi_sum = 0.0
        self.snr_sum = 0.0
        self.signal_count = 0


@dataclass
class AggregatedBatch:
    """Aggregated batch ready for blockchain submission."""
    gateway_eui: str
    period_start: datetime
    period_end: datetime
    uplink_count: int
    downlink_count: int
    join_count: int
    error_count: int
    avg_rssi: Optional[float]
    avg_snr: Optional[float]
    events: List[WebhookEvent]


# Type for the flush callback
FlushCallback = Callable[[AggregatedBatch], Awaitable[None]]


class EventAggregator:
    """
    Aggregates webhook events per gateway before blockchain submission.

    Events are buffered and flushed when:
    - The aggregation window expires (default: 5 minutes)
    - The buffer reaches max size (default: 100 events)

    This reduces blockchain transactions while maintaining reasonable latency.
    """

    def __init__(
        self,
        window_seconds: Optional[int] = None,
        max_buffer_size: Optional[int] = None,
    ):
        settings = get_settings()
        self.window_seconds = window_seconds or settings.aggregation_window_seconds
        self.max_buffer_size = max_buffer_size or settings.aggregation_max_buffer_size

        self._buffers: Dict[str, GatewayBuffer] = {}
        self._flush_callback: Optional[FlushCallback] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._running = False

        logger.info(
            "EventAggregator initialized",
            window_seconds=self.window_seconds,
            max_buffer_size=self.max_buffer_size,
        )

    def set_flush_callback(self, callback: FlushCallback):
        """Set the callback function to be called when a batch is flushed."""
        self._flush_callback = callback

    async def start(self):
        """Start the periodic flush task."""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info("Aggregator started")

    async def stop(self):
        """Stop the aggregator and flush remaining events."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush all remaining buffers
        await self._flush_all()
        logger.info("Aggregator stopped")

    async def add_event(self, event: WebhookEvent) -> bool:
        """
        Add an event to the aggregator.

        Returns True if the event triggered an immediate flush.
        """
        if not event.gateway_eui:
            logger.warning("Event has no gateway EUI, skipping aggregation", event=event)
            return False

        async with self._lock:
            gateway_eui = event.gateway_eui

            # Get or create buffer for this gateway
            if gateway_eui not in self._buffers:
                self._buffers[gateway_eui] = GatewayBuffer(gateway_eui=gateway_eui)
                logger.debug("Created new buffer", gateway_eui=gateway_eui)

            buffer = self._buffers[gateway_eui]
            buffer.add_event(event)

            logger.debug(
                "Event added to buffer",
                gateway_eui=gateway_eui,
                event_type=event.event_type,
                buffer_size=len(buffer.events),
            )

            # Check if we should flush due to buffer size
            if len(buffer.events) >= self.max_buffer_size:
                logger.info(
                    "Buffer full, triggering flush",
                    gateway_eui=gateway_eui,
                    buffer_size=len(buffer.events),
                )
                await self._flush_gateway(gateway_eui)
                return True

        return False

    async def _periodic_flush(self):
        """Periodically flush buffers that have exceeded the time window."""
        while self._running:
            try:
                await asyncio.sleep(self.window_seconds)
                await self._flush_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in periodic flush", error=str(e))

    async def _flush_expired(self):
        """Flush buffers that have exceeded the time window."""
        async with self._lock:
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=self.window_seconds)

            gateways_to_flush = [
                gw for gw, buffer in self._buffers.items()
                if buffer.period_start <= cutoff and buffer.total_packets > 0
            ]

            for gateway_eui in gateways_to_flush:
                logger.info(
                    "Window expired, flushing",
                    gateway_eui=gateway_eui,
                    packets=self._buffers[gateway_eui].total_packets,
                )
                await self._flush_gateway_locked(gateway_eui)

    async def _flush_gateway(self, gateway_eui: str):
        """Flush a specific gateway's buffer (acquires lock)."""
        async with self._lock:
            await self._flush_gateway_locked(gateway_eui)

    async def _flush_gateway_locked(self, gateway_eui: str):
        """Flush a specific gateway's buffer (caller must hold lock)."""
        if gateway_eui not in self._buffers:
            return

        buffer = self._buffers[gateway_eui]
        if buffer.total_packets == 0:
            return

        # Create the batch
        batch = AggregatedBatch(
            gateway_eui=gateway_eui,
            period_start=buffer.period_start,
            period_end=datetime.utcnow(),
            uplink_count=buffer.uplink_count,
            downlink_count=buffer.downlink_count,
            join_count=buffer.join_count,
            error_count=buffer.error_count,
            avg_rssi=buffer.avg_rssi,
            avg_snr=buffer.avg_snr,
            events=buffer.events.copy(),
        )

        # Reset the buffer
        buffer.reset()

        # Call the flush callback
        if self._flush_callback:
            try:
                await self._flush_callback(batch)
                logger.info(
                    "Batch flushed",
                    gateway_eui=gateway_eui,
                    total_packets=batch.uplink_count + batch.downlink_count + batch.join_count,
                )
            except Exception as e:
                logger.error(
                    "Failed to flush batch",
                    gateway_eui=gateway_eui,
                    error=str(e),
                )
                # Re-add events to buffer for retry
                for event in batch.events:
                    buffer.add_event(event)

    async def _flush_all(self):
        """Flush all buffers."""
        async with self._lock:
            for gateway_eui in list(self._buffers.keys()):
                await self._flush_gateway_locked(gateway_eui)

    def get_buffer_stats(self) -> Dict[str, dict]:
        """Get current buffer statistics for monitoring."""
        stats = {}
        for gateway_eui, buffer in self._buffers.items():
            stats[gateway_eui] = {
                "event_count": len(buffer.events),
                "uplink_count": buffer.uplink_count,
                "downlink_count": buffer.downlink_count,
                "join_count": buffer.join_count,
                "error_count": buffer.error_count,
                "period_start": buffer.period_start.isoformat(),
                "avg_rssi": buffer.avg_rssi,
                "avg_snr": buffer.avg_snr,
            }
        return stats

    async def force_flush(self, gateway_eui: Optional[str] = None):
        """Force flush a specific gateway or all gateways."""
        if gateway_eui:
            await self._flush_gateway(gateway_eui)
        else:
            await self._flush_all()
