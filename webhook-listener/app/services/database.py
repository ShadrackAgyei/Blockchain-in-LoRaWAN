"""Database service for storing webhook events."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
import structlog
import json


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

from ..config import get_settings

logger = structlog.get_logger()
Base = declarative_base()


class EventRecord(Base):
    """Model for storing webhook events in MySQL."""
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    dev_eui = Column(String(20), nullable=False, index=True)
    gateway_eui = Column(String(20), index=True)
    rssi = Column(Float)
    snr = Column(Float)
    timestamp = Column(DateTime, nullable=False, index=True)
    raw_payload = Column(Text)
    processed = Column(Boolean, default=False, index=True)
    blockchain_tx_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<EventRecord(id={self.id}, type={self.event_type}, dev={self.dev_eui})>"


class ForwardingBatchRecord(Base):
    """Model for storing aggregated forwarding batches sent to blockchain."""
    __tablename__ = "forwarding_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gateway_eui = Column(String(20), nullable=False, index=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    uplink_count = Column(Integer, default=0)
    downlink_count = Column(Integer, default=0)
    join_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    avg_rssi = Column(Float)
    avg_snr = Column(Float)
    blockchain_tx_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class ChargeRecord(Base):
    """Model for storing billing charges sent to blockchain."""
    __tablename__ = "billing_charges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dev_eui = Column(String(20), nullable=False, index=True)
    gateway_eui = Column(String(20), nullable=False, index=True)
    gateway_owner_org = Column(String(100), nullable=False)
    device_owner_org = Column(String(100), nullable=False)
    packet_type = Column(String(20), nullable=False)
    packet_count = Column(Integer, default=1)
    blockchain_tx_id = Column(String(100))
    timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DatabaseService:
    """Service for database operations."""

    def __init__(self, database_url: Optional[str] = None):
        settings = get_settings()
        url = database_url or settings.database_url

        self.engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info("Database service initialized", url=url.split("@")[-1])

    def init_db(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created/verified")

    def get_session(self):
        """Get a new database session."""
        return self.SessionLocal()

    def store_event(
        self,
        event_type: str,
        dev_eui: str,
        gateway_eui: Optional[str],
        rssi: Optional[float],
        snr: Optional[float],
        timestamp: datetime,
        raw_payload: dict,
    ) -> EventRecord:
        """Store a webhook event in the database."""
        session = self.get_session()
        try:
            record = EventRecord(
                event_type=event_type,
                dev_eui=dev_eui,
                gateway_eui=gateway_eui,
                rssi=rssi,
                snr=snr,
                timestamp=timestamp,
                raw_payload=json.dumps(raw_payload, cls=DateTimeEncoder),
                processed=False,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.debug(
                "Event stored",
                event_id=record.id,
                event_type=event_type,
                dev_eui=dev_eui,
            )
            return record
        except Exception as e:
            session.rollback()
            logger.error("Failed to store event", error=str(e))
            raise
        finally:
            session.close()

    def mark_event_processed(self, event_id: int, blockchain_tx_id: str):
        """Mark an event as processed with the blockchain transaction ID."""
        session = self.get_session()
        try:
            record = session.query(EventRecord).filter_by(id=event_id).first()
            if record:
                record.processed = True
                record.blockchain_tx_id = blockchain_tx_id
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to mark event processed", error=str(e))
        finally:
            session.close()

    def store_forwarding_batch(
        self,
        gateway_eui: str,
        period_start: datetime,
        period_end: datetime,
        uplink_count: int,
        downlink_count: int,
        join_count: int,
        error_count: int,
        avg_rssi: Optional[float],
        avg_snr: Optional[float],
        blockchain_tx_id: str,
    ) -> ForwardingBatchRecord:
        """Store a forwarding batch record."""
        session = self.get_session()
        try:
            record = ForwardingBatchRecord(
                gateway_eui=gateway_eui,
                period_start=period_start,
                period_end=period_end,
                uplink_count=uplink_count,
                downlink_count=downlink_count,
                join_count=join_count,
                error_count=error_count,
                avg_rssi=avg_rssi,
                avg_snr=avg_snr,
                blockchain_tx_id=blockchain_tx_id,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
        except Exception as e:
            session.rollback()
            logger.error("Failed to store forwarding batch", error=str(e))
            raise
        finally:
            session.close()

    def store_charge_record(
        self,
        dev_eui: str,
        gateway_eui: str,
        gateway_owner_org: str,
        device_owner_org: str,
        packet_type: str,
        packet_count: int,
        blockchain_tx_id: str,
        timestamp: datetime,
    ) -> ChargeRecord:
        """Store a billing charge record."""
        session = self.get_session()
        try:
            record = ChargeRecord(
                dev_eui=dev_eui,
                gateway_eui=gateway_eui,
                gateway_owner_org=gateway_owner_org,
                device_owner_org=device_owner_org,
                packet_type=packet_type,
                packet_count=packet_count,
                blockchain_tx_id=blockchain_tx_id,
                timestamp=timestamp,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
        except Exception as e:
            session.rollback()
            logger.error("Failed to store charge record", error=str(e))
            raise
        finally:
            session.close()

    def get_unprocessed_events(self, limit: int = 100) -> List[EventRecord]:
        """Get unprocessed events for retry processing."""
        session = self.get_session()
        try:
            return (
                session.query(EventRecord)
                .filter_by(processed=False)
                .order_by(EventRecord.timestamp)
                .limit(limit)
                .all()
            )
        finally:
            session.close()

    def get_events_by_gateway(
        self,
        gateway_eui: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[EventRecord]:
        """Get events for a specific gateway within a time range."""
        session = self.get_session()
        try:
            return (
                session.query(EventRecord)
                .filter(
                    EventRecord.gateway_eui == gateway_eui,
                    EventRecord.timestamp >= start_time,
                    EventRecord.timestamp <= end_time,
                )
                .order_by(EventRecord.timestamp)
                .all()
            )
        finally:
            session.close()

    def get_charge_summary(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list:
        """Get a summary of charges within a time range, broken down by org pair and packet type."""
        session = self.get_session()
        try:
            from sqlalchemy import func
            from collections import defaultdict

            # Default pricing (matches chaincode InitLedger defaults)
            pricing = {"UPLINK": 100, "DOWNLINK": 200, "JOIN": 500}

            results = (
                session.query(
                    ChargeRecord.device_owner_org,
                    ChargeRecord.gateway_owner_org,
                    ChargeRecord.packet_type,
                    func.sum(ChargeRecord.packet_count).label("total_packets"),
                )
                .filter(
                    ChargeRecord.timestamp >= start_time,
                    ChargeRecord.timestamp <= end_time,
                )
                .group_by(
                    ChargeRecord.device_owner_org,
                    ChargeRecord.gateway_owner_org,
                    ChargeRecord.packet_type,
                )
                .all()
            )

            # Aggregate by org pair
            pairs = defaultdict(lambda: {"uplink": 0, "downlink": 0, "join": 0, "amount": 0})
            for row in results:
                key = (row.device_owner_org, row.gateway_owner_org)
                count = int(row.total_packets or 0)
                ptype = row.packet_type.upper()
                if ptype == "UPLINK":
                    pairs[key]["uplink"] += count
                elif ptype == "DOWNLINK":
                    pairs[key]["downlink"] += count
                elif ptype == "JOIN":
                    pairs[key]["join"] += count
                pairs[key]["amount"] += count * pricing.get(ptype, 100)

            summary = []
            for (debtor, creditor), data in pairs.items():
                summary.append({
                    "debtorOrg": debtor,
                    "creditorOrg": creditor,
                    "uplinkCount": data["uplink"],
                    "downlinkCount": data["downlink"],
                    "joinCount": data["join"],
                    "totalPackets": data["uplink"] + data["downlink"] + data["join"],
                    "totalAmountMicro": data["amount"],
                })

            return summary
        finally:
            session.close()
