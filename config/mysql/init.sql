-- Initialize LoRaWAN events database

-- Create webhook_events table
CREATE TABLE IF NOT EXISTS webhook_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    dev_eui VARCHAR(20) NOT NULL,
    gateway_eui VARCHAR(20),
    rssi FLOAT,
    snr FLOAT,
    timestamp DATETIME NOT NULL,
    raw_payload TEXT,
    processed BOOLEAN DEFAULT FALSE,
    blockchain_tx_id VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event_type (event_type),
    INDEX idx_dev_eui (dev_eui),
    INDEX idx_gateway_eui (gateway_eui),
    INDEX idx_timestamp (timestamp),
    INDEX idx_processed (processed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create forwarding_batches table
CREATE TABLE IF NOT EXISTS forwarding_batches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    gateway_eui VARCHAR(20) NOT NULL,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    uplink_count INT DEFAULT 0,
    downlink_count INT DEFAULT 0,
    join_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    avg_rssi FLOAT,
    avg_snr FLOAT,
    blockchain_tx_id VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_gateway_eui (gateway_eui),
    INDEX idx_period (period_start, period_end)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create billing_charges table
CREATE TABLE IF NOT EXISTS billing_charges (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dev_eui VARCHAR(20) NOT NULL,
    gateway_eui VARCHAR(20) NOT NULL,
    gateway_owner_org VARCHAR(100) NOT NULL,
    device_owner_org VARCHAR(100) NOT NULL,
    packet_type VARCHAR(20) NOT NULL,
    packet_count INT DEFAULT 1,
    blockchain_tx_id VARCHAR(100),
    timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dev_eui (dev_eui),
    INDEX idx_gateway_eui (gateway_eui),
    INDEX idx_orgs (gateway_owner_org, device_owner_org),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create view for charge summary by organization pair
CREATE OR REPLACE VIEW charge_summary AS
SELECT
    device_owner_org,
    gateway_owner_org,
    packet_type,
    SUM(packet_count) as total_packets,
    COUNT(*) as charge_count,
    MIN(timestamp) as first_charge,
    MAX(timestamp) as last_charge
FROM billing_charges
GROUP BY device_owner_org, gateway_owner_org, packet_type;

-- Create view for daily gateway statistics
CREATE OR REPLACE VIEW daily_gateway_stats AS
SELECT
    gateway_eui,
    DATE(period_start) as stat_date,
    SUM(uplink_count) as total_uplinks,
    SUM(downlink_count) as total_downlinks,
    SUM(join_count) as total_joins,
    SUM(error_count) as total_errors,
    AVG(avg_rssi) as avg_rssi,
    AVG(avg_snr) as avg_snr
FROM forwarding_batches
GROUP BY gateway_eui, DATE(period_start);
