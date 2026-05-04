/*******************************************************************************
 * ESP32 LoRaWAN OTAA Firmware for TTN EU868
 *
 * Project: LoRaWAN Blockchain Capstone
 * Hardware: ESP32 + SX1276/SX1278 LoRa Module
 * Network: The Things Network (EU868)
 *
 * Wiring (ESP32 + SX1276/SX1278):
 * SX1276 Pin | ESP32 Pin | Function
 * -----------|-----------|----------
 * VCC        | 3.3V      | Power
 * GND        | GND       | Ground
 * SCK        | GPIO18    | SPI Clock
 * MISO       | GPIO19    | SPI MISO
 * MOSI       | GPIO23    | SPI MOSI
 * NSS        | GPIO5     | SPI CS
 * RST        | GPIO14    | Reset
 * DIO0       | GPIO26    | Interrupt
 * DIO1       | GPIO33    | Interrupt
 *
 * Required Libraries:
 * - MCCI LoRaWAN LMIC library (via Arduino Library Manager)
 *
 * Configuration:
 * 1. Register device on TTN Console
 * 2. Copy DevEUI (LSB), AppEUI (LSB), AppKey (MSB) to credentials below
 * 3. Upload to ESP32
 ******************************************************************************/

#include <lmic.h>
#include <hal/hal.h>
#include <SPI.h>

// =============================================================================
// TTN DEVICE CREDENTIALS
// =============================================================================
// Get these from TTN Console -> Applications -> Your App -> End Devices -> Your Device
// IMPORTANT: DevEUI and AppEUI use LSB (Least Significant Byte first)
//            AppKey uses MSB (Most Significant Byte first)

// DevEUI (LSB format) - Example: If TTN shows 70B3D57ED0000001
// Convert to LSB: { 0x01, 0x00, 0x00, 0xD0, 0x7E, 0xD5, 0xB3, 0x70 }
static const u1_t PROGMEM DEVEUI[8] = {
    0x44, 0x5A, 0x07, 0xD0, 0x7E, 0xD5, 0xB3, 0x70  // <-- REPLACE WITH YOUR DevEUI (LSB)
};

// AppEUI (LSB format) - Also called JoinEUI in LoRaWAN 1.1
static const u1_t PROGMEM APPEUI[8] = {
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00  // <-- REPLACE WITH YOUR AppEUI (LSB)
};

// AppKey (MSB format) - 16 bytes
static const u1_t PROGMEM APPKEY[16] = {
   0x68, 0xF5, 0xE7, 0x53,
    0xD8, 0x54, 0x56, 0xF4,
    0x76, 0x75, 0x00, 0x81,
    0xFF, 0x4D, 0x5A, 0x6D  // <-- REPLACE WITH YOUR AppKey (MSB)
};


// Callback functions for LMIC
void os_getArtEui (u1_t* buf) { memcpy_P(buf, APPEUI, 8); }
void os_getDevEui (u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }
void os_getDevKey (u1_t* buf) { memcpy_P(buf, APPKEY, 16); }

// =============================================================================
// PIN MAPPING FOR ESP32 + SX1276/SX1278
// =============================================================================
const lmic_pinmap lmic_pins = {
    .nss = 5,                    // GPIO5  - Chip Select
    .rxtx = LMIC_UNUSED_PIN,     // Not used
    .rst = 14,                   // GPIO14 - Reset
    .dio = {26, 33, LMIC_UNUSED_PIN},  // DIO0=GPIO26, DIO1=GPIO33
};

// =============================================================================
// CONFIGURATION
// =============================================================================
static osjob_t sendjob;
const unsigned TX_INTERVAL = 60;  // Transmit interval in seconds
static uint32_t packetCount = 0;  // Packet counter for debugging

// Device state
bool joined = false;

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

// Convert event type to string for debugging
const char* getEventName(ev_t ev) {
    switch(ev) {
        case EV_SCAN_TIMEOUT:   return "SCAN_TIMEOUT";
        case EV_BEACON_FOUND:   return "BEACON_FOUND";
        case EV_BEACON_MISSED:  return "BEACON_MISSED";
        case EV_BEACON_TRACKED: return "BEACON_TRACKED";
        case EV_JOINING:        return "JOINING";
        case EV_JOINED:         return "JOINED";
        case EV_JOIN_FAILED:    return "JOIN_FAILED";
        case EV_REJOIN_FAILED:  return "REJOIN_FAILED";
        case EV_TXCOMPLETE:     return "TXCOMPLETE";
        case EV_LOST_TSYNC:     return "LOST_TSYNC";
        case EV_RESET:          return "RESET";
        case EV_RXCOMPLETE:     return "RXCOMPLETE";
        case EV_LINK_DEAD:      return "LINK_DEAD";
        case EV_LINK_ALIVE:     return "LINK_ALIVE";
        case EV_TXSTART:        return "TXSTART";
        case EV_TXCANCELED:     return "TXCANCELED";
        case EV_RXSTART:        return "RXSTART";
        case EV_JOIN_TXCOMPLETE:return "JOIN_TXCOMPLETE";
        default:                return "UNKNOWN";
    }
}

