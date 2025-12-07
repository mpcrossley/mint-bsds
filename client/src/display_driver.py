"""
Display driver for Waveshare 7.5" e-Paper V2 HAT.

Provides abstraction over the hardware with mock mode for development.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Display dimensions for 7.5" V2
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480

# Check if we're in mock mode
MOCK_MODE = os.environ.get("BSDS_MOCK_DISPLAY", "0") == "1"


class DisplayDriver:
    """
    Driver for the Waveshare 7.5" e-Paper display.
    
    Supports multiple driver backends:
    - omni-epd (recommended, simpler API)
    - waveshare_epd (direct driver)
    - mock mode (for development without hardware)
    
    Set BSDS_DISPLAY env var to specify display model (default: waveshare_epd.epd7in5_V2)
    """
    
    def __init__(self, mock: bool = MOCK_MODE):
        self.mock = mock
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT
        self._epd = None
        self._use_omni = False  # Track which driver type we're using
        self._last_image: Optional[Image.Image] = None
        
        if not self.mock:
            self._init_hardware()
    
    def _init_hardware(self) -> None:
        """Initialize the e-paper hardware."""
        display_name = os.environ.get("BSDS_DISPLAY", "waveshare_epd.epd7in5_V2")
        
        # Try omni-epd first (simpler API, auto-detects display)
        try:
            from omni_epd import displayfactory
            
            logger.info(f"Initializing display via omni-epd: {display_name}")
            self._epd = displayfactory.load_display_driver(display_name)
            self._use_omni = True
            logger.info(f"E-Paper display initialized successfully (omni-epd, {self._epd.width}x{self._epd.height})")
            return
        except ImportError:
            logger.debug("omni-epd not available, trying direct driver")
        except Exception as e:
            logger.warning(f"omni-epd failed: {e}, trying direct driver")
        
        # Fall back to direct waveshare_epd driver
        try:
            from waveshare_epd import epd7in5_V2
            
            logger.info("Initializing display via waveshare_epd...")
            self._epd = epd7in5_V2.EPD()
            self._epd.init()
            self._use_omni = False
            logger.info("E-Paper display initialized successfully (waveshare_epd)")
            return
        except ImportError:
            logger.warning(
                "No display driver found. Install with: pip install omni-epd "
                "or clone https://github.com/waveshare/e-Paper"
            )
        except Exception as e:
            logger.error(f"Failed to initialize e-Paper display: {e}")
        
        # All drivers failed, enable mock mode
        self.mock = True
        logger.info("Falling back to mock display mode")
    
    def clear(self) -> None:
        """Clear the display to white."""
        if self.mock:
            logger.info("[MOCK] Clearing display")
            self._last_image = Image.new("L", (self.width, self.height), 255)
        elif self._use_omni:
            try:
                self._epd.prepare()
                # omni-epd clear via displaying white image
                white = Image.new("RGB", (self._epd.width, self._epd.height), (255, 255, 255))
                self._epd.display(white)
                logger.info("Display cleared (omni-epd)")
            except Exception as e:
                logger.error(f"Failed to clear display: {e}")
        else:
            try:
                self._epd.Clear()
                logger.info("Display cleared")
            except Exception as e:
                logger.error(f"Failed to clear display: {e}")
    
    def display(self, image: Image.Image) -> None:
        """
        Display an image on the e-paper screen.
        
        Args:
            image: PIL Image in grayscale (mode 'L') or RGB.
                   Will be converted and resized as needed.
        """
        # Ensure correct size
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)
        
        # Convert to grayscale if needed (for mock/preview)
        if image.mode != "L":
            grayscale = image.convert("L")
        else:
            grayscale = image
        
        self._last_image = grayscale
        
        if self.mock:
            logger.info("[MOCK] Displaying image")
            # Save to temp file for preview
            preview_path = Path(__file__).parent.parent / "preview.png"
            grayscale.save(preview_path)
            logger.info(f"[MOCK] Preview saved to {preview_path}")
        elif self._use_omni:
            try:
                logger.info("Updating e-Paper display (omni-epd)...")
                # omni-epd needs RGB and handles its own resizing
                rgb_image = image.convert("RGB") if image.mode != "RGB" else image
                rgb_image = rgb_image.resize((self._epd.width, self._epd.height))
                self._epd.prepare()
                self._epd.display(rgb_image)
                logger.info("Display updated successfully")
            except Exception as e:
                logger.error(f"Failed to update display: {e}")
        else:
            try:
                logger.info("Updating e-Paper display...")
                self._epd.display(self._epd.getbuffer(grayscale))
                logger.info("Display updated successfully")
            except Exception as e:
                logger.error(f"Failed to update display: {e}")
    
    def sleep(self) -> None:
        """Put the display into sleep mode to save power."""
        if self.mock:
            logger.info("[MOCK] Display entering sleep mode")
        elif self._use_omni:
            try:
                self._epd.close()
                logger.info("Display closed (omni-epd)")
            except Exception as e:
                logger.error(f"Failed to close display: {e}")
        else:
            try:
                self._epd.sleep()
                logger.info("Display entered sleep mode")
            except Exception as e:
                logger.error(f"Failed to sleep display: {e}")
    
    def wake(self) -> None:
        """Wake the display from sleep mode."""
        if self.mock:
            logger.info("[MOCK] Display waking up")
        else:
            self._init_hardware()
    
    def get_last_image(self) -> Optional[Image.Image]:
        """Get the last displayed image (useful for web preview)."""
        return self._last_image
    
    def get_preview_bytes(self) -> Optional[bytes]:
        """Get the last displayed image as PNG bytes."""
        if self._last_image is None:
            return None
        
        from io import BytesIO
        buffer = BytesIO()
        self._last_image.save(buffer, format="PNG")
        return buffer.getvalue()


# Global driver instance
_driver: Optional[DisplayDriver] = None


def get_display_driver() -> DisplayDriver:
    """Get the global display driver instance."""
    global _driver
    if _driver is None:
        _driver = DisplayDriver()
    return _driver
