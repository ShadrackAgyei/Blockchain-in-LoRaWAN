"""FastAPI webhook listener service for TTN events."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import structlog

from .config import get_settings
from .routers.webhooks import router as webhooks_router
from .routers.dashboard import router as dashboard_router
from .services.aggregator import EventAggregator, AggregatedBatch
from .services.fabric_client import FabricClient
from .services.database import DatabaseService

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Prometheus metrics
WEBHOOK_REQUESTS = Counter(
    "webhook_requests_total",
    "Total webhook requests",
    ["event_type", "status"],
)
WEBHOOK_LATENCY = Histogram(
    "webhook_latency_seconds",
    "Webhook processing latency",
    ["event_type"],
)
BLOCKCHAIN_TRANSACTIONS = Counter(
    "blockchain_transactions_total",
    "Total blockchain transactions",
    ["chaincode", "function", "status"],
)
AGGREGATOR_FLUSHES = Counter(
    "aggregator_flushes_total",
    "Total aggregator batch flushes",
    ["gateway_eui"],
)


class OrgResolver:
    """
    Resolves organization ownership for devices and gateways.

    In production, this would query the blockchain or a local cache.
    For demonstration, it uses a simple in-memory mapping.
    Lookups are case-insensitive and strip 'eui-' prefixes automatically.
    """

    def __init__(self):
        # Device EUI -> Owner Org mapping (stored normalized)
        self._device_orgs: Dict[str, str] = {}
        # Gateway EUI -> Owner Org mapping (stored normalized)
        self._gateway_orgs: Dict[str, str] = {}

    @staticmethod
    def _normalize_eui(eui: str) -> str:
        """Normalize EUI: lowercase, strip eui- prefix."""
        eui = eui.lower().strip()
        if eui.startswith("eui-"):
            eui = eui[4:]
        return eui

    def register_device(self, dev_eui: str, org: str):
        """Register a device's organization."""
        self._device_orgs[self._normalize_eui(dev_eui)] = org

    def register_gateway(self, gateway_eui: str, org: str):
        """Register a gateway's organization."""
        self._gateway_orgs[self._normalize_eui(gateway_eui)] = org

    def get_device_org(self, dev_eui: str) -> Optional[str]:
        """Get the organization that owns a device."""
        return self._device_orgs.get(self._normalize_eui(dev_eui))

    def get_gateway_org(self, gateway_eui: str) -> Optional[str]:
        """Get the organization that owns a gateway."""
        return self._gateway_orgs.get(self._normalize_eui(gateway_eui))

    def load_from_config(self, device_mapping: Dict[str, str], gateway_mapping: Dict[str, str]):
        """Load mappings from configuration."""
        for eui, org in device_mapping.items():
            self._device_orgs[self._normalize_eui(eui)] = org
        for eui, org in gateway_mapping.items():
            self._gateway_orgs[self._normalize_eui(eui)] = org


async def _ensure_billing_policies(fabric_client: FabricClient, org_resolver: 'OrgResolver'):
    """Create default billing policies for devices if they don't already exist."""
    import time

    # Group devices by org
    org_devices: Dict[str, list] = {}
    for dev_eui, org in org_resolver._device_orgs.items():
        org_devices.setdefault(org, []).append(dev_eui)

    for org, devices in org_devices.items():
        policy_id = f"default-{org.lower()}-v2"
        try:
            # Check if policy already exists and is active
            existing = await fabric_client._query_chaincode(
                fabric_client.billing_chaincode,
                "GetPolicy",
                [policy_id],
            )
            if existing:
                import json as _json
                policy_data = _json.loads(existing)
                if policy_data.get("active", False):
                    logger.info("Billing policy already exists and active", policy_id=policy_id, org=org)
                    continue
        except Exception:
            pass

        try:
            # Create default policy: covers all packet types, valid for 1 year
            # Use the org's MSP to invoke so getCallerOrg sets the correct ownerOrg
            msp_id = f"{org}MSP"  # e.g. "Org1" -> "Org1MSP"
            valid_until = int(time.time()) + (365 * 24 * 3600)
            await fabric_client.create_policy(
                policy_id=policy_id,
                devices=devices,
                packet_types=["UPLINK", "DOWNLINK", "JOIN"],
                msp_id=msp_id,
                uplink_micro=100,    # 0.001 cents per uplink
                downlink_micro=200,  # 0.002 cents per downlink
                join_micro=500,      # 0.005 cents per join
                valid_until=valid_until,
            )
            logger.info(
                "Created default billing policy",
                policy_id=policy_id,
                org=org,
                device_count=len(devices),
            )
        except Exception as e:
            # Policy might already exist (race condition) or blockchain error
            logger.warning("Failed to create billing policy", policy_id=policy_id, error=str(e))


