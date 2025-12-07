"""Tests for renderer module."""

import pytest
from datetime import datetime
from PIL import Image

from src.api_client import Arrival, ArrivalsResponse, Stop
from src.renderer import Renderer, DISPLAY_WIDTH, DISPLAY_HEIGHT


@pytest.fixture
def renderer():
    """Create a renderer instance."""
    return Renderer()


@pytest.fixture
def sample_stop():
    """Create a sample stop."""
    return Stop(
        id=123,
        gtfs_stop_id="STOP123",
        stop_code="12345",
        stop_name="Douglas St at Cloverdale Ave",
        lat=48.42,
        lon=-123.36,
    )


@pytest.fixture
def sample_arrivals(sample_stop):
    """Create sample arrival data."""
    return ArrivalsResponse(
        stop=sample_stop,
        arrivals=[
            Arrival(
                route_short_name="10",
                route_color="FF5733",
                headsign="Downtown",
                scheduled_time="2025-12-06T09:30:00",
                predicted_time="2025-12-06T09:32:00",
                minutes_away=5,
                is_realtime=True,
                delay_seconds=120,
            ),
            Arrival(
                route_short_name="14",
                route_color="3366FF",
                headsign="University",
                scheduled_time="2025-12-06T09:45:00",
                predicted_time=None,
                minutes_away=20,
                is_realtime=False,
            ),
        ],
        timestamp=datetime(2025, 12, 6, 9, 27, 0),
        is_connected=True,
    )


class TestRenderer:
    """Tests for Renderer class."""

    def test_render_returns_correct_size(self, renderer, sample_arrivals):
        """Rendered image should have correct dimensions."""
        image = renderer.render(sample_arrivals)
        
        assert isinstance(image, Image.Image)
        assert image.size == (DISPLAY_WIDTH, DISPLAY_HEIGHT)
        assert image.mode == "L"  # Grayscale

    def test_render_placeholder(self, renderer):
        """Placeholder should render without errors."""
        image = renderer.render_placeholder("No stop configured")
        
        assert isinstance(image, Image.Image)
        assert image.size == (DISPLAY_WIDTH, DISPLAY_HEIGHT)

    def test_render_with_no_arrivals(self, renderer, sample_stop):
        """Should handle empty arrivals list."""
        response = ArrivalsResponse(
            stop=sample_stop,
            arrivals=[],
            timestamp=datetime.now(),
            is_connected=True,
        )
        
        image = renderer.render(response)
        assert isinstance(image, Image.Image)

    def test_render_with_disconnected_status(self, renderer, sample_stop):
        """Should show error banner when disconnected."""
        response = ArrivalsResponse(
            stop=sample_stop,
            arrivals=[],
            timestamp=datetime.now(),
            is_connected=False,
            error="Connection timeout",
        )
        
        image = renderer.render(response)
        assert isinstance(image, Image.Image)

    def test_truncate_text(self, renderer):
        """Text truncation should work correctly."""
        from PIL import ImageDraw, ImageFont
        
        img = Image.new("L", (100, 100))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        
        # Long text should be truncated
        long_text = "This is a very long stop name that should be truncated"
        truncated = renderer._truncate_text(draw, long_text, font, 100)
        
        assert len(truncated) < len(long_text)
        assert truncated.endswith("...")

    def test_render_many_arrivals(self, renderer, sample_stop):
        """Should handle many arrivals (more than display can show)."""
        arrivals = [
            Arrival(
                route_short_name=str(i),
                route_color="000000",
                headsign=f"Destination {i}",
                scheduled_time="2025-12-06T09:30:00",
                predicted_time=None,
                minutes_away=i * 5,
                is_realtime=False,
            )
            for i in range(20)
        ]
        
        response = ArrivalsResponse(
            stop=sample_stop,
            arrivals=arrivals,
            timestamp=datetime.now(),
            is_connected=True,
        )
        
        # Should not raise, should only show max_arrivals
        image = renderer.render(response)
        assert isinstance(image, Image.Image)
