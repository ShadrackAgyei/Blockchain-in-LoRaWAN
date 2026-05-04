# Physical Hardware Setup Guide

This guide covers setting up the physical LoRaWAN hardware for the blockchain capstone project.

## Current Status

- Hyperledger Fabric network deployed (2 orgs, lorawan-channel)
- TrustManagement + Billing chaincodes running
- Webhook listener connected to blockchain (localhost:8080)
- MySQL, Prometheus, Grafana running

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   ESP32 + LoRa  │────▶│  RPi + RAK5146  │────▶│  Public TTN     │
│   (OTAA Auth)   │     │  Basics Station │     │  EU868 Region   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │ Webhooks
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌────────┴────────┐
│ Hyperledger     │◀────│  Webhook        │◀────│   MySQL         │
│ Fabric          │     │  Listener       │     │   (event cache) │
│ (localhost)     │     │  :8080          │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Hardware Components

| Component | Model | Purpose |
|-----------|-------|---------|
| Gateway | Raspberry Pi 5 + RAK5146 | LoRaWAN concentrator |
| End Device | ESP32 + SX1276/SX1278 | Sensor node |
| Region | EU868 | European frequency band |

---

## Step 1: Raspberry Pi Gateway Setup

### 1.1 Prepare Raspberry Pi 5

1. Flash **Raspberry Pi OS Lite (64-bit)** using Raspberry Pi Imager
2. Enable SSH during imaging (set username/password)
3. Connect to network (Ethernet recommended initially)

```bash
# After boot, SSH into Pi:
ssh pi@<raspberry-pi-ip>

# Update system
sudo apt update && sudo apt upgrade -y

# Enable SPI (required for RAK5146)
sudo raspi-config
# -> Interface Options -> SPI -> Enable

# Reboot
sudo reboot
```

### 1.2 Install RAK5146 Basics Station

Copy the gateway configuration files to your Raspberry Pi:

```bash
# On your development machine:
scp -r gateway/ pi@<raspberry-pi-ip>:~/

# On Raspberry Pi:
cd ~/gateway
chmod +x setup-gateway.sh
./setup-gateway.sh
```

The setup script will:
- Install Docker and dependencies
- Enable SPI interface
- Clone Basics Station repository
- Create configuration directory at `~/gateway-config/`

### 1.3 Configure for TTN

1. **Get Gateway EUI**: Check the label on your RAK5146 or run `gateway-version`

2. **Edit configuration files**:

```bash
# Edit station.conf - replace YOUR_GATEWAY_EUI
nano ~/gateway-config/station.conf

# Edit tc.key - replace YOUR_TTN_API_KEY_HERE
nano ~/gateway-config/tc.key
```

---

## Step 2: Register Gateway on TTN

### 2.1 Create TTN Account & Application

1. Go to https://console.cloud.thethings.network/
2. Select **Europe 1** cluster (for EU868)
3. Create account or login
4. Click **Go to applications** → **+ Create application**
   - Application ID: `lorawan-blockchain-demo`
   - Description: "LoRaWAN Blockchain Capstone Project"

### 2.2 Register Gateway

1. Go to **Gateways** → **+ Register gateway**
2. Enter Gateway details:
   - **Gateway EUI**: (from RAK5146 label)
   - **Gateway ID**: `rak5146-gateway-01`
   - **Frequency plan**: `Europe 863-870 MHz (SF7-SF12 for RX2)`

3. Generate **API Key**:
   - Gateway settings → **API keys** → **+ Add API key**
   - Grant: `Link as Gateway to a Gateway Server for traffic exchange`
   - Copy the key to `tc.key` file on Raspberry Pi

### 2.3 Start Gateway

```bash
# On Raspberry Pi:
~/start-gateway.sh

# Check TTN Console -> Gateways -> Your gateway
# Status should show "Connected" with live data
```

---

## Step 3: ESP32 End Device Setup

### 3.1 Hardware Wiring

Connect SX1276/SX1278 to ESP32:

| SX1276 Pin | ESP32 Pin | Function |
|------------|-----------|----------|
| VCC        | 3.3V      | Power    |
| GND        | GND       | Ground   |
| SCK        | GPIO18    | SPI Clock|
| MISO       | GPIO19    | SPI MISO |
| MOSI       | GPIO23    | SPI MOSI |
| NSS        | GPIO5     | SPI CS   |
| RST        | GPIO14    | Reset    |
| DIO0       | GPIO26    | Interrupt|
| DIO1       | GPIO33    | Interrupt|

