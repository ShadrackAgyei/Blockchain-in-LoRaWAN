"""Hyperledger Fabric client wrapper for chaincode interactions."""

import asyncio
import json
import os
import time
from typing import Optional, Dict, Any, List
import structlog

from ..config import get_settings

logger = structlog.get_logger()


class FabricClient:
    """
    Client for interacting with Hyperledger Fabric chaincode.

    Uses the peer CLI for chaincode invocations.
    """

    def __init__(
        self,
        channel: Optional[str] = None,
        msp_id: Optional[str] = None,
    ):
        settings = get_settings()
        self.channel = channel or settings.fabric_channel
        self.msp_id = msp_id or settings.fabric_msp_id
        self.trust_chaincode = settings.trust_chaincode
        self.billing_chaincode = settings.billing_chaincode

        # Fabric network paths
        self.fabric_path = os.path.expanduser("~/fabric-samples")
        self.test_network_path = os.path.join(self.fabric_path, "test-network")
        self.bin_path = os.path.join(self.fabric_path, "bin")
        self.config_path = os.path.join(self.fabric_path, "config")

        # Organization configuration
        self.org_configs = {
            "Org1MSP": {
                "peer_address": "localhost:7051",
                "tls_rootcert": os.path.join(
                    self.test_network_path,
                    "organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
                ),
                "msp_config_path": os.path.join(
                    self.test_network_path,
                    "organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
                ),
            },
            "Org2MSP": {
                "peer_address": "localhost:9051",
                "tls_rootcert": os.path.join(
                    self.test_network_path,
                    "organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
                ),
                "msp_config_path": os.path.join(
                    self.test_network_path,
                    "organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp"
                ),
            },
        }

        # Orderer configuration
        self.orderer_address = "localhost:7050"
        self.orderer_tls_hostname = "orderer.example.com"
        self.orderer_ca_file = os.path.join(
            self.test_network_path,
            "organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem"
        )

        # Track transaction latencies for metrics
        self._transaction_latencies: List[float] = []
        self._connected = False

        logger.info(
            "FabricClient initialized",
            channel=self.channel,
            msp_id=self.msp_id,
        )

    async def connect(self):
        """Verify connection to Fabric network."""
        try:
            # Test by querying committed chaincodes
            env = self._get_env(self.msp_id)
            cmd = [
                os.path.join(self.bin_path, "peer"),
                "lifecycle", "chaincode", "querycommitted",
                "--channelID", self.channel,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                self._connected = True
                logger.info("Fabric client connected", output=stdout.decode()[:200])
            else:
                raise Exception(f"Failed to connect: {stderr.decode()}")

        except Exception as e:
            logger.error("Fabric connection failed", error=str(e))
            raise

    async def disconnect(self):
        """Disconnect from Fabric network."""
        self._connected = False
        logger.info("Fabric client disconnected")

    def _get_env(self, msp_id: str) -> Dict[str, str]:
        """Get environment variables for peer CLI."""
        org_config = self.org_configs.get(msp_id, self.org_configs["Org1MSP"])

        env = os.environ.copy()
        env.update({
            "PATH": f"{self.bin_path}:{env.get('PATH', '')}",
            "FABRIC_CFG_PATH": self.config_path,
            "CORE_PEER_TLS_ENABLED": "true",
            "CORE_PEER_LOCALMSPID": msp_id,
            "CORE_PEER_TLS_ROOTCERT_FILE": org_config["tls_rootcert"],
            "CORE_PEER_MSPCONFIGPATH": org_config["msp_config_path"],
            "CORE_PEER_ADDRESS": org_config["peer_address"],
        })
        return env

    async def _invoke_chaincode(
        self,
        chaincode: str,
        function: str,
        args: List[str],
        msp_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke a chaincode function using peer CLI."""
        start_time = time.time()
        use_msp = msp_id or self.msp_id

        try:
            # Build the args JSON
            invoke_args = {"function": function, "Args": args}
            args_json = json.dumps(invoke_args)

            env = self._get_env(use_msp)
            org1_config = self.org_configs["Org1MSP"]
            org2_config = self.org_configs["Org2MSP"]

            cmd = [
                os.path.join(self.bin_path, "peer"),
                "chaincode", "invoke",
                "-o", self.orderer_address,
                "--ordererTLSHostnameOverride", self.orderer_tls_hostname,
                "--tls",
                "--cafile", self.orderer_ca_file,
                "-C", self.channel,
                "-n", chaincode,
                "--peerAddresses", org1_config["peer_address"],
                "--tlsRootCertFiles", org1_config["tls_rootcert"],
                "--peerAddresses", org2_config["peer_address"],
                "--tlsRootCertFiles", org2_config["tls_rootcert"],
                "-c", args_json,
            ]

            logger.debug(
                "Invoking chaincode",
                chaincode=chaincode,
                function=function,
                args_count=len(args),
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            latency = time.time() - start_time
            self._transaction_latencies.append(latency)

            # Keep only last 1000 latencies for metrics
            if len(self._transaction_latencies) > 1000:
                self._transaction_latencies = self._transaction_latencies[-1000:]

            if proc.returncode != 0:
                error_msg = stderr.decode()
                logger.error(
                    "Chaincode invocation failed",
                    chaincode=chaincode,
                    function=function,
                    error=error_msg,
                )
                raise Exception(f"Chaincode invoke failed: {error_msg}")

            # Parse the transaction ID from output
            output = stderr.decode()  # peer CLI outputs to stderr
            tx_id = self._extract_tx_id(output)

            logger.info(
                "Chaincode invoked",
                chaincode=chaincode,
                function=function,
                tx_id=tx_id,
                latency_ms=round(latency * 1000, 2),
            )

            return {"txId": tx_id, "status": "SUCCESS", "payload": None}

        except Exception as e:
            latency = time.time() - start_time
            logger.error(
                "Chaincode invocation failed",
                chaincode=chaincode,
                function=function,
                error=str(e),
                latency_ms=round(latency * 1000, 2),
            )
            raise

    async def _query_chaincode(
        self,
        chaincode: str,
        function: str,
        args: List[str],
        msp_id: Optional[str] = None,
    ) -> Optional[str]:
        """Query a chaincode function using peer CLI."""
        use_msp = msp_id or self.msp_id

        try:
            invoke_args = {"function": function, "Args": args}
            args_json = json.dumps(invoke_args)

            env = self._get_env(use_msp)

            cmd = [
                os.path.join(self.bin_path, "peer"),
                "chaincode", "query",
                "-C", self.channel,
                "-n", chaincode,
                "-c", args_json,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode()
                logger.error(
                    "Chaincode query failed",
                    chaincode=chaincode,
                    function=function,
                    error=error_msg,
                )
                return None

            return stdout.decode().strip()

        except Exception as e:
            logger.error(
                "Chaincode query failed",
                chaincode=chaincode,
                function=function,
                error=str(e),
            )
            return None

    def _extract_tx_id(self, output: str) -> str:
        """Extract transaction ID from peer CLI output."""
        # Look for txid in the output
        import re
        match = re.search(r'txid \[([a-f0-9]+)\]', output)
        if match:
            return match.group(1)
        return f"tx_{int(time.time() * 1000)}"

    # TrustManagement chaincode functions

    async def record_forwarding_batch(
        self,
        gateway_eui: str,
        period_start: int,
        period_end: int,
        uplink_count: int,
        downlink_count: int,
        join_count: int,
        error_count: int,
        avg_rssi: float,
        avg_snr: float,
    ) -> str:
        """Record a batch of forwarding events on the blockchain."""
        result = await self._invoke_chaincode(
            self.trust_chaincode,
            "RecordForwardingBatch",
            [
                gateway_eui,
                str(period_start),
                str(period_end),
                str(uplink_count),
                str(downlink_count),
                str(join_count),
                str(error_count),
                str(avg_rssi) if avg_rssi else "0",
                str(avg_snr) if avg_snr else "0",
            ],
        )
        return result.get("txId", "")

    async def register_gateway(
        self,
        gateway_eui: str,
        owner_org: str,
        latitude: float,
        longitude: float,
        altitude: float,
    ) -> str:
        """Register a new gateway."""
        result = await self._invoke_chaincode(
            self.trust_chaincode,
            "RegisterGateway",
            [
                gateway_eui,
                owner_org,
                str(latitude),
                str(longitude),
                str(altitude),
            ],
        )
        return result.get("txId", "")

    async def get_gateway(self, gateway_eui: str) -> Optional[Dict[str, Any]]:
        """Get gateway information."""
        try:
            result = await self._query_chaincode(
                self.trust_chaincode,
                "GetGateway",
                [gateway_eui],
            )
            if result:
                return json.loads(result)
            return None
        except Exception:
            return None

    async def compute_trust_score(self, gateway_eui: str) -> float:
        """Compute and update the trust score for a gateway."""
        result = await self._invoke_chaincode(
            self.trust_chaincode,
            "ComputeTrustScore",
            [gateway_eui],
        )
        return 0.0

    async def get_trusted_gateways(self, min_trust_score: float) -> List[Dict[str, Any]]:
        """Get all gateways above a minimum trust score."""
        result = await self._query_chaincode(
            self.trust_chaincode,
            "GetTrustedGateways",
            [str(min_trust_score)],
        )
        if result:
            return json.loads(result)
        return []

    # Billing chaincode functions

    async def record_charge(
        self,
        dev_eui: str,
        gateway_eui: str,
        gateway_owner_org: str,
        packet_type: str,
        packet_count: int,
    ) -> str:
        """Record a billing charge for roaming traffic."""
        result = await self._invoke_chaincode(
            self.billing_chaincode,
            "RecordCharge",
            [
                dev_eui,
                gateway_eui,
                gateway_owner_org,
                packet_type,
                str(packet_count),
            ],
        )
        return result.get("txId", "")

    async def create_policy(
        self,
        policy_id: str,
        devices: List[str],
        packet_types: List[str],
        uplink_micro: int,
        downlink_micro: int,
        join_micro: int,
        valid_until: int,
        msp_id: Optional[str] = None,
    ) -> str:
        """Create a billing policy. Uses msp_id to set the policy's ownerOrg via getCallerOrg."""
        result = await self._invoke_chaincode(
            self.billing_chaincode,
            "CreatePolicy",
            [
                policy_id,
                json.dumps(devices),
                json.dumps(packet_types),
                str(uplink_micro),
                str(downlink_micro),
                str(join_micro),
                str(valid_until),
            ],
            msp_id=msp_id,
        )
        return result.get("txId", "")

    async def get_pending_charges(
        self,
        debtor_org: str,
        creditor_org: str,
    ) -> Optional[Dict[str, Any]]:
        """Get pending charges between two organizations."""
        try:
            result = await self._query_chaincode(
                self.billing_chaincode,
                "GetPendingCharges",
                [debtor_org, creditor_org],
            )
            if result:
                return json.loads(result)
            return None
        except Exception:
            return None

    async def initiate_settlement(
        self,
        debtor_org: str,
        creditor_org: str,
    ) -> Optional[Dict[str, Any]]:
        """Initiate a settlement for pending charges."""
        result = await self._invoke_chaincode(
            self.billing_chaincode,
            "InitiateSettlement",
            [debtor_org, creditor_org],
        )
        return {"txId": result.get("txId", "")}

    async def confirm_payment(
        self,
        settlement_id: str,
        payment_ref: str,
    ) -> str:
        """Confirm payment for a settlement."""
        result = await self._invoke_chaincode(
            self.billing_chaincode,
            "ConfirmPayment",
            [settlement_id, payment_ref],
        )
        return result.get("txId", "")

    # Metrics

    def get_latency_stats(self) -> Dict[str, float]:
        """Get transaction latency statistics."""
        if not self._transaction_latencies:
            return {"avg_ms": 0, "min_ms": 0, "max_ms": 0, "count": 0}

        latencies = self._transaction_latencies
        return {
            "avg_ms": round(sum(latencies) / len(latencies) * 1000, 2),
            "min_ms": round(min(latencies) * 1000, 2),
            "max_ms": round(max(latencies) * 1000, 2),
            "count": len(latencies),
        }
