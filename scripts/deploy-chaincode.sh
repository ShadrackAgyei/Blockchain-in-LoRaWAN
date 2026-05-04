#!/bin/bash

# Deploy chaincode to Hyperledger Fabric network using Chaincode-as-a-Service (ccaas)
# This script assumes the Fabric test-network is already running with ccaas_builder configured.
#
# Usage: ./scripts/deploy-chaincode.sh [--sequence N] [--version V]
#
# The ccaas approach builds chaincodes as Docker images and runs them as external
# containers, avoiding the Docker-in-Docker API version incompatibility.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FABRIC_SAMPLES_PATH="${FABRIC_SAMPLES_PATH:-$HOME/fabric-samples}"
CHANNEL_NAME="${CHANNEL_NAME:-lorawan-channel}"
CC_VERSION="${CC_VERSION:-1.0}"
CC_SEQUENCE="${CC_SEQUENCE:-1}"

# Parse optional flags
while [[ $# -gt 0 ]]; do
    case $1 in
        --sequence) CC_SEQUENCE="$2"; shift 2 ;;
        --version)  CC_VERSION="$2"; shift 2 ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=== Deploying LoRaWAN Blockchain Chaincode (ccaas) ==="
echo "    Version: $CC_VERSION  Sequence: $CC_SEQUENCE  Channel: $CHANNEL_NAME"

# Check prerequisites
if [ ! -d "$FABRIC_SAMPLES_PATH" ]; then
    echo "Error: Fabric samples not found at $FABRIC_SAMPLES_PATH"
    exit 1
fi

if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running"
    exit 1
fi

export PATH="$FABRIC_SAMPLES_PATH/bin:$PATH"
export FABRIC_CFG_PATH="$FABRIC_SAMPLES_PATH/config/"

ORDERER_CA="$FABRIC_SAMPLES_PATH/test-network/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem"
ORG1_TLS="$FABRIC_SAMPLES_PATH/test-network/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
ORG2_TLS="$FABRIC_SAMPLES_PATH/test-network/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"

set_org1() {
    export CORE_PEER_TLS_ENABLED=true
    export CORE_PEER_LOCALMSPID="Org1MSP"
    export CORE_PEER_TLS_ROOTCERT_FILE="$ORG1_TLS"
    export CORE_PEER_MSPCONFIGPATH="$FABRIC_SAMPLES_PATH/test-network/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
    export CORE_PEER_ADDRESS=localhost:7051
}

set_org2() {
    export CORE_PEER_TLS_ENABLED=true
    export CORE_PEER_LOCALMSPID="Org2MSP"
    export CORE_PEER_TLS_ROOTCERT_FILE="$ORG2_TLS"
    export CORE_PEER_MSPCONFIGPATH="$FABRIC_SAMPLES_PATH/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp"
    export CORE_PEER_ADDRESS=localhost:9051
}

# ============================================================
# Step 1: Build Docker images
# ============================================================
echo ""
echo "--- Step 1: Building chaincode Docker images ---"

echo "Building trustmanagement_ccaas:${CC_VERSION}..."
docker build -t "trustmanagement_ccaas:${CC_VERSION}" "$PROJECT_DIR/chaincode/trustmanagement/"

echo "Building billing_ccaas:${CC_VERSION}..."
docker build -t "billing_ccaas:${CC_VERSION}" "$PROJECT_DIR/chaincode/billing/"

# ============================================================
# Step 2: Create ccaas packages
# ============================================================
echo ""
echo "--- Step 2: Creating ccaas packages ---"

PKG_DIR=$(mktemp -d)
for CC_NAME in trustmanagement billing; do
    mkdir -p "$PKG_DIR/$CC_NAME"

    # connection.json - container name on fabric_test network, port 9999
    cat > "$PKG_DIR/$CC_NAME/connection.json" <<EOF
{
  "address": "${CC_NAME}_ccaas:9999",
  "dial_timeout": "10s",
  "tls_required": false
}
EOF

    cat > "$PKG_DIR/$CC_NAME/metadata.json" <<EOF
{
  "type": "ccaas",
  "label": "${CC_NAME}_${CC_VERSION}"
}
EOF

    (cd "$PKG_DIR/$CC_NAME" && tar czf code.tar.gz connection.json && tar czf "${CC_NAME}_ccaas.tar.gz" code.tar.gz metadata.json)
    echo "  Created ${CC_NAME}_ccaas.tar.gz"
done

# ============================================================
# Step 3: Install on both peers
# ============================================================
echo ""
echo "--- Step 3: Installing chaincodes on both peers ---"

for CC_NAME in trustmanagement billing; do
    set_org1
    echo "  Installing ${CC_NAME} on Org1..."
    peer lifecycle chaincode install "$PKG_DIR/$CC_NAME/${CC_NAME}_ccaas.tar.gz"

    set_org2
    echo "  Installing ${CC_NAME} on Org2..."
    peer lifecycle chaincode install "$PKG_DIR/$CC_NAME/${CC_NAME}_ccaas.tar.gz"
done

# ============================================================
# Step 4: Get package IDs and approve for both orgs
# ============================================================
echo ""
echo "--- Step 4: Approving chaincodes for both orgs ---"