### 3.2 Development Environment

**Option A: Arduino IDE**

1. Install Arduino IDE 2.x
2. Add ESP32 board support:
   - File → Preferences → Additional Board URLs:
   - `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Install **MCCI LoRaWAN LMIC library** via Library Manager
4. Open `devices/esp32/esp32_lorawan_otaa.ino`

**Option B: PlatformIO (Recommended)**

```bash
# Install PlatformIO CLI or VS Code extension
cd devices/esp32

# Build
pio run

# Upload
pio run -t upload

# Monitor serial output
pio device monitor
```

### 3.3 Configure Device Credentials

1. Register device on TTN Console (see Step 4)
2. Edit firmware with your credentials:

```cpp
// DevEUI (LSB format) - reverse byte order from TTN
static const u1_t PROGMEM DEVEUI[8] = {
    0x01, 0x00, 0x00, 0xD0, 0x7E, 0xD5, 0xB3, 0x70
};

// AppEUI (LSB format)
static const u1_t PROGMEM APPEUI[8] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};

// AppKey (MSB format) - same order as TTN
static const u1_t PROGMEM APPKEY[16] = {
    0xAB, 0xCD, 0xEF, 0x01, 0x23, 0x45, 0x67, 0x89,
    0xAB, 0xCD, 0xEF, 0x01, 0x23, 0x45, 0x67, 0x89
};
```

**Byte Order Conversion:**
- TTN shows: `70B3D57ED0000001`
- LSB format: `{ 0x01, 0x00, 0x00, 0xD0, 0x7E, 0xD5, 0xB3, 0x70 }`

---

## Step 4: Register End Device on TTN

### 4.1 Add Device to Application

1. TTN Console → Applications → `lorawan-blockchain-demo`
2. **End devices** → **+ Register end device**
3. Select **Enter end device specifics manually**
4. Configure:
   - **Frequency plan**: Europe 863-870 MHz
   - **LoRaWAN version**: 1.0.3
   - **Regional Parameters**: RP001 1.0.3 Rev A

5. Enter device identifiers:
   - **DevEUI**: Generate or enter custom
   - **AppEUI**: Use application's default or generate
   - **AppKey**: Generate
   - **End device ID**: `esp32-device-01`

### 4.2 Add Payload Decoder

TTN Console → Applications → Payload formatters → Uplink:

```javascript
function decodeUplink(input) {
  var data = {};

  // Temperature (bytes 0-1, signed int16, /100)
  var tempRaw = (input.bytes[0] << 8) | input.bytes[1];
  if (tempRaw > 32767) tempRaw -= 65536;
  data.temperature = tempRaw / 100.0;

  // Humidity (byte 2)
  data.humidity = input.bytes[2];

  // Battery voltage (bytes 3-4, mV)
  data.battery_mv = (input.bytes[3] << 8) | input.bytes[4];
  data.battery_v = data.battery_mv / 1000.0;

  // Packet counter (bytes 5-6)
  data.packet_count = (input.bytes[5] << 8) | input.bytes[6];

  // Status byte (byte 7)
  data.status = input.bytes[7];

  return {
    data: data,
    warnings: [],
    errors: []
  };
}
```

---

## Step 5: Configure TTN Webhooks

### 5.1 Create Webhook Integration

1. TTN Console → Applications → `lorawan-blockchain-demo`
2. **Integrations** → **Webhooks** → **+ Add webhook**
3. Choose **Custom webhook**
4. Configure:
   - **Webhook ID**: `blockchain-listener`
   - **Webhook format**: JSON
   - **Base URL**: `http://<your-server-ip>:8080`
   - **Enabled messages**:
     - Uplink message: `/webhook/uplink`
     - Join accept: `/webhook/join`
     - Downlink ack: `/webhook/downlink`

### 5.2 Expose Webhook Listener

**Option A: ngrok (Quick testing)**
```bash
ngrok http 8080
# Use the ngrok URL in TTN webhook config
```