async def broadcast_event(app: FastAPI, event_data: dict):
    """Broadcast event to all connected SSE clients."""
    event_queues = getattr(app.state, "event_queues", [])
    for queue in event_queues:
        try:
            await queue.put(event_data)
        except Exception as e:
            logger.warning("Failed to broadcast to client", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    logger.info("Starting webhook listener service")

    # Initialize event broadcasting queues for SSE
    app.state.event_queues = []

    # Initialize database service
    db_service = DatabaseService()
    try:
        db_service.init_db()
        app.state.db_service = db_service
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database initialization failed (will continue without)", error=str(e))
        app.state.db_service = None

    # Initialize Fabric client
    fabric_client = FabricClient()
    try:
        await fabric_client.connect()
        app.state.fabric_client = fabric_client
        logger.info("Fabric client connected")
    except Exception as e:
        logger.warning("Fabric client connection failed (will continue in simulation mode)", error=str(e))
        app.state.fabric_client = fabric_client  # Keep for simulation

    # Initialize org resolver
    org_resolver = OrgResolver()
    # Load organization mappings for devices and gateways
    # NOTE: Update these with your actual device/gateway EUIs from TTN Console
    # Mappings are case-insensitive and eui- prefix is stripped automatically
    org_resolver.load_from_config(
        device_mapping={
            # Demo/Simulation Devices
            "0000000000000001": "Org1",
            "0000000000000002": "Org1",
            "0000000000000003": "Org2",
            "dev-001": "Org1",
            "dev-002": "Org1",
            # Physical Hardware Devices
            "70B3D57ED00759DD": "Org1",   # ESP32 Device 1
            "70B3D57ED0075A44": "Org2",   # ESP32 Device 2 (roaming)
        },
        gateway_mapping={
            # Demo/Simulation Gateways
            "AA555A0000000101": "Org1",
            "AA555A0000000001": "Org1",
            "AA555A0000000002": "Org2",
            # Physical Hardware Gateways
            "2CF7F1C0644001D1": "Org1",   # RAK5146 Gateway
            "2CCF67FFFE6491D1": "Org1",   # RAK5146 Gateway (alternate EUI)
        },
    )
    app.state.org_resolver = org_resolver

    # Ensure billing policies exist for demo devices
    if fabric_client and fabric_client._connected:
        await _ensure_billing_policies(fabric_client, org_resolver)

    # Initialize aggregator with flush callback
    aggregator = EventAggregator()

    async def on_batch_flush(batch: AggregatedBatch):
        """Callback when aggregator flushes a batch."""
        AGGREGATOR_FLUSHES.labels(gateway_eui=batch.gateway_eui).inc()

        try:
            # Record forwarding batch on blockchain
            tx_id = await fabric_client.record_forwarding_batch(
                gateway_eui=batch.gateway_eui,
                period_start=int(batch.period_start.timestamp()),
                period_end=int(batch.period_end.timestamp()),
                uplink_count=batch.uplink_count,
                downlink_count=batch.downlink_count,
                join_count=batch.join_count,
                error_count=batch.error_count,
                avg_rssi=batch.avg_rssi or 0,
                avg_snr=batch.avg_snr or 0,
            )

            BLOCKCHAIN_TRANSACTIONS.labels(
                chaincode="trustmanagement",
                function="RecordForwardingBatch",
                status="success",
            ).inc()

            logger.info(
                "Forwarding batch recorded",
                gateway_eui=batch.gateway_eui,
                tx_id=tx_id,
                total_packets=batch.uplink_count + batch.downlink_count + batch.join_count,
            )

            # Store batch in database
            if db_service:
                db_service.store_forwarding_batch(
                    gateway_eui=batch.gateway_eui,
                    period_start=batch.period_start,
                    period_end=batch.period_end,
                    uplink_count=batch.uplink_count,
                    downlink_count=batch.downlink_count,
                    join_count=batch.join_count,
                    error_count=batch.error_count,
                    avg_rssi=batch.avg_rssi,
                    avg_snr=batch.avg_snr,
                    blockchain_tx_id=tx_id,
                )

            # Broadcast batch event to SSE clients
            await broadcast_event(app, {
                "type": "batch_flush",
                "gatewayEui": batch.gateway_eui,
                "periodStart": batch.period_start.isoformat(),
                "periodEnd": batch.period_end.isoformat(),
                "uplinkCount": batch.uplink_count,
                "downlinkCount": batch.downlink_count,
                "joinCount": batch.join_count,
                "txId": tx_id,
                "timestamp": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            BLOCKCHAIN_TRANSACTIONS.labels(
                chaincode="trustmanagement",
                function="RecordForwardingBatch",
                status="error",
            ).inc()
            logger.error("Failed to record forwarding batch", error=str(e))
            raise

    aggregator.set_flush_callback(on_batch_flush)
    await aggregator.start()
    app.state.aggregator = aggregator

    logger.info("Webhook listener service started")

    yield

    # Shutdown
    logger.info("Shutting down webhook listener service")
    await aggregator.stop()
    await fabric_client.disconnect()
    logger.info("Webhook listener service stopped")


# Create FastAPI app
app = FastAPI(
    title="LoRaWAN Blockchain Webhook Listener",
    description="Webhook listener for TTN events with Hyperledger Fabric integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhooks_router)
app.include_router(dashboard_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "LoRaWAN Blockchain Webhook Listener",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/stats")
async def stats():
    """Get service statistics."""
    aggregator: Optional[EventAggregator] = getattr(app.state, "aggregator", None)
    fabric_client: Optional[FabricClient] = getattr(app.state, "fabric_client", None)

    stats = {
        "timestamp": datetime.utcnow().isoformat(),
        "aggregator": {},
        "fabric": {},
    }

    if aggregator:
        stats["aggregator"] = aggregator.get_buffer_stats()

    if fabric_client:
        stats["fabric"] = fabric_client.get_latency_stats()

    return stats


@app.post("/admin/flush")
async def admin_flush(gateway_eui: Optional[str] = None):
    """Force flush aggregator buffers (admin endpoint)."""
    aggregator: Optional[EventAggregator] = getattr(app.state, "aggregator", None)
    if aggregator:
        await aggregator.force_flush(gateway_eui)
        return {"status": "flushed", "gateway_eui": gateway_eui or "all"}
    return {"status": "aggregator not available"}


@app.post("/admin/register/device")
async def admin_register_device(dev_eui: str, org: str):
    """Register a device's organization (admin endpoint)."""
    org_resolver: Optional[OrgResolver] = getattr(app.state, "org_resolver", None)
    if org_resolver:
        org_resolver.register_device(dev_eui, org)
        return {"status": "registered", "dev_eui": dev_eui, "org": org}
    return {"status": "org resolver not available"}


@app.post("/admin/register/gateway")
async def admin_register_gateway(gateway_eui: str, org: str):
    """Register a gateway's organization (admin endpoint)."""
    org_resolver: Optional[OrgResolver] = getattr(app.state, "org_resolver", None)
    if org_resolver:
        org_resolver.register_gateway(gateway_eui, org)
        return {"status": "registered", "gateway_eui": gateway_eui, "org": org}
    return {"status": "org resolver not available"}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    if settings.debug:
        uvicorn.run(
            "app.main:app",
            host=settings.host,
            port=settings.port,
            reload=True,
        )
    else:
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
        )
