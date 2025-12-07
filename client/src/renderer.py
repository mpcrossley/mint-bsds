"""
Rendering engine for the bus stop display.

Uses Pillow to generate images matching the reference design.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .api_client import Arrival, ArrivalsResponse
from .config import get_config
from .display_driver import DISPLAY_WIDTH, DISPLAY_HEIGHT

logger = logging.getLogger(__name__)

# Layout constants
HEADER_HEIGHT = 60
ROW_HEIGHT = 52
COLUMN_WIDTHS = {
    "route": 100,
    "destination": 320,
    "time": 120,
    "status": 120,
}
PADDING = 12

# Colors (grayscale values)
WHITE = 255
BLACK = 0
GRAY = 128
LIGHT_GRAY = 200


class Renderer:
    """Renders arrival information to display-ready images."""
    
    def __init__(self):
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT
        self._fonts = self._load_fonts()
    
    def _load_fonts(self) -> dict:
        """Load fonts for rendering."""
        fonts_dir = Path(__file__).parent.parent / "assets" / "fonts"
        
        fonts = {}
        
        # Try to load Inter fonts
        regular_path = fonts_dir / "Inter-Regular.ttf"
        bold_path = fonts_dir / "Inter-Bold.ttf"
        
        try:
            if regular_path.exists():
                fonts["header"] = ImageFont.truetype(str(bold_path), 32)
                fonts["route"] = ImageFont.truetype(str(bold_path), 42)
                fonts["destination"] = ImageFont.truetype(str(regular_path), 28)
                fonts["time"] = ImageFont.truetype(str(bold_path), 40)
                fonts["time_unit"] = ImageFont.truetype(str(regular_path), 20)
                fonts["status"] = ImageFont.truetype(str(regular_path), 18)
                fonts["column_header"] = ImageFont.truetype(str(regular_path), 18)
                logger.info("Loaded Inter fonts")
            else:
                raise FileNotFoundError("Inter fonts not found")
        except Exception as e:
            logger.warning(f"Could not load custom fonts: {e}. Using defaults.")
            # Fallback to default fonts
            fonts["header"] = ImageFont.load_default()
            fonts["route"] = ImageFont.load_default()
            fonts["destination"] = ImageFont.load_default()
            fonts["time"] = ImageFont.load_default()
            fonts["time_unit"] = ImageFont.load_default()
            fonts["status"] = ImageFont.load_default()
            fonts["column_header"] = ImageFont.load_default()
        
        return fonts
    
    def _truncate_text(self, draw: ImageDraw.ImageDraw, text: str, 
                       font: ImageFont.FreeTypeFont, max_width: int) -> str:
        """Truncate text to fit within max_width, adding ellipsis if needed."""
        if draw.textlength(text, font=font) <= max_width:
            return text
        
        ellipsis = "..."
        while len(text) > 0:
            text = text[:-1]
            if draw.textlength(text + ellipsis, font=font) <= max_width:
                return text + ellipsis
        
        return ellipsis
    
    def render(self, data: ArrivalsResponse) -> Image.Image:
        """
        Render arrival data to a display image.
        
        Args:
            data: ArrivalsResponse containing stop and arrival information.
        
        Returns:
            PIL Image ready for display (grayscale, 800x480).
        """
        # Create image
        img = Image.new("L", (self.width, self.height), WHITE)
        draw = ImageDraw.Draw(img)
        
        # Draw header
        self._draw_header(draw, data.stop.stop_name, data.timestamp)
        
        # Draw column headers
        self._draw_column_headers(draw)
        
        # Draw arrivals
        config = get_config()
        max_arrivals = min(config.display.max_arrivals, len(data.arrivals))
        
        y = HEADER_HEIGHT + 40  # After column headers
        for i, arrival in enumerate(data.arrivals[:max_arrivals]):
            self._draw_arrival_row(draw, arrival, y, i % 2 == 1)
            y += ROW_HEIGHT
        
        # Draw connection status if disconnected or using cached data
        if not data.is_connected:
            if data.is_cached:
                self._draw_info_banner(draw, "Using cached schedule (offline)")
            else:
                self._draw_error_banner(draw, "No connection to server")
        
        return img
    
    def _draw_header(self, draw: ImageDraw.ImageDraw, 
                     stop_name: str, timestamp: datetime) -> None:
        """Draw the header with stop name and time."""
        # Background
        draw.rectangle([(0, 0), (self.width, HEADER_HEIGHT)], fill=BLACK)
        
        # Stop name (left side)
        name = self._truncate_text(draw, stop_name, self._fonts["header"], 
                                   self.width - 180)
        draw.text((PADDING, 14), name, font=self._fonts["header"], fill=WHITE)
        
        # Time (right side)
        time_str = f"Time {timestamp.strftime('%H:%M')}"
        time_width = draw.textlength(time_str, font=self._fonts["header"])
        draw.text((self.width - time_width - PADDING, 14), time_str, 
                  font=self._fonts["header"], fill=WHITE)
    
    def _draw_column_headers(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw column headers."""
        y = HEADER_HEIGHT + 10
        x = PADDING
        
        headers = [
            ("Next Bus", COLUMN_WIDTHS["route"]),
            ("Travelling to", COLUMN_WIDTHS["destination"]),
            ("Departing", COLUMN_WIDTHS["time"]),
            ("Status", COLUMN_WIDTHS["status"]),
        ]
        
        for header, width in headers:
            draw.text((x, y), header, font=self._fonts["column_header"], fill=GRAY)
            x += width + PADDING
        
        # Separator line
        draw.line([(0, HEADER_HEIGHT + 35), (self.width, HEADER_HEIGHT + 35)], 
                  fill=LIGHT_GRAY, width=1)
    
    def _draw_arrival_row(self, draw: ImageDraw.ImageDraw, 
                          arrival: Arrival, y: int, alternate: bool) -> None:
        """Draw a single arrival row."""
        # Alternate row background
        if alternate:
            draw.rectangle(
                [(0, y), (self.width, y + ROW_HEIGHT)], 
                fill=245  # Very light gray
            )
        
        x = PADDING
        row_center = y + ROW_HEIGHT // 2
        
        # Route number (large, bold)
        route_text = arrival.route_short_name
        draw.text((x, row_center - 21), route_text, 
                  font=self._fonts["route"], fill=BLACK)
        x += COLUMN_WIDTHS["route"] + PADDING
        
        # Destination (headsign)
        dest = self._truncate_text(draw, arrival.headsign, 
                                   self._fonts["destination"], 
                                   COLUMN_WIDTHS["destination"])
        draw.text((x, row_center - 14), dest, 
                  font=self._fonts["destination"], fill=BLACK)
        x += COLUMN_WIDTHS["destination"] + PADDING
        
        # Time (minutes away - large)
        if arrival.minutes_away == 0:
            time_text = "Now"
        else:
            time_text = str(arrival.minutes_away)
        
        draw.text((x, row_center - 20), time_text, 
                  font=self._fonts["time"], fill=BLACK)
        
        # Add "min" label
        if arrival.minutes_away > 0:
            time_width = draw.textlength(time_text, font=self._fonts["time"])
            draw.text((x + time_width + 4, row_center - 8), "min", 
                      font=self._fonts["time_unit"], fill=GRAY)
        
        x += COLUMN_WIDTHS["time"] + PADDING
        
        # Status icon (radio waves for real-time, clock for scheduled)
        icon_x = x + 20
        icon_y = row_center - 12
        if arrival.is_realtime:
            self._draw_radio_waves_icon(draw, icon_x, icon_y)
        else:
            self._draw_clock_icon(draw, icon_x, icon_y)
    
    def _draw_radio_waves_icon(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        """Draw radio waves icon for real-time arrivals."""
        # Draw concentric arcs representing radio waves
        size = 24
        center_x = x + 6
        center_y = y + size // 2
        
        # Small dot in center
        draw.ellipse([(center_x - 3, center_y - 3), (center_x + 3, center_y + 3)], fill=GRAY)
        
        # Radio waves (arcs) - draw as partial circles
        for i, radius in enumerate([8, 14, 20]):
            # Draw arc from -45 to 45 degrees (upper right quadrant)
            draw.arc(
                [(center_x - radius, center_y - radius), 
                 (center_x + radius, center_y + radius)],
                start=-60, end=60,
                fill=GRAY, width=2
            )
    
    def _draw_clock_icon(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        """Draw clock icon for scheduled arrivals."""
        size = 22
        center_x = x + size // 2
        center_y = y + size // 2
        
        # Clock face (circle)
        draw.ellipse(
            [(x, y), (x + size, y + size)],
            outline=GRAY, width=2
        )
        
        # Hour hand (pointing to 10)
        draw.line(
            [(center_x, center_y), (center_x - 4, center_y - 6)],
            fill=GRAY, width=2
        )
        
        # Minute hand (pointing to 2) 
        draw.line(
            [(center_x, center_y), (center_x + 6, center_y - 3)],
            fill=GRAY, width=2
        )
    
    def _draw_error_banner(self, draw: ImageDraw.ImageDraw, message: str) -> None:
        """Draw an error banner at the bottom of the screen."""
        banner_height = 40
        y = self.height - banner_height
        
        draw.rectangle([(0, y), (self.width, self.height)], fill=GRAY)
        
        text_width = draw.textlength(message, font=self._fonts["header"])
        draw.text(((self.width - text_width) // 2, y + 8), message, 
                  font=self._fonts["header"], fill=WHITE)
    
    def _draw_info_banner(self, draw: ImageDraw.ImageDraw, message: str) -> None:
        """Draw an info banner at the bottom of the screen (for cached data)."""
        banner_height = 30
        y = self.height - banner_height
        
        # Lighter background for info (not error)
        draw.rectangle([(0, y), (self.width, self.height)], fill=LIGHT_GRAY)
        
        text_width = draw.textlength(message, font=self._fonts["column_header"])
        draw.text(((self.width - text_width) // 2, y + 7), message, 
                  font=self._fonts["column_header"], fill=GRAY)
    
    def render_placeholder(self, message: str = "No stop selected") -> Image.Image:
        """Render a placeholder screen."""
        img = Image.new("L", (self.width, self.height), WHITE)
        draw = ImageDraw.Draw(img)
        
        # Draw message centered
        text_width = draw.textlength(message, font=self._fonts["header"])
        x = (self.width - text_width) // 2
        y = self.height // 2 - 12
        
        draw.text((x, y), message, font=self._fonts["header"], fill=GRAY)
        
        # Draw setup instructions
        setup_msg = "Configure via web interface at port 5000"
        setup_width = draw.textlength(setup_msg, font=self._fonts["column_header"])
        draw.text(((self.width - setup_width) // 2, y + 40), setup_msg, 
                  font=self._fonts["column_header"], fill=GRAY)
        
        return img


# Global renderer instance
_renderer: Optional[Renderer] = None


def get_renderer() -> Renderer:
    """Get the global renderer instance."""
    global _renderer
    if _renderer is None:
        _renderer = Renderer()
    return _renderer
