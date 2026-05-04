#!/bin/bash

# Demo test script for the LoRaWAN Blockchain project
# Simulates webhook events to test the full flow

set -e

WEBHOOK_URL="${WEBHOOK_URL:-http://localhost:8000}"

echo "=== LoRaWAN Blockchain Demo Test ==="
echo ""

# Test 1: Health check
echo "1. Testing webhook listener health..."
curl -s "${WEBHOOK_URL}/webhook/health" | jq .
echo ""

# Test 2: Register demo organizations
echo "2. Registering demo devices and gateways..."

# Register devices
curl -s -X POST "${WEBHOOK_URL}/admin/register/device?dev_eui=70B3D57ED0000001&org=Org1" | jq .
curl -s -X POST "${WEBHOOK_URL}/admin/register/device?dev_eui=70B3D57ED0000002&org=Org2" | jq .

# Register gateways
curl -s -X POST "${WEBHOOK_URL}/admin/register/gateway?gateway_eui=AA555A0000000101&org=Org1" | jq .
curl -s -X POST "${WEBHOOK_URL}/admin/register/gateway?gateway_eui=AA555A0000000202&org=Org2" | jq .

echo ""

# Test 3: Simulate uplink from device owned by Org1 through gateway owned by Org1 (no roaming)
echo "3. Simulating non-roaming uplink (Org1 device -> Org1 gateway)..."
curl -s -X POST "${WEBHOOK_URL}/webhook/uplink" \
    -H "Content-Type: application/json" \
    -d '{
        "end_device_ids": {
            "device_id": "test-device-1",
            "application_ids": {"application_id": "test-app"},
            "dev_eui": "70B3D57ED0000001"
        },
        "correlation_ids": ["test-correlation-1"],
        "received_at": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
        "uplink_message": {
            "f_port": 1,
            "f_cnt": 1,
            "frm_payload": "SGVsbG8gV29ybGQ=",
            "rx_metadata": [{
                "gateway_ids": {
                    "gateway_id": "test-gateway-1",
                    "eui": "AA555A0000000101"
                },
                "rssi": -80,
                "snr": 7.5,
                "channel_index": 0
            }]
        }
    }' | jq .

echo ""

# Test 4: Simulate uplink from device owned by Org2 through gateway owned by Org1 (roaming!)
echo "4. Simulating ROAMING uplink (Org2 device -> Org1 gateway)..."
curl -s -X POST "${WEBHOOK_URL}/webhook/uplink" \
    -H "Content-Type: application/json" \
    -d '{
        "end_device_ids": {
            "device_id": "test-device-2",
            "application_ids": {"application_id": "test-app"},
            "dev_eui": "70B3D57ED0000002"
        },
        "correlation_ids": ["test-correlation-2"],
        "received_at": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
        "uplink_message": {
            "f_port": 1,
            "f_cnt": 1,
            "frm_payload": "Um9hbWluZyBUZXN0",
            "rx_metadata": [{
                "gateway_ids": {
                    "gateway_id": "test-gateway-1",
                    "eui": "AA555A0000000101"
                },
                "rssi": -95,
                "snr": 3.2,
                "channel_index": 0
            }]
        }
    }' | jq .

echo ""

# Test 5: Simulate join request
echo "5. Simulating join accept..."
curl -s -X POST "${WEBHOOK_URL}/webhook/join" \
    -H "Content-Type: application/json" \
    -d '{
        "end_device_ids": {
            "device_id": "test-device-2",
            "application_ids": {"application_id": "test-app"},
            "dev_eui": "70B3D57ED0000002",
            "join_eui": "0000000000000000"
        },
        "correlation_ids": ["test-join-1"],
        "received_at": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
        "join_accept": {
            "session_key_id": "test-session",
            "rx_metadata": [{
                "gateway_ids": {
                    "gateway_id": "test-gateway-1",
                    "eui": "AA555A0000000101"
                },
                "rssi": -90,
                "snr": 5.0
            }]
        }
    }' | jq .

echo ""

# Test 6: Check aggregator stats
echo "6. Checking aggregator buffer stats..."
curl -s "${WEBHOOK_URL}/stats" | jq .

echo ""

# Test 7: Force flush the aggregator
echo "7. Forcing aggregator flush..."
curl -s -X POST "${WEBHOOK_URL}/admin/flush" | jq .

echo ""

# Test 8: Check final stats
echo "8. Final service stats..."
curl -s "${WEBHOOK_URL}/stats" | jq .

echo ""
echo "=== Demo Test Complete ==="
echo ""
echo "Check the following for verification:"
echo "  - MySQL database: SELECT * FROM webhook_events;"
echo "  - Prometheus metrics: http://localhost:9090"
echo "  - Grafana dashboard: http://localhost:3000"
