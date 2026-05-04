#!/bin/bash

# Setup Hyperledger Fabric test network for LoRaWAN project
# This script creates a 2-org network with the lorawan-channel

set -e

FABRIC_SAMPLES_PATH="${FABRIC_SAMPLES_PATH:-$HOME/fabric-samples}"

echo "=== Setting up Hyperledger Fabric Network ==="

# Check if Fabric samples directory exists
if [ ! -d "$FABRIC_SAMPLES_PATH" ]; then
    echo "Error: Fabric samples not found at $FABRIC_SAMPLES_PATH"
    echo ""
    echo "To install Hyperledger Fabric:"
    echo "  curl -sSLO https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/install-fabric.sh"
    echo "  chmod +x install-fabric.sh"
    echo "  ./install-fabric.sh docker samples binary"
    exit 1
fi

cd "$FABRIC_SAMPLES_PATH/test-network"

# Set environment
export PATH="$FABRIC_SAMPLES_PATH/bin:$PATH"
export FABRIC_CFG_PATH="$FABRIC_SAMPLES_PATH/config/"

# Bring down any existing network
echo "Bringing down existing network..."
./network.sh down

# Bring up network with CA and create channel
echo "Starting network with CAs..."
./network.sh up createChannel -ca -c lorawan-channel

echo ""
echo "=== Fabric Network Ready ==="
echo ""
echo "Network topology:"
echo "  - Org1: peer0.org1.example.com (localhost:7051)"
echo "  - Org2: peer0.org2.example.com (localhost:9051)"
echo "  - Orderer: orderer.example.com (localhost:7050)"
echo "  - Channel: lorawan-channel"
echo ""
echo "Next steps:"
echo "  1. Run: ./scripts/deploy-chaincode.sh"
echo "  2. Start the webhook listener: docker-compose up -d"
