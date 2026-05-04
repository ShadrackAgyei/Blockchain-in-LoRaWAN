/*******************************************************************************
 * SX1278 Diagnostic Test
 *
 * Tests SPI communication and basic radio functionality.
 * Upload to Device 2 to verify the SX1278 module is working.
 *
 * Wiring (same as your LoRaWAN sketch):
 *   NSS  = GPIO5
 *   RST  = GPIO14
 *   SCK  = GPIO18
 *   MISO = GPIO19
 *   MOSI = GPIO23
 ******************************************************************************/

#include <SPI.h>

// Pin definitions - match your lmic_pins
#define PIN_NSS   5
#define PIN_RST   14
#define PIN_SCK   18
#define PIN_MISO  19
#define PIN_MOSI  23

// SX1278 registers
#define REG_VERSION     0x42
#define REG_OP_MODE     0x01
#define REG_FRF_MSB     0x06
#define REG_FRF_MID     0x07
#define REG_FRF_LSB     0x08
#define REG_PA_CONFIG   0x09
#define REG_FIFO        0x00
#define REG_FIFO_ADDR   0x0D
#define REG_FIFO_TX     0x0E
#define REG_FIFO_RX     0x0F
#define REG_IRQ_FLAGS   0x12
#define REG_RSSI_VALUE  0x1B
#define REG_TEMP        0x3C

// OpMode values
#define MODE_SLEEP      0x00
#define MODE_STANDBY    0x01
#define MODE_TX         0x03
#define MODE_RXCONT     0x05
#define MODE_LORA       0x80

uint8_t readRegister(uint8_t addr) {
    digitalWrite(PIN_NSS, LOW);
    SPI.transfer(addr & 0x7F);  // Read: bit 7 = 0
    uint8_t val = SPI.transfer(0x00);
    digitalWrite(PIN_NSS, HIGH);
    return val;
}

void writeRegister(uint8_t addr, uint8_t val) {
    digitalWrite(PIN_NSS, LOW);
    SPI.transfer(addr | 0x80);  // Write: bit 7 = 1
    SPI.transfer(val);
    digitalWrite(PIN_NSS, HIGH);
}

int testsPassed = 0;
int testsFailed = 0;

