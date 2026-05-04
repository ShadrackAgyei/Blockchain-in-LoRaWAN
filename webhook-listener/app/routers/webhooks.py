"""Webhook endpoints for TTN events."""

import hmac
import hashlib
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Request, Depends
import structlog

from ..config import get_settings, Settings
from ..models.ttn_events import (
    UplinkMessage,
    JoinAccept,
    DownlinkSent,
    WebhookEvent,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/webhook", tags=["webhooks"])


def get_settings_dep() -> Settings:
    """Dependency for getting settings."""
    return get_settings()


def verify_webhook_signature(
    payload: bytes,
    signature: Optional[str],
    secret: str,
) -> bool:
    """Verify TTN webhook signature."""
    if not secret:
        # No secret configured, skip verification
        return True

    if not signature:
        return False

    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


@router.post("/uplink")
async def handle_uplink(
    request: Request,
    x_downlink_apikey: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings_dep),
):
    """
    Handle uplink message webhooks from TTN.

    This is called when a device sends data through a gateway.
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify signature if configured
    signature = request.headers.get("X-TTN-Signature")
    if settings.ttn_webhook_secret and not verify_webhook_signature(
        body, signature, settings.ttn_webhook_secret
    ):
        logger.warning("Invalid webhook signature for uplink")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        # Parse the payload
        payload = UplinkMessage.model_validate_json(body)

        # Convert to generic event
        event = WebhookEvent.from_uplink(payload)

        logger.info(
            "Uplink received",
            dev_eui=event.dev_eui,
            gateway_eui=event.gateway_eui,
            rssi=event.rssi,
            snr=event.snr,
        )

        # Get app state from request
        app = request.app
        db_service = getattr(app.state, "db_service", None)
        aggregator = getattr(app.state, "aggregator", None)
        fabric_client = getattr(app.state, "fabric_client", None)
        org_resolver = getattr(app.state, "org_resolver", None)

        # Store in database
        if db_service:
            db_record = db_service.store_event(
                event_type=event.event_type,
                dev_eui=event.dev_eui,
                gateway_eui=event.gateway_eui,
                rssi=event.rssi,
                snr=event.snr,
                timestamp=event.timestamp,
                raw_payload=event.raw_payload,
            )
            logger.debug("Event stored in database", event_id=db_record.id)

        # Add to aggregator for batching
        if aggregator and event.gateway_eui:
            await aggregator.add_event(event)

        # Check for roaming and record billing charge
        if fabric_client and org_resolver and event.gateway_eui:
            device_org = org_resolver.get_device_org(event.dev_eui)
            gateway_org = org_resolver.get_gateway_org(event.gateway_eui)

            if device_org and gateway_org and device_org != gateway_org:
                # This is roaming traffic - record charge
                tx_id = "PENDING"
                try:
                    tx_id = await fabric_client.record_charge(
                        dev_eui=event.dev_eui,
                        gateway_eui=event.gateway_eui,
                        gateway_owner_org=gateway_org,
                        packet_type="UPLINK",
                        packet_count=1,
                    )
                    logger.info(
                        "Roaming charge recorded on blockchain",
                        dev_eui=event.dev_eui,
                        device_org=device_org,
                        gateway_org=gateway_org,
                        tx_id=tx_id,
                    )
                except Exception as e:
                    logger.warning("Blockchain unavailable, charge stored locally", error=str(e))

                # Always store charge record in database (even if blockchain fails)
                if db_service:
                    db_service.store_charge_record(
                        dev_eui=event.dev_eui,
                        gateway_eui=event.gateway_eui,
                        gateway_owner_org=gateway_org,
                        device_owner_org=device_org,
                        packet_type="UPLINK",
                        packet_count=1,
                        blockchain_tx_id=tx_id,
                        timestamp=event.timestamp,
                    )
                    logger.info(
                        "Roaming charge stored in database",
                        dev_eui=event.dev_eui,
                        device_org=device_org,
                        gateway_org=gateway_org,
                    )

        # Broadcast event to SSE clients
        event_queues = getattr(app.state, "event_queues", [])
        if event_queues:
            event_data = {
                "type": "uplink",
                "devEui": event.dev_eui,
                "gatewayEui": event.gateway_eui,
                "rssi": event.rssi,
                "snr": event.snr,
                "timestamp": event.timestamp.isoformat() if event.timestamp else datetime.utcnow().isoformat(),
            }
            for queue in event_queues:
                try:
                    await queue.put(event_data)
                except Exception:
                    pass

        return {"status": "ok", "event_type": "uplink", "dev_eui": event.dev_eui}

    except Exception as e:
        logger.error("Failed to process uplink", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/join")
async def handle_join(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
):
    """
    Handle join accept webhooks from TTN.

    This is called when a device successfully joins the network.
    """
    body = await request.body()

    signature = request.headers.get("X-TTN-Signature")
    if settings.ttn_webhook_secret and not verify_webhook_signature(
        body, signature, settings.ttn_webhook_secret
    ):
        logger.warning("Invalid webhook signature for join")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = JoinAccept.model_validate_json(body)
        event = WebhookEvent.from_join(payload)

        logger.info(
            "Join received",
            dev_eui=event.dev_eui,
            gateway_eui=event.gateway_eui,
        )

        app = request.app
        db_service = getattr(app.state, "db_service", None)
        aggregator = getattr(app.state, "aggregator", None)
        fabric_client = getattr(app.state, "fabric_client", None)
        org_resolver = getattr(app.state, "org_resolver", None)

        # Store in database
        if db_service:
            db_service.store_event(
                event_type=event.event_type,
                dev_eui=event.dev_eui,
                gateway_eui=event.gateway_eui,
                rssi=event.rssi,
                snr=event.snr,
                timestamp=event.timestamp,
                raw_payload=event.raw_payload,
            )

        # Add to aggregator
        if aggregator and event.gateway_eui:
            await aggregator.add_event(event)

        # Record join charge for roaming
        if fabric_client and org_resolver and event.gateway_eui:
            device_org = org_resolver.get_device_org(event.dev_eui)
            gateway_org = org_resolver.get_gateway_org(event.gateway_eui)

            if device_org and gateway_org and device_org != gateway_org:
                tx_id = "PENDING"
                try:
                    tx_id = await fabric_client.record_charge(
                        dev_eui=event.dev_eui,
                        gateway_eui=event.gateway_eui,
                        gateway_owner_org=gateway_org,
                        packet_type="JOIN",
                        packet_count=1,
                    )
                    logger.info("Join roaming charge recorded on blockchain", tx_id=tx_id)
                except Exception as e:
                    logger.warning("Blockchain unavailable, join charge stored locally", error=str(e))

                # Always store charge record in database
                if db_service:
                    db_service.store_charge_record(
                        dev_eui=event.dev_eui,
                        gateway_eui=event.gateway_eui,
                        gateway_owner_org=gateway_org,
                        device_owner_org=device_org,
                        packet_type="JOIN",
                        packet_count=1,
                        blockchain_tx_id=tx_id,
                        timestamp=event.timestamp,
                    )
                    logger.info("Join roaming charge stored in database")

        # Broadcast event to SSE clients
        event_queues = getattr(app.state, "event_queues", [])
        if event_queues:
            event_data = {
                "type": "join",
                "devEui": event.dev_eui,
                "gatewayEui": event.gateway_eui,
                "rssi": event.rssi,
                "snr": event.snr,
                "timestamp": event.timestamp.isoformat() if event.timestamp else datetime.utcnow().isoformat(),
            }
            for queue in event_queues:
                try:
                    await queue.put(event_data)
                except Exception:
                    pass

        return {"status": "ok", "event_type": "join", "dev_eui": event.dev_eui}

    except Exception as e:
        logger.error("Failed to process join", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/downlink/sent")
async def handle_downlink_sent(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
):
    """
    Handle downlink sent webhooks from TTN.

    This is called when a downlink message is sent to a device.
    """
    body = await request.body()

    signature = request.headers.get("X-TTN-Signature")
    if settings.ttn_webhook_secret and not verify_webhook_signature(
        body, signature, settings.ttn_webhook_secret
    ):
        logger.warning("Invalid webhook signature for downlink")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = DownlinkSent.model_validate_json(body)
        event = WebhookEvent.from_downlink_sent(payload)

        logger.info(
            "Downlink sent",
            dev_eui=event.dev_eui,
            gateway_eui=event.gateway_eui,
        )

        app = request.app
        db_service = getattr(app.state, "db_service", None)
        aggregator = getattr(app.state, "aggregator", None)
        fabric_client = getattr(app.state, "fabric_client", None)
        org_resolver = getattr(app.state, "org_resolver", None)

        # Store in database
        if db_service:
            db_service.store_event(
                event_type=event.event_type,
                dev_eui=event.dev_eui,
                gateway_eui=event.gateway_eui,
                rssi=None,
                snr=None,
                timestamp=event.timestamp,
                raw_payload=event.raw_payload,
            )

        # Add to aggregator
        if aggregator and event.gateway_eui:
            await aggregator.add_event(event)

        # Record downlink charge for roaming
        if fabric_client and org_resolver and event.gateway_eui:
            device_org = org_resolver.get_device_org(event.dev_eui)
            gateway_org = org_resolver.get_gateway_org(event.gateway_eui)

            if device_org and gateway_org and device_org != gateway_org:
                try:
                    tx_id = await fabric_client.record_charge(
                        dev_eui=event.dev_eui,
                        gateway_eui=event.gateway_eui,
                        gateway_owner_org=gateway_org,
                        packet_type="DOWNLINK",
                        packet_count=1,
                    )
                    logger.info("Downlink roaming charge recorded", tx_id=tx_id)

                    if db_service:
                        db_service.store_charge_record(
                            dev_eui=event.dev_eui,
                            gateway_eui=event.gateway_eui,
                            gateway_owner_org=gateway_org,
                            device_owner_org=device_org,
                            packet_type="DOWNLINK",
                            packet_count=1,
                            blockchain_tx_id=tx_id,
                            timestamp=event.timestamp,
                        )
                except Exception as e:
                    logger.error("Failed to record downlink charge", error=str(e))

        # Broadcast event to SSE clients
        event_queues = getattr(app.state, "event_queues", [])
        if event_queues:
            event_data = {
                "type": "downlink",
                "devEui": event.dev_eui,
                "gatewayEui": event.gateway_eui,
                "timestamp": event.timestamp.isoformat() if event.timestamp else datetime.utcnow().isoformat(),
            }
            for queue in event_queues:
                try:
                    await queue.put(event_data)
                except Exception:
                    pass

        return {"status": "ok", "event_type": "downlink_sent", "dev_eui": event.dev_eui}

    except Exception as e:
        logger.error("Failed to process downlink", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
