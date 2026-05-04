"""Pydantic models for TTN webhook event payloads."""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class EndDeviceIds(BaseModel):
    """End device identifiers."""
    device_id: str
    application_ids: dict
    dev_eui: str = Field(alias="dev_eui")
    join_eui: Optional[str] = Field(default=None, alias="join_eui")
    dev_addr: Optional[str] = Field(default=None, alias="dev_addr")


class GatewayIds(BaseModel):
    """Gateway identifiers."""
    gateway_id: str
    eui: Optional[str] = None


class RxMetadata(BaseModel):
    """Metadata from receiving gateway."""
    gateway_ids: GatewayIds
    time: Optional[datetime] = None
    timestamp: Optional[int] = None
    rssi: Optional[float] = None
    channel_rssi: Optional[float] = None
    snr: Optional[float] = None
    uplink_token: Optional[str] = None
    channel_index: Optional[int] = None
    gps_time: Optional[datetime] = None
    received_at: Optional[datetime] = None


class DataRateLoRa(BaseModel):
    """LoRa data rate parameters."""
    bandwidth: int
    spreading_factor: int
    coding_rate: Optional[str] = None


class DataRate(BaseModel):
    """Data rate information."""
    lora: Optional[DataRateLoRa] = None


class Settings(BaseModel):
    """Transmission settings."""
    data_rate: Optional[DataRate] = None
    frequency: Optional[str] = None
    timestamp: Optional[int] = None
    time: Optional[datetime] = None


class UplinkMessagePayload(BaseModel):
    """Uplink message payload."""
    session_key_id: Optional[str] = None
    f_port: Optional[int] = None
    f_cnt: Optional[int] = None
    frm_payload: Optional[str] = None
    decoded_payload: Optional[dict] = None
    rx_metadata: List[RxMetadata] = []
    settings: Optional[Settings] = None
    received_at: Optional[datetime] = None
    consumed_airtime: Optional[str] = None
    version_ids: Optional[dict] = None
    network_ids: Optional[dict] = None


class UplinkMessage(BaseModel):
    """TTN uplink message webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    received_at: Optional[datetime] = None
    uplink_message: UplinkMessagePayload
    simulated: bool = False


class JoinAcceptPayload(BaseModel):
    """Join accept payload."""
    session_key_id: Optional[str] = None
    received_at: Optional[datetime] = None
    rx_metadata: List[RxMetadata] = []


class JoinAccept(BaseModel):
    """TTN join accept webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    received_at: Optional[datetime] = None
    join_accept: JoinAcceptPayload
    simulated: bool = False


class DownlinkPayload(BaseModel):
    """Downlink message payload."""
    f_port: Optional[int] = None
    frm_payload: Optional[str] = None
    decoded_payload: Optional[dict] = None
    confirmed: bool = False
    priority: Optional[str] = None
    correlation_ids: List[str] = []


class DownlinkQueued(BaseModel):
    """TTN downlink queued webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    downlink_queued: DownlinkPayload
    simulated: bool = False


class DownlinkSentPayload(BaseModel):
    """Downlink sent details."""
    session_key_id: Optional[str] = None
    f_port: Optional[int] = None
    f_cnt: Optional[int] = None
    frm_payload: Optional[str] = None
    correlation_ids: List[str] = []
    tx_metadata: Optional[dict] = None


class DownlinkSent(BaseModel):
    """TTN downlink sent webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    downlink_sent: DownlinkSentPayload
    simulated: bool = False


class DownlinkAck(BaseModel):
    """TTN downlink acknowledgment webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    downlink_ack: dict = {}
    simulated: bool = False


class DownlinkNack(BaseModel):
    """TTN downlink negative acknowledgment webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    downlink_nack: dict = {}
    simulated: bool = False


class DownlinkFailed(BaseModel):
    """TTN downlink failed webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    downlink_failed: dict = {}
    simulated: bool = False


class LocationSolved(BaseModel):
    """TTN location solved webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    location_solved: dict = {}
    simulated: bool = False


class ServiceData(BaseModel):
    """TTN service data webhook payload."""
    end_device_ids: EndDeviceIds
    correlation_ids: List[str] = []
    service_data: dict = {}
    simulated: bool = False


class WebhookEvent(BaseModel):
    """Generic webhook event that can hold any event type."""
    event_type: str
    timestamp: datetime
    raw_payload: dict
    dev_eui: str
    gateway_eui: Optional[str] = None
    rssi: Optional[float] = None
    snr: Optional[float] = None

    @classmethod
    def from_uplink(cls, payload: UplinkMessage) -> "WebhookEvent":
        """Create event from uplink message."""
        gateway_eui = None
        rssi = None
        snr = None

        if payload.uplink_message.rx_metadata:
            best_rx = max(
                payload.uplink_message.rx_metadata,
                key=lambda x: x.rssi if x.rssi else -999
            )
            gateway_eui = best_rx.gateway_ids.eui
            rssi = best_rx.rssi or best_rx.channel_rssi
            snr = best_rx.snr

        return cls(
            event_type="UPLINK",
            timestamp=payload.received_at or datetime.utcnow(),
            raw_payload=payload.model_dump(),
            dev_eui=payload.end_device_ids.dev_eui,
            gateway_eui=gateway_eui,
            rssi=rssi,
            snr=snr,
        )

    @classmethod
    def from_join(cls, payload: JoinAccept) -> "WebhookEvent":
        """Create event from join accept."""
        gateway_eui = None
        rssi = None
        snr = None

        if payload.join_accept.rx_metadata:
            best_rx = max(
                payload.join_accept.rx_metadata,
                key=lambda x: x.rssi if x.rssi else -999
            )
            gateway_eui = best_rx.gateway_ids.eui
            rssi = best_rx.rssi or best_rx.channel_rssi
            snr = best_rx.snr

        return cls(
            event_type="JOIN",
            timestamp=payload.received_at or datetime.utcnow(),
            raw_payload=payload.model_dump(),
            dev_eui=payload.end_device_ids.dev_eui,
            gateway_eui=gateway_eui,
            rssi=rssi,
            snr=snr,
        )

    @classmethod
    def from_downlink_sent(cls, payload: DownlinkSent) -> "WebhookEvent":
        """Create event from downlink sent."""
        gateway_eui = None
        if payload.downlink_sent.tx_metadata:
            gateway_ids = payload.downlink_sent.tx_metadata.get("gateway_ids", {})
            gateway_eui = gateway_ids.get("eui")

        return cls(
            event_type="DOWNLINK",
            timestamp=datetime.utcnow(),
            raw_payload=payload.model_dump(),
            dev_eui=payload.end_device_ids.dev_eui,
            gateway_eui=gateway_eui,
        )
