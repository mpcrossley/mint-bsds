"""
Device provisioning - QR code pairing and server communication.

Handles the first-boot pairing flow:
1. Generate claim code
2. Display QR code on e-ink
3. Poll server until paired
4. Download configuration and GTFS data
"""
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Config file location
CONFIG_FILE = Path(os.getenv("BSDS_CONFIG_PATH", "config.json"))
DEVICE_FILE = Path("device.json")  # Stores device identity


def generate_claim_code() -> str:
    """Generate a 6-character alphanumeric claim code."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def get_serial_number() -> Optional[str]:
    """Get Raspberry Pi serial number."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("Serial"):
                    return line.split(":")[1].strip()
    except Exception:
        pass
    return None


def load_device_identity() -> dict:
    """Load or create device identity."""
    if DEVICE_FILE.exists():
        with open(DEVICE_FILE) as f:
            return json.load(f)
    
    # First boot - generate new identity
    identity = {
        "claim_code": generate_claim_code(),
        "serial_number": get_serial_number(),
        "api_token": None,
        "stop_code": None,
        "stop_name": None,
    }
    
    save_device_identity(identity)
    return identity


def save_device_identity(identity: dict):
    """Save device identity to disk."""
    with open(DEVICE_FILE, "w") as f:
        json.dump(identity, f, indent=2)


class ProvisioningClient:
    """Handles communication with BSDS server for provisioning."""
    
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")
        self._session = None
    
    def _get_session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session
    
    def register(self, claim_code: str, serial_number: Optional[str] = None) -> dict:
        """Register device with server."""
        response = self._get_session().post(
            f"{self.server_url}/api/devices/register",
            json={
                "claim_code": claim_code,
                "serial_number": serial_number,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    
    def get_status(self, claim_code: str) -> dict:
        """Poll for pairing status."""
        response = self._get_session().get(
            f"{self.server_url}/api/devices/status",
            params={"claim_code": claim_code},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    
    def download_gtfs(self, stop_code: str, api_token: str) -> bytes:
        """Download pruned GTFS data for assigned stop."""
        response = self._get_session().get(
            f"{self.server_url}/api/gtfs/light/{stop_code}",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=60,
        )
        response.raise_for_status()
        return response.content
    
    def heartbeat(self, api_token: str, software_version: Optional[str] = None) -> dict:
        """Send heartbeat to server."""
        response = self._get_session().post(
            f"{self.server_url}/api/devices/heartbeat",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"software_version": software_version},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


def render_pairing_screen(display_driver, claim_code: str, server_url: str):
    """Render pairing screen with QR code on e-ink display."""
    from PIL import Image, ImageDraw, ImageFont
    
    # Create image matching display size
    width = display_driver.width
    height = display_driver.height
    image = Image.new("L", (width, height), 255)  # White background
    draw = ImageDraw.Draw(image)
    
    # Try to generate QR code
    qr_image = None
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(f"{server_url}/pair?code={claim_code}")
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")
        qr_image = qr_image.resize((200, 200))
    except ImportError:
        logger.warning("qrcode library not installed, skipping QR code")
    
    # Load fonts
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_code = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 48)
    except Exception:
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_code = font_large
    
    # Draw title
    draw.text((width // 2, 40), "Pair This Device", font=font_large, fill=0, anchor="mm")
    
    # Draw QR code
    if qr_image:
        qr_x = (width - 200) // 2
        image.paste(qr_image, (qr_x, 80))
    
    # Draw claim code
    code_y = 300 if qr_image else 150
    draw.text((width // 2, code_y), "Code:", font=font_medium, fill=0, anchor="mm")
    draw.text((width // 2, code_y + 50), claim_code, font=font_code, fill=0, anchor="mm")
    
    # Draw server URL
    draw.text((width // 2, height - 40), server_url, font=font_medium, fill=128, anchor="mm")
    
    # Display
    display_driver.display(image)


def run_provisioning(server_url: str, display_driver) -> Tuple[str, str, str]:
    """
    Run the provisioning flow.
    
    Returns (stop_code, stop_name, api_token) when paired.
    """
    identity = load_device_identity()
    claim_code = identity["claim_code"]
    
    # Check if already paired
    if identity.get("api_token") and identity.get("stop_code"):
        logger.info("Device already paired")
        return identity["stop_code"], identity["stop_name"], identity["api_token"]
    
    logger.info(f"Starting provisioning with claim code: {claim_code}")
    
    client = ProvisioningClient(server_url)
    
    # Register with server
    try:
        client.register(claim_code, identity.get("serial_number"))
    except Exception as e:
        logger.error(f"Failed to register: {e}")
    
    # Display pairing screen
    render_pairing_screen(display_driver, claim_code, server_url)
    
    # Poll until paired
    poll_interval = 10
    while True:
        try:
            status = client.get_status(claim_code)
            
            if status["status"] in ("paired", "active"):
                # Save identity
                identity["api_token"] = status["api_token"]
                identity["stop_code"] = status["stop_code"]
                identity["stop_name"] = status["stop_name"]
                save_device_identity(identity)
                
                logger.info(f"Paired to stop: {status['stop_name']}")
                return status["stop_code"], status["stop_name"], status["api_token"]
            
            poll_interval = status.get("poll_interval", 10)
            
        except Exception as e:
            logger.warning(f"Polling failed: {e}")
        
        time.sleep(poll_interval)