// Read simulated sensor data (replace with actual sensors)
float readTemperature() {
    // Simulate temperature between 20-30°C
    // Replace with actual sensor reading (e.g., DHT22, BME280)
    return 20.0 + (random(0, 100) / 10.0);
}

uint8_t readHumidity() {
    // Simulate humidity between 40-80%
    // Replace with actual sensor reading
    return 40 + random(0, 40);
}

uint16_t readBatteryVoltage() {
    // Read ESP32 ADC for battery monitoring (if connected)
    // Returns millivolts, e.g., 3300 = 3.3V
    // For testing, return simulated value
    return 3300 + random(-100, 100);
}

// =============================================================================
// LMIC EVENT HANDLER
// =============================================================================
void onEvent(ev_t ev) {
    Serial.print(os_getTime());
    Serial.print(": ");
    Serial.println(getEventName(ev));

    switch(ev) {
        case EV_JOINING:
            Serial.println(F("Starting OTAA join procedure..."));
            break;

        case EV_JOINED:
            Serial.println(F("OTAA Join successful!"));
            {
                u4_t netid = 0;
                devaddr_t devaddr = 0;
                u1_t nwkKey[16];
                u1_t artKey[16];
                LMIC_getSessionKeys(&netid, &devaddr, nwkKey, artKey);
                Serial.print(F("NetID: "));
                Serial.println(netid, HEX);
                Serial.print(F("DevAddr: "));
                Serial.println(devaddr, HEX);
            }
            joined = true;
            // Disable link check validation for faster operations
            LMIC_setLinkCheckMode(0);
            // Start sending data
            do_send(&sendjob);
            break;

        case EV_JOIN_FAILED:
            Serial.println(F("Join failed! Check credentials and gateway."));
            // Retry join after delay
            os_setTimedCallback(&sendjob, os_getTime() + sec2osticks(30), do_send);
            break;

        case EV_REJOIN_FAILED:
            Serial.println(F("Rejoin failed!"));
            break;

        case EV_TXCOMPLETE:
            Serial.println(F("Transmission complete"));
            packetCount++;
            Serial.print(F("Total packets sent: "));
            Serial.println(packetCount);

            // Check for downlink data
            if (LMIC.txrxFlags & TXRX_ACK) {
                Serial.println(F("Received ACK"));
            }
            if (LMIC.dataLen) {
                Serial.print(F("Received "));
                Serial.print(LMIC.dataLen);
                Serial.println(F(" bytes of downlink data:"));
                for (int i = 0; i < LMIC.dataLen; i++) {
                    Serial.print(LMIC.frame[LMIC.dataBeg + i], HEX);
                    Serial.print(" ");
                }
                Serial.println();
                // Process downlink commands here if needed
            }

            // Schedule next transmission
            os_setTimedCallback(&sendjob, os_getTime() + sec2osticks(TX_INTERVAL), do_send);
            break;

        case EV_TXSTART:
            Serial.println(F("Starting transmission..."));
            break;

        case EV_TXCANCELED:
            Serial.println(F("Transmission canceled"));
            break;

        case EV_RXSTART:
            // Do not print for less noise
            break;

        case EV_JOIN_TXCOMPLETE:
            Serial.println(F("Join request sent, waiting for response..."));
            break;

        default:
            Serial.print(F("Unhandled event: "));
            Serial.println((unsigned)ev);
            break;
    }
}

// =============================================================================
// SEND DATA FUNCTION
// =============================================================================
void do_send(osjob_t* j) {
    // Check if there is not a current TX/RX job running
    if (LMIC.opmode & OP_TXRXPEND) {
        Serial.println(F("OP_TXRXPEND, not sending"));
        return;
    }

    // If not joined yet, this will trigger join
    if (!joined) {
        Serial.println(F("Not joined yet, join will be triggered..."));
        return;
    }

    // ==========================================================================
    // PAYLOAD ENCODING
    // ==========================================================================
    // Payload format (8 bytes):
    // Byte 0-1: Temperature (int16, x100) - e.g., 2550 = 25.50°C
    // Byte 2:   Humidity (uint8, %)
    // Byte 3-4: Battery voltage (uint16, mV)
    // Byte 5-7: Reserved/Custom data

    uint8_t payload[8];

    // Temperature (multiply by 100 to preserve 2 decimal places)
    float temp = readTemperature();
    int16_t tempInt = (int16_t)(temp * 100);
    payload[0] = (tempInt >> 8) & 0xFF;  // High byte
    payload[1] = tempInt & 0xFF;          // Low byte

    // Humidity
    payload[2] = readHumidity();

    // Battery voltage (millivolts)
    uint16_t battery = readBatteryVoltage();
    payload[3] = (battery >> 8) & 0xFF;
    payload[4] = battery & 0xFF;

    // Packet counter (for debugging)
    payload[5] = (packetCount >> 8) & 0xFF;
    payload[6] = packetCount & 0xFF;

    // Status byte (bit flags)
    payload[7] = 0x00;  // Can add status flags here

    // Debug output
    Serial.println(F("--- Sending Uplink ---"));
    Serial.print(F("Temperature: ")); Serial.print(temp); Serial.println(F(" °C"));
    Serial.print(F("Humidity: ")); Serial.print(payload[2]); Serial.println(F(" %"));
    Serial.print(F("Battery: ")); Serial.print(battery); Serial.println(F(" mV"));
    Serial.print(F("Packet #: ")); Serial.println(packetCount);

    // Print raw payload
    Serial.print(F("Payload (hex): "));
    for (int i = 0; i < sizeof(payload); i++) {
        if (payload[i] < 0x10) Serial.print("0");
        Serial.print(payload[i], HEX);
        Serial.print(" ");
    }
    Serial.println();

    // Queue transmission on port 1 (unconfirmed)
    // Use port 2 for confirmed messages if needed
    LMIC_setTxData2(1, payload, sizeof(payload), 0);
    Serial.println(F("Packet queued for transmission"));
}

