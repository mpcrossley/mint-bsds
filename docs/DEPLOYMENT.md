# BSDS Deployment Guide

Complete guide for deploying BSDS on a Raspberry Pi with a Waveshare e-ink display.

## Hardware Requirements

| Component | Recommended |
|-----------|-------------|
| Raspberry Pi | 3B+, 4, or Zero 2 W |
| Display | Waveshare 7.5" e-Paper HAT V2 (800×480) |
| Storage | 16GB+ MicroSD card |
| Power | 5V 2.5A power supply |

## Quick Deploy (Offline)

For air-gapped deployments, all dependencies are bundled:

```bash
# 1. Copy the bsds folder to the Pi
scp -r bsds/ pi@raspberrypi:~/

# 2. SSH into the Pi
ssh pi@raspberrypi

# 3. Create virtual environment
cd ~/bsds
python3 -m venv venv
source venv/bin/activate

# 4. Install from local wheels (offline)
pip install --no-index --find-links=packages/wheels -r requirements.txt

# 5. Install local packages
pip install packages/omni-epd/
pip install packages/e-Paper/RaspberryPi_JetsonNano/python/

# 6. Run in mock mode to test
python -m src.main --mock
```

## Systemd Service

Run BSDS automatically on boot:

```bash
# Create service file
sudo tee /etc/systemd/system/bsds.service << 'EOF'
[Unit]
Description=Bus Stop Display System
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/bsds
Environment=PATH=/home/pi/bsds/venv/bin
ExecStart=/home/pi/bsds/venv/bin/python -m src.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable bsds
sudo systemctl start bsds
```

## SPI Configuration

Enable SPI for the e-ink display:

```bash
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable

# Verify
ls /dev/spidev*
# Should show: /dev/spidev0.0  /dev/spidev0.1
```

## Pre-Processing GTFS Data

For faster startup, pre-process and prune GTFS data on a more powerful machine:

```bash
# On your development machine
python -m src.process_gtfs

# This creates a pruned gtfs_data.pkl cache
# Copy this to the Pi along with config.json
```

## Troubleshooting

### Display not updating
```bash
# Check service status
sudo systemctl status bsds

# View logs
journalctl -u bsds -f
```

### SPI Permission denied
```bash
sudo usermod -a -G spi,gpio pi
# Logout and login again
```

### Web interface not accessible
- Check firewall: `sudo ufw allow 5000`
- Verify IP: `hostname -I`
