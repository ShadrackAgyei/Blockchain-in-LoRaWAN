"""Fabric peer CLI helper for evaluation scripts."""

import asyncio
import json
import os
import re
import time
from typing import Optional


FABRIC_PATH = os.path.expanduser("~/fabric-samples")
TEST_NETWORK = os.path.join(FABRIC_PATH, "test-network")
BIN_PATH = os.path.join(FABRIC_PATH, "bin")
CONFIG_PATH = os.path.join(FABRIC_PATH, "config")
CHANNEL = "lorawan-channel"

ORG_CONFIGS = {
    "Org1MSP": {
        "peer_address": "localhost:7051",
        "tls_rootcert": os.path.join(
            TEST_NETWORK,
            "organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt",
        ),
        "msp_config_path": os.path.join(
            TEST_NETWORK,
            "organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp",
        ),
    },
    "Org2MSP": {
        "peer_address": "localhost:9051",
        "tls_rootcert": os.path.join(
            TEST_NETWORK,
            "organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt",
        ),
        "msp_config_path": os.path.join(
            TEST_NETWORK,
            "organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp",
        ),
    },
}

ORDERER_ADDRESS = "localhost:7050"
ORDERER_TLS_HOSTNAME = "orderer.example.com"
ORDERER_CA_FILE = os.path.join(
    TEST_NETWORK,
    "organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem",
)


def _get_env(msp_id: str) -> dict:
    """Build environment variables for peer CLI."""
    org = ORG_CONFIGS.get(msp_id, ORG_CONFIGS["Org1MSP"])
    env = os.environ.copy()
    env.update({
        "PATH": f"{BIN_PATH}:{env.get('PATH', '')}",
        "FABRIC_CFG_PATH": CONFIG_PATH,
        "CORE_PEER_TLS_ENABLED": "true",
        "CORE_PEER_LOCALMSPID": msp_id,
        "CORE_PEER_TLS_ROOTCERT_FILE": org["tls_rootcert"],
        "CORE_PEER_MSPCONFIGPATH": org["msp_config_path"],
        "CORE_PEER_ADDRESS": org["peer_address"],
    })
    return env


def _extract_tx_id(output: str) -> str:
    """Extract transaction ID from peer CLI stderr."""
    match = re.search(r"txid \[([a-f0-9]+)\]", output)
    return match.group(1) if match else f"tx_{int(time.time() * 1000)}"


async def invoke_chaincode(
    chaincode: str,
    function: str,
    args: list[str],
    msp_id: str = "Org1MSP",
) -> dict:
    """Invoke a chaincode function. Returns {"txId": ..., "latency_ms": ...}."""
    start = time.time()
    invoke_args = json.dumps({"function": function, "Args": args})
    env = _get_env(msp_id)
    org1 = ORG_CONFIGS["Org1MSP"]
    org2 = ORG_CONFIGS["Org2MSP"]

    cmd = [
        os.path.join(BIN_PATH, "peer"),
        "chaincode", "invoke",
        "-o", ORDERER_ADDRESS,
        "--ordererTLSHostnameOverride", ORDERER_TLS_HOSTNAME,
        "--tls",
        "--cafile", ORDERER_CA_FILE,
        "-C", CHANNEL,
        "-n", chaincode,
        "--peerAddresses", org1["peer_address"],
        "--tlsRootCertFiles", org1["tls_rootcert"],
        "--peerAddresses", org2["peer_address"],
        "--tlsRootCertFiles", org2["tls_rootcert"],
        "-c", invoke_args,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    latency_ms = round((time.time() - start) * 1000, 2)

    if proc.returncode != 0:
        error = stderr.decode()
        raise RuntimeError(f"Invoke failed ({function}): {error}")

    tx_id = _extract_tx_id(stderr.decode())
    return {"txId": tx_id, "latency_ms": latency_ms}


async def query_chaincode(
    chaincode: str,
    function: str,
    args: list[str],
    msp_id: str = "Org1MSP",
) -> Optional[str]:
    """Query a chaincode function. Returns raw stdout string or None."""
    start = time.time()
    invoke_args = json.dumps({"function": function, "Args": args})
    env = _get_env(msp_id)

    cmd = [
        os.path.join(BIN_PATH, "peer"),
        "chaincode", "query",
        "-C", CHANNEL,
        "-n", chaincode,
        "-c", invoke_args,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    latency_ms = round((time.time() - start) * 1000, 2)

    if proc.returncode != 0:
        error = stderr.decode()
        raise RuntimeError(f"Query failed ({function}): {error}")

    return stdout.decode().strip()


# ── Convenience wrappers ─────────────────────────────────────────

async def register_gateway(eui: str, owner_org: str, lat: float, lon: float, alt: float, msp_id: str = "Org1MSP"):
    """RegisterGateway on trustmanagement chaincode."""
    return await invoke_chaincode(
        "trustmanagement", "RegisterGateway",
        [eui, owner_org, str(lat), str(lon), str(alt)],
        msp_id=msp_id,
    )


async def compute_trust_score(eui: str):
    """ComputeTrustScore — returns {"txId", "latency_ms"}."""
    return await invoke_chaincode(
        "trustmanagement", "ComputeTrustScore", [eui],
    )


async def get_gateway(eui: str) -> Optional[dict]:
    """GetGateway — returns parsed JSON or None."""
    raw = await query_chaincode("trustmanagement", "GetGateway", [eui])
    return json.loads(raw) if raw else None


async def get_trusted_gateways(min_score: float) -> list:
    """GetTrustedGateways — returns list of gateway dicts."""
    raw = await query_chaincode(
        "trustmanagement", "GetTrustedGateways", [str(min_score)],
    )
    return json.loads(raw) if raw else []


async def update_gateway_status(eui: str, status: str, msp_id: str = "Org1MSP"):
    """UpdateGatewayStatus (ACTIVE/SUSPENDED)."""
    return await invoke_chaincode(
        "trustmanagement", "UpdateGatewayStatus",
        [eui, status], msp_id=msp_id,
    )


async def get_forwarding_history(eui: str, start_time: int, end_time: int) -> list:
    """GetForwardingHistory — returns list of record dicts."""
    raw = await query_chaincode(
        "trustmanagement", "GetForwardingHistory",
        [eui, str(start_time), str(end_time)],
    )
    return json.loads(raw) if raw else []


async def get_pending_charges(debtor_org: str, creditor_org: str) -> Optional[dict]:
    """GetPendingCharges from billing chaincode."""
    try:
        raw = await query_chaincode(
            "billing", "GetPendingCharges", [debtor_org, creditor_org],
        )
        return json.loads(raw) if raw else None
    except RuntimeError:
        return None


async def initiate_settlement(debtor_org: str, creditor_org: str, msp_id: str = "Org1MSP"):
    """InitiateSettlement on billing chaincode."""
    return await invoke_chaincode(
        "billing", "InitiateSettlement",
        [debtor_org, creditor_org], msp_id=msp_id,
    )


async def confirm_payment(settlement_id: str, payment_ref: str, msp_id: str = "Org1MSP"):
    """ConfirmPayment on billing chaincode."""
    return await invoke_chaincode(
        "billing", "ConfirmPayment",
        [settlement_id, payment_ref], msp_id=msp_id,
    )
