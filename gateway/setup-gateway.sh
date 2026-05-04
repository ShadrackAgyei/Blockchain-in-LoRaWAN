#!/bin/bash
#
# Raspberry Pi 5 + RAK5146 Gateway Setup Script
# For LoRaWAN Blockchain Capstone Project
#
# This script sets up Basics Station for connecting to TTN EU868
#
# Usage:
#   1. Copy this script and basicstation/ folder to Raspberry Pi
#   2. Run: chmod +x setup-gateway.sh && ./setup-gateway.sh
#   3. Edit config files with your Gateway EUI and TTN API key
#   4. Run: ./start-gateway.sh
#

set -e

echo "=============================================="
echo "RAK5146 Gateway Setup for TTN (Basics Station)"
echo "=============================================="
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo "Warning: This script is designed for Raspberry Pi"
    echo "Continue anyway? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "[1/6] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "[2/6] Installing dependencies..."
sudo apt install -y git build-essential libsqlite3-dev

# Enable SPI interface
echo "[3/6] Enabling SPI interface..."
if ! grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=spi=on" | sudo tee -a /boot/config.txt > /dev/null || \
    echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt > /dev/null
    echo "SPI enabled. Reboot required."
fi

# Check for SPI device
if ls /dev/spi* 1> /dev/null 2>&1; then
    echo "SPI device found: $(ls /dev/spi*)"
else
    echo "Warning: No SPI device found. Please reboot and check SPI is enabled."
fi

# Install Docker (for containerized deployment)
echo "[4/6] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to log out and back in."
else
    echo "Docker already installed."
fi

# Clone Basics Station (for manual builds)
echo "[5/6] Cloning Basics Station repository..."
STATION_DIR="$HOME/basicstation"
if [ ! -d "$STATION_DIR" ]; then
    git clone https://github.com/lorabasics/basicstation.git "$STATION_DIR"
    echo "Basics Station cloned to $STATION_DIR"
else
    echo "Basics Station already exists at $STATION_DIR"
fi

# Create configuration directory
echo "[6/6] Setting up configuration..."
CONFIG_DIR="$HOME/gateway-config"
mkdir -p "$CONFIG_DIR"

# Copy configuration files if they exist in current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/basicstation" ]; then
    cp -r "$SCRIPT_DIR/basicstation/"* "$CONFIG_DIR/"
    echo "Configuration files copied to $CONFIG_DIR"
fi

# Create start script
cat > "$HOME/start-gateway.sh" << 'EOF'
#!/bin/bash
#
# Start Basics Station Gateway
#

CONFIG_DIR="$HOME/gateway-config"

# Check configuration files
if [ ! -f "$CONFIG_DIR/tc.uri" ]; then
    echo "Error: tc.uri not found. Please configure TTN endpoint."
    exit 1
fi

if [ ! -f "$CONFIG_DIR/tc.key" ]; then
    echo "Error: tc.key not found. Please add TTN API key."
    exit 1
fi

# Check if tc.key has placeholder
if grep -q "YOUR_TTN_API_KEY_HERE" "$CONFIG_DIR/tc.key"; then
    echo "Error: Please replace YOUR_TTN_API_KEY_HERE in tc.key with your actual TTN API key."
    echo "Get the key from TTN Console -> Gateways -> Your Gateway -> API Keys"
    exit 1
fi

echo "Starting Basics Station..."
echo "Config directory: $CONFIG_DIR"
echo "TTN Endpoint: $(cat $CONFIG_DIR/tc.uri)"
echo ""

# Run using Docker (recommended)
docker run --rm \
    --device /dev/spidev0.0 \
    --device /dev/gpiochip0 \
    -v "$CONFIG_DIR:/etc/basicstation" \
    --network host \
    --name basicstation \
    xoseperez/basicstation:latest

# Alternative: Run compiled binary
# cd ~/basicstation
# ./build/linux/x86_64/station -h "$CONFIG_DIR"
EOF

chmod +x "$HOME/start-gateway.sh"

# Create stop script
cat > "$HOME/stop-gateway.sh" << 'EOF'
#!/bin/bash
docker stop basicstation 2>/dev/null || echo "Gateway not running"
EOF
chmod +x "$HOME/stop-gateway.sh"

echo ""
echo "=============================================="
echo "Setup Complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Get your Gateway EUI:"
echo "   - Check RAK5146 label or run: sudo gateway-version"
echo ""
echo "2. Register gateway on TTN Console:"
echo "   - Go to https://console.cloud.thethings.network/"
echo "   - Select EU1 cluster"
echo "   - Gateways -> Register gateway"
echo "   - Enter Gateway EUI and frequency plan (EU868)"
echo ""
echo "3. Generate TTN API key:"
echo "   - Gateway settings -> API keys -> Add API key"
echo "   - Grant: 'Link as Gateway to a Gateway Server'"
echo "   - Copy the key"
echo ""
echo "4. Update configuration files:"
echo "   - Edit $CONFIG_DIR/station.conf"
echo "     Replace 'YOUR_GATEWAY_EUI' with actual EUI"
echo ""
echo "   - Edit $CONFIG_DIR/tc.key"
echo "     Replace 'YOUR_TTN_API_KEY_HERE' with actual API key"
echo ""
echo "5. Start the gateway:"
echo "   $HOME/start-gateway.sh"
echo ""
echo "6. Check TTN Console to verify gateway is connected"
echo ""
echo "Troubleshooting:"
echo "   - Check SPI: ls /dev/spi*"
echo "   - Check GPIO: ls /dev/gpiochip*"
echo "   - View logs: docker logs basicstation"
echo ""
