"""Dashboard API endpoints for the frontend."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api", tags=["dashboard"])


# Response models
class Location(BaseModel):
    latitude: float
    longitude: float
    altitude: float = 0.0


class GatewayResponse(BaseModel):
    gatewayEUI: str
    ownerOrg: str
    location: Location
    trustScore: float
    status: str
    registeredAt: Optional[str] = None
    lastActive: Optional[str] = None


class GatewayHistoryEntry(BaseModel):
    periodStart: str
    periodEnd: str
    uplinkCount: int
    downlinkCount: int
    joinCount: int
    errorCount: int
    avgRssi: Optional[float]
    avgSnr: Optional[float]


class EventResponse(BaseModel):
    id: int
    eventType: str
    devEui: str
    gatewayEui: Optional[str]
    rssi: Optional[float]
    snr: Optional[float]
    timestamp: str
    processed: bool


class ChargeResponse(BaseModel):
    debtorOrg: str
    creditorOrg: str
    totalPackets: int
    uplinkCount: int
    downlinkCount: int
    joinCount: int
    totalAmountMicro: int


class BillingSummary(BaseModel):
    totalCharges: int
    pendingSettlements: int
    orgPairs: List[ChargeResponse]


class StatsOverview(BaseModel):
    totalGateways: int
    activeGateways: int
    totalDevices: int
    eventsToday: int
    pendingCharges: int
    lastUpdated: str


# Helper to serialize datetime
def serialize_datetime(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


@router.get("/gateways", response_model=List[GatewayResponse])
async def list_gateways(request: Request, min_trust: float = Query(0.0, ge=0.0, le=1.0)):
    """List all gateways with trust scores from blockchain, with DB fallback."""
    fabric_client = getattr(request.app.state, "fabric_client", None)
    db_service = getattr(request.app.state, "db_service", None)
    org_resolver = getattr(request.app.state, "org_resolver", None)

    # Try blockchain first
    if fabric_client:
        try:
            gateways = await fabric_client.get_trusted_gateways(min_trust)
            if gateways:
                return [
                    GatewayResponse(
                        gatewayEUI=gw.get("gatewayEUI", ""),
                        ownerOrg=gw.get("ownerOrg", ""),
                        location=Location(
                            latitude=gw.get("location", {}).get("latitude", 0.0),
                            longitude=gw.get("location", {}).get("longitude", 0.0),
                            altitude=gw.get("location", {}).get("altitude", 0.0),
                        ),
                        trustScore=gw.get("trustScore", 0.0),
                        status=gw.get("status", "UNKNOWN"),
                        registeredAt=gw.get("registeredAt"),
                        lastActive=gw.get("lastActive"),
                    )
                    for gw in gateways
                ]
        except Exception as e:
            logger.warning("Failed to fetch gateways from blockchain", error=str(e))

    # DB fallback: derive gateways from webhook events
    if db_service:
        try:
            session = db_service.get_session()
            try:
                from ..services.database import EventRecord
                from sqlalchemy import func

                results = (
                    session.query(
                        EventRecord.gateway_eui,
                        func.count(EventRecord.id).label("event_count"),
                        func.avg(EventRecord.rssi).label("avg_rssi"),
                        func.avg(EventRecord.snr).label("avg_snr"),
                        func.max(EventRecord.timestamp).label("last_seen"),
                        func.min(EventRecord.timestamp).label("first_seen"),
                    )
                    .filter(EventRecord.gateway_eui.isnot(None))
                    .group_by(EventRecord.gateway_eui)
                    .all()
                )

                # Convert rows to plain dicts for easier handling
                from ..main import OrgResolver
                rows = []
                for row in results:
                    rows.append({
                        "eui": row.gateway_eui,
                        "event_count": int(row.event_count or 0),
                        "avg_rssi": float(row.avg_rssi) if row.avg_rssi is not None else -100.0,
                        "avg_snr": float(row.avg_snr) if row.avg_snr is not None else 0.0,
                        "last_seen": row.last_seen,
                        "first_seen": row.first_seen,
                    })

                # Deduplicate by normalized EUI
                seen = {}
                for r in rows:
                    norm_eui = OrgResolver._normalize_eui(r["eui"])
                    if norm_eui not in seen or (r["last_seen"] and (not seen[norm_eui]["last_seen"] or r["last_seen"] > seen[norm_eui]["last_seen"])):
                        seen[norm_eui] = r

                gateways = []
                for norm_eui, r in seen.items():
                    owner_org = (org_resolver.get_gateway_org(r["eui"]) if org_resolver else None) or "Unknown"
                    avg_rssi = r["avg_rssi"]
                    avg_snr = r["avg_snr"]
                    trust_estimate = min(1.0, max(0.0, (avg_rssi + 120) / 40 * 0.4 + min(avg_snr / 10, 1.0) * 0.6))

                    if trust_estimate >= min_trust:
                        gateways.append(GatewayResponse(
                            gatewayEUI=r["eui"],
                            ownerOrg=owner_org,
                            location=Location(latitude=5.759, longitude=-0.220, altitude=100.0),
                            trustScore=round(trust_estimate, 2),
                            status="ACTIVE",
                            registeredAt=serialize_datetime(r["first_seen"]),
                            lastActive=serialize_datetime(r["last_seen"]),
                        ))
                return gateways
            finally:
                session.close()
        except Exception as e:
            logger.warning("Failed to fetch gateways from database", error=str(e))

    return []


@router.get("/gateways/{eui}", response_model=GatewayResponse)
async def get_gateway(request: Request, eui: str):
    """Get single gateway details."""
    fabric_client = getattr(request.app.state, "fabric_client", None)

    if not fabric_client:
        # Return mock data
        return GatewayResponse(
            gatewayEUI=eui,
            ownerOrg="Org1",
            location=Location(latitude=5.7590, longitude=-0.2200, altitude=100.0),
            trustScore=0.85,
            status="ACTIVE",
            registeredAt=datetime.utcnow().isoformat(),
            lastActive=datetime.utcnow().isoformat(),
        )

    try:
        gw = await fabric_client.get_gateway(eui)
        if not gw:
            raise HTTPException(status_code=404, detail="Gateway not found")

        return GatewayResponse(
            gatewayEUI=gw.get("gatewayEUI", eui),
            ownerOrg=gw.get("ownerOrg", ""),
            location=Location(
                latitude=gw.get("location", {}).get("latitude", 0.0),
                longitude=gw.get("location", {}).get("longitude", 0.0),
                altitude=gw.get("location", {}).get("altitude", 0.0),
            ),
            trustScore=gw.get("trustScore", 0.0),
            status=gw.get("status", "UNKNOWN"),
            registeredAt=gw.get("registeredAt"),
            lastActive=gw.get("lastActive"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch gateway", eui=eui, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch gateway from blockchain")


@router.get("/gateways/{eui}/history", response_model=List[GatewayHistoryEntry])
async def get_gateway_history(
    request: Request,
    eui: str,
    days: int = Query(7, ge=1, le=30),
):
    """Get forwarding history for a gateway."""
    db_service = getattr(request.app.state, "db_service", None)

    if not db_service:
        # Return mock data
        history = []
        now = datetime.utcnow()
        for i in range(days):
            start = now - timedelta(days=i+1)
            end = now - timedelta(days=i)
            history.append(GatewayHistoryEntry(
                periodStart=start.isoformat(),
                periodEnd=end.isoformat(),
                uplinkCount=50 + i * 10,
                downlinkCount=10 + i * 2,
                joinCount=5,
                errorCount=i,
                avgRssi=-85.0 + i,
                avgSnr=8.5 - i * 0.5,
            ))
        return history

    try:
        session = db_service.get_session()
        try:
            from ..services.database import ForwardingBatchRecord
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)

            records = (
                session.query(ForwardingBatchRecord)
                .filter(
                    ForwardingBatchRecord.gateway_eui == eui,
                    ForwardingBatchRecord.period_start >= start_time,
                )
                .order_by(ForwardingBatchRecord.period_start.desc())
                .all()
            )

            return [
                GatewayHistoryEntry(
                    periodStart=serialize_datetime(r.period_start),
                    periodEnd=serialize_datetime(r.period_end),
                    uplinkCount=r.uplink_count or 0,
                    downlinkCount=r.downlink_count or 0,
                    joinCount=r.join_count or 0,
                    errorCount=r.error_count or 0,
                    avgRssi=r.avg_rssi,
                    avgSnr=r.avg_snr,
                )
                for r in records
            ]
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to fetch gateway history", eui=eui, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch gateway history")


@router.get("/events/recent", response_model=List[EventResponse])
async def get_recent_events(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    event_type: Optional[str] = Query(None),
    gateway_eui: Optional[str] = Query(None),
    dev_eui: Optional[str] = Query(None),
):
    """Get recent events from database."""
    db_service = getattr(request.app.state, "db_service", None)

    if not db_service:
        # Return mock data
        events = []
        now = datetime.utcnow()
        for i in range(min(limit, 10)):
            events.append(EventResponse(
                id=i + 1,
                eventType=["uplink", "join", "downlink"][i % 3],
                devEui=f"000000000000000{i}",
                gatewayEui="AA555A0000000001",
                rssi=-85.0 - i,
                snr=8.5 - i * 0.5,
                timestamp=(now - timedelta(minutes=i * 5)).isoformat(),
                processed=True,
            ))
        return events

    try:
        session = db_service.get_session()
        try:
            from ..services.database import EventRecord

            query = session.query(EventRecord)

            if event_type:
                query = query.filter(EventRecord.event_type == event_type)
            if gateway_eui:
                query = query.filter(EventRecord.gateway_eui == gateway_eui)
            if dev_eui:
                query = query.filter(EventRecord.dev_eui == dev_eui)

            records = (
                query
                .order_by(EventRecord.timestamp.desc())
                .limit(limit)
                .all()
            )

            return [
                EventResponse(
                    id=r.id,
                    eventType=r.event_type,
                    devEui=r.dev_eui,
                    gatewayEui=r.gateway_eui,
                    rssi=r.rssi,
                    snr=r.snr,
                    timestamp=serialize_datetime(r.timestamp),
                    processed=r.processed,
                )
                for r in records
            ]
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to fetch recent events", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch events")


@router.get("/events/stream")
async def event_stream(request: Request):
    """SSE stream for real-time events."""

    async def generate():
        queue = asyncio.Queue()
        event_queues = getattr(request.app.state, "event_queues", None)

        if event_queues is None:
            # Initialize if not exists
            request.app.state.event_queues = []
            event_queues = request.app.state.event_queues

        event_queues.append(queue)
        logger.info("SSE client connected", total_clients=len(event_queues))

        try:
            # Send initial keepalive
            yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.utcnow().isoformat()})}\n\n"

            while True:
                try:
                    # Wait for event with timeout for keepalive
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in event_queues:
                event_queues.remove(queue)
            logger.info("SSE client disconnected", total_clients=len(event_queues))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/billing/charges", response_model=List[ChargeResponse])
async def get_billing_charges(request: Request):
    """Get pending charges between organizations."""
    fabric_client = getattr(request.app.state, "fabric_client", None)
    db_service = getattr(request.app.state, "db_service", None)

    # Define organization pairs to check
    org_pairs = [("Org1", "Org2"), ("Org2", "Org1")]
    charges = []

    if fabric_client:
        for debtor, creditor in org_pairs:
            try:
                result = await fabric_client.get_pending_charges(debtor, creditor)
                if result:
                    # Parse ChargeAccumulator from blockchain
                    # Chaincode returns: totalMicro, charges[] with packetType/packetCount/amountMicro
                    charge_items = result.get("charges", [])
                    uplink_count = sum(c.get("packetCount", 0) for c in charge_items if c.get("packetType") == "UPLINK")
                    downlink_count = sum(c.get("packetCount", 0) for c in charge_items if c.get("packetType") == "DOWNLINK")
                    join_count = sum(c.get("packetCount", 0) for c in charge_items if c.get("packetType") == "JOIN")
                    total_packets = uplink_count + downlink_count + join_count
                    total_amount_micro = result.get("totalMicro", 0)

                    if total_packets > 0 or total_amount_micro > 0:
                        charges.append(ChargeResponse(
                            debtorOrg=debtor,
                            creditorOrg=creditor,
                            totalPackets=total_packets,
                            uplinkCount=uplink_count,
                            downlinkCount=downlink_count,
                            joinCount=join_count,
                            totalAmountMicro=total_amount_micro,
                        ))
            except Exception as e:
                logger.warning("Failed to get charges", debtor=debtor, creditor=creditor, error=str(e))

    # Fallback to database if blockchain unavailable or empty
    if not charges and db_service:
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=30)
            summary = db_service.get_charge_summary(start_time, end_time)

            for entry in summary:
                charges.append(ChargeResponse(
                    debtorOrg=entry["debtorOrg"],
                    creditorOrg=entry["creditorOrg"],
                    totalPackets=entry["totalPackets"],
                    uplinkCount=entry["uplinkCount"],
                    downlinkCount=entry["downlinkCount"],
                    joinCount=entry["joinCount"],
                    totalAmountMicro=entry["totalAmountMicro"],
                ))
            if charges:
                logger.info("Billing charges loaded from database fallback", count=len(charges))
        except Exception as e:
            logger.warning("Failed to get charges from database", error=str(e))

    if not charges:
        logger.info("No billing charges found from blockchain or database")

    return charges


@router.get("/billing/summary", response_model=BillingSummary)
async def get_billing_summary(request: Request):
    """Get aggregated billing statistics."""
    charges = await get_billing_charges(request)

    total_charges = sum(c.totalAmountMicro for c in charges)

    return BillingSummary(
        totalCharges=total_charges,
        pendingSettlements=len([c for c in charges if c.totalAmountMicro > 0]),
        orgPairs=charges,
    )


@router.get("/stats/overview", response_model=StatsOverview)
async def get_stats_overview(request: Request):
    """Get combined system statistics for dashboard."""
    fabric_client = getattr(request.app.state, "fabric_client", None)
    db_service = getattr(request.app.state, "db_service", None)

    # Default values
    total_gateways = 0
    active_gateways = 0
    total_devices = 0
    events_today = 0
    pending_charges = 0

    # Get gateway stats from blockchain
    if fabric_client:
        try:
            gateways = await fabric_client.get_trusted_gateways(0.0)
            if gateways:
                total_gateways = len(gateways)
                active_gateways = len([g for g in gateways if g.get("status") == "ACTIVE"])
        except Exception as e:
            logger.warning("Failed to get gateway stats from blockchain", error=str(e))

    # Get event stats from database
    if db_service:
        try:
            session = db_service.get_session()
            try:
                from ..services.database import EventRecord
                from sqlalchemy import func

                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

                events_today = (
                    session.query(func.count(EventRecord.id))
                    .filter(EventRecord.timestamp >= today_start)
                    .scalar()
                ) or 0

                # Count unique devices seen in last 24 hours (active devices only)
                yesterday = datetime.utcnow() - timedelta(hours=24)
                total_devices = (
                    session.query(func.count(func.distinct(EventRecord.dev_eui)))
                    .filter(EventRecord.timestamp >= yesterday)
                    .scalar()
                ) or 0

                # DB fallback for gateway count: use the deduplicated gateway list
                if total_gateways == 0:
                    try:
                        gw_list = await list_gateways(request, min_trust=0.0)
                        total_gateways = len(gw_list)
                        active_gateways = len([g for g in gw_list if g.status == "ACTIVE"])
                    except Exception:
                        total_gateways = 0
                        active_gateways = 0
            finally:
                session.close()
        except Exception as e:
            logger.warning("Failed to get event stats", error=str(e))

    # Get billing stats
    try:
        billing = await get_billing_summary(request)
        pending_charges = billing.totalCharges
    except Exception:
        pending_charges = 0

    return StatsOverview(
        totalGateways=total_gateways,
        activeGateways=active_gateways,
        totalDevices=total_devices,
        eventsToday=events_today,
        pendingCharges=pending_charges,
        lastUpdated=datetime.utcnow().isoformat(),
    )
