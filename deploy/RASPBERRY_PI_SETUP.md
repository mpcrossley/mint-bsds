# Raspberry Pi Setup for BSDS

This guide covers deploying BSDS on a Raspberry Pi Zero 2 with a Waveshare 7.5" V2 e-Paper display.

## Hardware Requirements

- Raspberry Pi Zero 2 (or any Pi with 40-pin GPIO)
- Waveshare 7.5" V2 e-Paper HAT
- MicroSD card with Raspberry Pi OS

## Quick Start

```bash
# 1. Enable SPI
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable
# Reboot when prompted

# 2. Install system dependencies
sudo apt update
sudo apt install -y python3-pip python3-pil python3-numpy git

# 3. Clone/copy BSDS to the Pi
git clone <your-repo> ~/bsds
cd ~/bsds

# 4. Install Python dependencies
pip install --break-system-packages omni-epd Pillow Flask requests python-dotenv

# 5. Run BSDS
python -m src.main
```

## Detailed Setup

### 1. Enable SPI Interface

The e-Paper display communicates via SPI. Enable it:

```bash
sudo raspi-config
```

Navigate to: **Interface Options** → **SPI** → **Yes** to enable.

Reboot to apply changes:
```bash
sudo reboot
```

### 2. Verify SPI is Working

After reboot, check that SPI devices are available:

```bash
ls /dev/spi*
```

You should see `/dev/spidev0.0` and `/dev/spidev0.1`.

### 3. Install Dependencies

```bash
sudo apt update
sudo apt install -y python3-pip python3-pil python3-numpy git

# Install the e-Paper driver (omni-epd is recommended)
pip install --break-system-packages omni-epd

# Install BSDS dependencies
cd ~/bsds
pip install --break-system-packages -r requirements.txt
```

### 4. Test the Display

Quick test to verify the display works:

```bash
cd ~/bsds
BSDS_MOCK_DISPLAY=0 python -c "
from src.display_driver import get_display_driver
from PIL import Image, ImageDraw

driver = get_display_driver()
img = Image.new('L', (800, 480), 255)
draw = ImageDraw.Draw(img)
draw.text((350, 220), 'BSDS Test', fill=0)
driver.display(img)
print('Display test complete!')
"
```

### 5. Run as a Service

Copy the systemd service file:

```bash
sudo cp ~/bsds/deploy/bsds.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bsds
sudo systemctl start bsds
```

Check status:
```bash
sudo systemctl status bsds
journalctl -u bsds -f  # View logs
```

## Configuration

### Display Model

Set the `BSDS_DISPLAY` environment variable if using a different display:

```bash
# Default is waveshare_epd.epd7in5_V2
export BSDS_DISPLAY="waveshare_epd.epd7in5_V2"
```

For the systemd service, add to `/etc/systemd/system/bsds.service`:
```ini
[Service]
Environment="BSDS_DISPLAY=waveshare_epd.epd7in5_V2"
```

### Available Displays

Common Waveshare models work with omni-epd:
- `waveshare_epd.epd7in5_V2` - 7.5" V2 (800x480)
- `waveshare_epd.epd2in13_V2` - 2.13" V2 (250x122)
- `waveshare_epd.epd4in2` - 4.2" (400x300)

See [omni-epd docs](https://github.com/robweber/omni-epd) for full list.

## Troubleshooting

### "Permission denied" on SPI

Add your user to the spi group:
```bash
sudo usermod -a -G spi $USER
# Log out and back in
```

### "No display driver found"

1. Verify SPI is enabled: `ls /dev/spi*`
2. Install omni-epd: `pip install --break-system-packages omni-epd`
3. Check wiring - ensure HAT is properly seated on GPIO pins

### Display shows nothing / stays white

1. Verify the correct display model in `BSDS_DISPLAY`
2. Check logs: `journalctl -u bsds -n 50`
3. Try running the test script above

### "Cannot allocate memory"

The Pi Zero has limited RAM. Close other applications or add swap:
```bash
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile  # Set CONF_SWAPSIZE=512
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## Web Interface

Once running, access the configuration web interface at:
```
http://<pi-ip-address>:5000
```

Configure your GTFS URL and stop ID through the web interface.
