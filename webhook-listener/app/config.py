"""Configuration management for the webhook listener service."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # TTN Webhook settings
    ttn_webhook_secret: str = ""
    ttn_api_key: str = ""

    # Database settings
    database_url: str = "mysql+pymysql://lorawan:lorawan@localhost:3307/lorawan_events"

    # Hyperledger Fabric settings
    fabric_gateway_url: str = "localhost:7051"
    fabric_channel: str = "lorawan-channel"
    fabric_msp_id: str = "Org1MSP"
    fabric_cert_path: str = "/fabric/crypto/users/User1@org1.example.com/msp/signcerts/cert.pem"
    fabric_key_path: str = "/fabric/crypto/users/User1@org1.example.com/msp/keystore/priv_sk"
    fabric_tls_cert_path: str = "/fabric/crypto/peers/peer0.org1.example.com/tls/ca.crt"
    fabric_peer_endpoint: str = "peer0.org1.example.com:7051"

    # Aggregator settings
    aggregation_window_seconds: int = 300  # 5 minutes
    aggregation_max_buffer_size: int = 100

    # Chaincode names
    trust_chaincode: str = "trustmanagement"
    billing_chaincode: str = "billing"

    # Organization mapping (gateway EUI prefix -> org)
    # In production, this would be queried from the blockchain
    gateway_org_mapping: dict = {}

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