set_org1
INSTALLED_JSON=$(peer lifecycle chaincode queryinstalled --output json)

for CC_NAME in trustmanagement billing; do
    PACKAGE_ID=$(echo "$INSTALLED_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cc in data.get('installed_chaincodes', []):
    if cc['label'] == '${CC_NAME}_${CC_VERSION}':
        print(cc['package_id'])
        break
")
    echo "  ${CC_NAME} package ID: $PACKAGE_ID"

    if [ -z "$PACKAGE_ID" ]; then
        echo "Error: Could not find package ID for ${CC_NAME}_${CC_VERSION}"
        exit 1
    fi

    # Approve for Org1
    set_org1
    echo "  Approving ${CC_NAME} for Org1..."
    peer lifecycle chaincode approveformyorg -o localhost:7050 \
        --ordererTLSHostnameOverride orderer.example.com \
        --tls --cafile "$ORDERER_CA" \
        --channelID "$CHANNEL_NAME" \
        --name "$CC_NAME" \
        --version "$CC_VERSION" \
        --package-id "$PACKAGE_ID" \
        --sequence "$CC_SEQUENCE"

    # Approve for Org2
    set_org2
    echo "  Approving ${CC_NAME} for Org2..."
    peer lifecycle chaincode approveformyorg -o localhost:7050 \
        --ordererTLSHostnameOverride orderer.example.com \
        --tls --cafile "$ORDERER_CA" \
        --channelID "$CHANNEL_NAME" \
        --name "$CC_NAME" \
        --version "$CC_VERSION" \
        --package-id "$PACKAGE_ID" \
        --sequence "$CC_SEQUENCE"

    # Store package ID for container launch
    eval "$(echo "$CC_NAME" | tr '[:lower:]' '[:upper:]')_PACKAGE_ID=\$PACKAGE_ID"
done

# ============================================================
# Step 5: Commit chaincodes
# ============================================================
echo ""
echo "--- Step 5: Committing chaincodes to channel ---"

set_org1
for CC_NAME in trustmanagement billing; do
    echo "  Committing ${CC_NAME}..."
    peer lifecycle chaincode commit -o localhost:7050 \
        --ordererTLSHostnameOverride orderer.example.com \
        --tls --cafile "$ORDERER_CA" \
        --channelID "$CHANNEL_NAME" \
        --name "$CC_NAME" \
        --version "$CC_VERSION" \
        --sequence "$CC_SEQUENCE" \
        --peerAddresses localhost:7051 --tlsRootCertFiles "$ORG1_TLS" \
        --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_TLS"
done

# ============================================================
# Step 6: Start chaincode containers
# ============================================================
echo ""
echo "--- Step 6: Starting chaincode containers ---"

# Remove old containers if they exist
docker rm -f trustmanagement_ccaas billing_ccaas 2>/dev/null || true

# Re-query package IDs for container env vars
set_org1
INSTALLED_JSON=$(peer lifecycle chaincode queryinstalled --output json)

for CC_NAME in trustmanagement billing; do
    PACKAGE_ID=$(echo "$INSTALLED_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cc in data.get('installed_chaincodes', []):
    if cc['label'] == '${CC_NAME}_${CC_VERSION}':
        print(cc['package_id'])
        break
")

    echo "  Starting ${CC_NAME}_ccaas container..."
    docker run -d \
        --name "${CC_NAME}_ccaas" \
        --network fabric_test \
        -e CHAINCODE_SERVER_ADDRESS=0.0.0.0:9999 \
        -e CORE_CHAINCODE_ID_NAME="$PACKAGE_ID" \
        "${CC_NAME}_ccaas:${CC_VERSION}"
done

# Wait for containers to start
sleep 2

# ============================================================
# Step 7: Verify deployment
# ============================================================
echo ""
echo "--- Step 7: Verifying deployment ---"

set_org1
echo "  Committed chaincodes:"
peer lifecycle chaincode querycommitted --channelID "$CHANNEL_NAME" 2>&1 | grep -E "Name:|Version:|Sequence:"

echo ""
echo "  Chaincode containers:"
docker ps --filter name=ccaas --format "  {{.Names}}  {{.Status}}  {{.Networks}}"

# Initialize ledgers
echo ""
echo "  Initializing trustmanagement ledger..."
peer chaincode invoke -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls --cafile "$ORDERER_CA" \
    -C "$CHANNEL_NAME" -n trustmanagement \
    --peerAddresses localhost:7051 --tlsRootCertFiles "$ORG1_TLS" \
    --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_TLS" \
    -c '{"function":"InitLedger","Args":[]}' 2>&1

echo "  Initializing billing ledger..."
peer chaincode invoke -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls --cafile "$ORDERER_CA" \
    -C "$CHANNEL_NAME" -n billing \
    --peerAddresses localhost:7051 --tlsRootCertFiles "$ORG1_TLS" \
    --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_TLS" \
    -c '{"function":"InitLedger","Args":[]}' 2>&1

# Cleanup temp dir
rm -rf "$PKG_DIR"

echo ""
echo "=== All chaincodes deployed and verified successfully! ==="
echo ""
echo "Chaincode containers running on fabric_test network:"
echo "  - trustmanagement_ccaas (port 9999)"
echo "  - billing_ccaas (port 9999)"