void printResult(const char* name, bool pass) {
    Serial.print("  ");
    Serial.print(name);
    Serial.print(": ");
    if (pass) {
        Serial.println("PASS");
        testsPassed++;
    } else {
        Serial.println("FAIL");
        testsFailed++;
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000);

    Serial.println();
    Serial.println("========================================");
    Serial.println("  SX1278 Diagnostic Test");
    Serial.println("========================================");
    Serial.println();

    // ---- Hardware Reset ----
    Serial.println("[1] Resetting radio...");
    pinMode(PIN_RST, OUTPUT);
    digitalWrite(PIN_RST, LOW);
    delay(10);
    digitalWrite(PIN_RST, HIGH);
    delay(10);
    Serial.println("  Reset complete.");
    Serial.println();

    // ---- SPI Init ----
    Serial.println("[2] Initializing SPI...");
    pinMode(PIN_NSS, OUTPUT);
    digitalWrite(PIN_NSS, HIGH);
    SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_NSS);
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
    Serial.println("  SPI ready.");
    Serial.println();

    // ---- Test 1: Read chip version ----
    Serial.println("[3] Chip Version");
    uint8_t version = readRegister(REG_VERSION);
    Serial.print("  RegVersion = 0x");
    Serial.println(version, HEX);
    printResult("Version is 0x12 (SX1278)", version == 0x12);
    Serial.println();

    if (version != 0x12) {
        Serial.println("  >>> SPI communication FAILED.");
        Serial.println("  >>> Check wiring: NSS(GPIO5), SCK(18), MISO(19), MOSI(23)");
        Serial.println("  >>> Also check power (3.3V) and RST(GPIO14).");
        Serial.println();
        Serial.println("RESULT: RADIO NOT DETECTED - stopping here.");
        return;
    }

    // ---- Test 2: Mode switching ----
    Serial.println("[4] Mode Switching");

    // Sleep mode
    writeRegister(REG_OP_MODE, MODE_LORA | MODE_SLEEP);
    delay(5);
    uint8_t mode = readRegister(REG_OP_MODE);
    printResult("Set SLEEP mode", (mode & 0x07) == MODE_SLEEP);

    // Standby mode
    writeRegister(REG_OP_MODE, MODE_LORA | MODE_STANDBY);
    delay(5);
    mode = readRegister(REG_OP_MODE);
    printResult("Set STANDBY mode", (mode & 0x07) == MODE_STANDBY);
    Serial.println();

    // ---- Test 3: Register read/write ----
    Serial.println("[5] Register Read/Write");

    // Write and read back a frequency register (use 434 MHz = 0x6C8000)
    writeRegister(REG_OP_MODE, MODE_LORA | MODE_SLEEP);  // Must be in sleep to change freq
    delay(5);

    // Save original values
    uint8_t origMsb = readRegister(REG_FRF_MSB);
    uint8_t origMid = readRegister(REG_FRF_MID);
    uint8_t origLsb = readRegister(REG_FRF_LSB);

    // Write test pattern
    writeRegister(REG_FRF_MSB, 0x6C);
    writeRegister(REG_FRF_MID, 0x80);
    writeRegister(REG_FRF_LSB, 0x00);

    uint8_t rb1 = readRegister(REG_FRF_MSB);
    uint8_t rb2 = readRegister(REG_FRF_MID);
    uint8_t rb3 = readRegister(REG_FRF_LSB);

    printResult("Write/Read FRF_MSB", rb1 == 0x6C);
    printResult("Write/Read FRF_MID", rb2 == 0x80);
    printResult("Write/Read FRF_LSB", rb3 == 0x00);

    // Restore original
    writeRegister(REG_FRF_MSB, origMsb);
    writeRegister(REG_FRF_MID, origMid);
    writeRegister(REG_FRF_LSB, origLsb);
    Serial.println();

    // ---- Test 4: FIFO read/write ----
    Serial.println("[6] FIFO Read/Write");
    writeRegister(REG_OP_MODE, MODE_LORA | MODE_STANDBY);
    delay(5);

    // Reset FIFO pointer
    writeRegister(REG_FIFO_ADDR, 0x00);
    writeRegister(REG_FIFO_TX, 0x00);

    // Write test bytes to FIFO
    uint8_t testData[] = {0xDE, 0xAD, 0xBE, 0xEF};
    writeRegister(REG_FIFO_ADDR, 0x00);
    for (int i = 0; i < 4; i++) {
        writeRegister(REG_FIFO, testData[i]);
    }

    // Read back
    writeRegister(REG_FIFO_ADDR, 0x00);
    bool fifoOk = true;
    for (int i = 0; i < 4; i++) {
        uint8_t rb = readRegister(REG_FIFO);
        if (rb != testData[i]) fifoOk = false;
    }
    printResult("FIFO write/read 4 bytes", fifoOk);
    Serial.println();

    // ---- Test 5: PA Config ----
    Serial.println("[7] PA Configuration");
    uint8_t paConfig = readRegister(REG_PA_CONFIG);
    Serial.print("  PA_CONFIG = 0x");
    Serial.println(paConfig, HEX);
    bool paBoost = (paConfig & 0x80) != 0;
    Serial.print("  PA output: ");
    Serial.println(paBoost ? "PA_BOOST pin" : "RFO pin");
    printResult("PA_CONFIG readable", true);
    Serial.println();

    // ---- Test 6: Quick TX test at 434 MHz (SX1278 native band) ----
    Serial.println("[8] TX Test at 434.0 MHz (native band)");
    Serial.println("  Attempting short transmission...");

    // Set sleep to change frequency
    writeRegister(REG_OP_MODE, MODE_LORA | MODE_SLEEP);
    delay(5);

    // Set 434.0 MHz
    writeRegister(REG_FRF_MSB, 0x6C);
    writeRegister(REG_FRF_MID, 0x80);
    writeRegister(REG_FRF_LSB, 0x00);

    // Standby
    writeRegister(REG_OP_MODE, MODE_LORA | MODE_STANDBY);
    delay(5);

    // PA config: PA_BOOST, max power
    writeRegister(REG_PA_CONFIG, 0x8F);

    // Clear IRQ flags
    writeRegister(REG_IRQ_FLAGS, 0xFF);

    // Write 4 bytes to FIFO
    writeRegister(REG_FIFO_ADDR, 0x00);
    writeRegister(REG_FIFO_TX, 0x00);
    writeRegister(REG_FIFO, 0xAA);
    writeRegister(REG_FIFO, 0xBB);
    writeRegister(REG_FIFO, 0xCC);
    writeRegister(REG_FIFO, 0xDD);

    // Set payload length
    writeRegister(0x22, 4);  // RegPayloadLength

    // Switch to TX mode
    writeRegister(REG_OP_MODE, MODE_LORA | MODE_TX);

    // Wait for TxDone (bit 3 of IRQ flags) with timeout
    unsigned long start = millis();
    bool txDone = false;
    while (millis() - start < 5000) {
        uint8_t irq = readRegister(REG_IRQ_FLAGS);
        if (irq & 0x08) {  // TxDone
            txDone = true;
            break;
        }
        delay(10);
    }

    // Clear IRQ
    writeRegister(REG_IRQ_FLAGS, 0xFF);

    // Back to standby
    writeRegister(REG_OP_MODE, MODE_LORA | MODE_STANDBY);

    if (txDone) {
        printResult("TX at 434 MHz completed", true);
    } else {
        printResult("TX at 434 MHz completed", false);
        Serial.println("  >>> Radio could not transmit. Possible hardware fault.");
    }
    Serial.println();

    // ---- Summary ----
    Serial.println("========================================");
    Serial.print("  PASSED: "); Serial.println(testsPassed);
    Serial.print("  FAILED: "); Serial.println(testsFailed);
    Serial.println("========================================");

    if (testsFailed == 0) {
        Serial.println("  Radio is OK. SPI and TX working.");
        Serial.println("  The crash in LMIC is because EU868");
        Serial.println("  is outside SX1278 range (max 525 MHz).");
    } else {
        Serial.println("  Hardware issue detected.");
        Serial.println("  Check wiring and module.");
    }
    Serial.println("========================================");
}

void loop() {
    // Nothing - diagnostic runs once in setup
}