**Option B: Port forwarding**
- Forward port 8080 on your router to your server
- Use your public IP in TTN webhook config

**Option C: Cloud deployment**
- Deploy webhook listener to a VPS with public IP

---

## Step 6: Blockchain Integration

### 6.1 Register Gateway on Blockchain

```bash
cd ~/fabric-samples/test-network

# Set environment
export PATH="${PWD}/../bin:$PATH"
export FABRIC_CFG_PATH="${PWD}/../config/"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_MSPCONFIGPATH=${PWD}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
export CORE_PEER_ADDRESS=localhost:7051
export CORE_PEER_TLS_ROOTCERT_FILE=${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt

# Register gateway (replace GATEWAY_EUI with actual value)
peer chaincode invoke -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "${PWD}/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem" \
  -C lorawan-channel -n trustmanagement \
  --peerAddresses localhost:7051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt" \
  -c '{"function":"RegisterGateway","Args":["2CCF67FFFE6491D1","Org1","5.759","0.220","100"]}'
```

### 6.2 Update OrgResolver Mappings

Edit `webhook-listener/app/services/org_resolver.py` to map your actual device/gateway EUIs to organizations.

---

## Step 7: Verification Checklist

- [ ] Raspberry Pi gateway shows "Connected" in TTN Console
- [ ] ESP32 device joins network (EV_JOINED in Serial Monitor)
- [ ] Uplink messages appear in TTN Console → Live data
- [ ] Webhook listener receives events (`curl http://localhost:8080/stats`)
- [ ] Events stored in MySQL database
- [ ] Blockchain transactions recorded

### Test Commands

```bash
# Check webhook listener status
curl http://localhost:8080/stats

# Check MySQL for received events
docker exec lorawan-mysql mysql -uroot -prootpassword -D lorawan_events \
  -e "SELECT * FROM webhook_events ORDER BY id DESC LIMIT 5;"

# Query blockchain for gateway data
peer chaincode query -C lorawan-channel -n trustmanagement \
  -c '{"function":"GetGateway","Args":["YOUR_GATEWAY_EUI"]}'
```

---

## Troubleshooting

### Gateway Not Connecting

1. Check SPI is enabled: `ls /dev/spi*`
2. Verify RAK5146 is detected: `sudo i2cdetect -y 1`
3. Check Basics Station logs: `docker logs basicstation`
4. Ensure `tc.key` has correct API key from TTN
5. Verify frequency plan matches region

### Device Not Joining

1. Verify DevEUI/AppEUI/AppKey match TTN registration
2. Check byte order (LSB vs MSB) in firmware
3. Ensure gateway is receiving join requests (TTN live data)
4. Check antenna connections on both gateway and device
5. Verify device is within range of gateway

### Webhook Not Receiving Events

1. Verify webhook URL is accessible from internet
2. Check TTN webhook configuration (correct endpoints)
3. Test locally:
   ```bash
   curl -X POST http://localhost:8080/webhook/uplink \
     -H "Content-Type: application/json" \
     -d '{"end_device_ids":{"device_id":"test"}}'
   ```
4. Check webhook listener logs for errors
5. Verify firewall allows inbound connections on port 8080

### Serial Monitor Issues

1. Ensure correct baud rate: 115200
2. Reset ESP32 after opening serial monitor
3. Check USB cable supports data (not charge-only)

---

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| ESP32 Firmware | `devices/esp32/esp32_lorawan_otaa.ino` | End device code |
| PlatformIO Config | `devices/esp32/platformio.ini` | Build configuration |
| Gateway Config | `gateway/basicstation/station.conf` | Basics Station settings |
| TTN Endpoint | `gateway/basicstation/tc.uri` | LNS server URL |
| TTN API Key | `gateway/basicstation/tc.key` | Authentication |
| Setup Script | `gateway/setup-gateway.sh` | Raspberry Pi setup |

---

## References

- [RAK5146 Documentation](https://docs.rakwireless.com/Product-Categories/WisLink/RAK5146/)
- [Basics Station Documentation](https://doc.sm.tc/station/)
- [TTN Console](https://console.cloud.thethings.network/)
- [MCCI LMIC Library](https://github.com/mcci-catena/arduino-lmic)
- [ESP32 Arduino Core](https://github.com/espressif/arduino-esp32)