// =============================================================================
// SETUP
// =============================================================================
void setup() {
    // Initialize serial for debugging
    Serial.begin(115200);
    while (!Serial && millis() < 3000);  // Wait for serial (timeout after 3s)

    Serial.println(F("\n===================================="));
    Serial.println(F("LoRaWAN OTAA - Blockchain Capstone"));
    Serial.println(F("===================================="));
    Serial.println(F("Hardware: ESP32 + SX1276/SX1278"));
    Serial.println(F("Network: TTN EU868"));
    Serial.println();

    // Initialize random seed for simulated sensor data
    randomSeed(analogRead(0));

    // Initialize LMIC
    os_init();

    // Reset the MAC state
    LMIC_reset();

   

    // ==========================================================================
    // EU868 CHANNEL CONFIGURATION
    // ==========================================================================
    // TTN uses specific channels for EU868
    // These are the default 3 channels that all EU868 devices must support
 //   LMIC_setupChannel(0, 868100000, DR_RANGE_MAP(DR_SF12, DR_SF7), BAND_CENTI);
//    LMIC_setupChannel(1, 868300000, DR_RANGE_MAP(DR_SF12, DR_SF7B), BAND_CENTI);
  //  LMIC_setupChannel(2, 868500000, DR_RANGE_MAP(DR_SF12, DR_SF7), BAND_CENTI);

    // TTN adds these channels after join (handled automatically)
    // But we can pre-configure them:
//    LMIC_setupChannel(3, 867100000, DR_RANGE_MAP(DR_SF12, DR_SF7), BAND_CENTI);
 //   LMIC_setupChannel(4, 867300000, DR_RANGE_MAP(DR_SF12, DR_SF7), BAND_CENTI);
  //  LMIC_setupChannel(5, 867500000, DR_RANGE_MAP(DR_SF12, DR_SF7), BAND_CENTI);
   // LMIC_setupChannel(6, 867700000, DR_RANGE_MAP(DR_SF12, DR_SF7), BAND_CENTI);
   // LMIC_setupChannel(7, 867900000, DR_RANGE_MAP(DR_SF12, DR_SF7), BAND_CENTI);
    // Channel 8 is FSK (not commonly used)
 //   LMIC_setupChannel(8, 868800000, DR_RANGE_MAP(DR_FSK, DR_FSK), BAND_MILLI);

    // Disable link check validation for faster join
    LMIC_setLinkCheckMode(0);

    // TTN uses SF9 for RX2 window
    LMIC.dn2Dr = DR_SF9;

    // Set data rate and transmit power for uplink
    // Start with SF7 (fastest, shortest range)
    // Network will adjust via ADR if needed
    LMIC_setDrTxpow(DR_SF7, 14);

    // Enable Adaptive Data Rate (recommended for production)
    LMIC_setAdrMode(1);

    Serial.println(F("LMIC initialized, starting OTAA join..."));
    Serial.println();

    // Start join process - this triggers EV_JOINING event
    LMIC_startJoining();
}

// =============================================================================
// MAIN LOOP
// =============================================================================
void loop() {
    // LMIC scheduler handles all LoRaWAN operations
    os_runloop_once();
}

// =============================================================================
// TTN PAYLOAD DECODER (JavaScript - paste in TTN Console)
// =============================================================================
/*
// Paste this in TTN Console -> Applications -> Payload formatters -> Uplink

function decodeUplink(input) {
  var data = {};

  // Temperature (bytes 0-1, signed int16, /100)
  var tempRaw = (input.bytes[0] << 8) | input.bytes[1];
  if (tempRaw > 32767) tempRaw -= 65536;  // Handle signed
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
*/
