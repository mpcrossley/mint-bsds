"""Tests for API client module."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from src.api_client import APIClient, Arrival, Stop, ArrivalsResponse


@pytest.fixture
def mock_config():
    """Mock configuration."""
    with patch("src.api_client.get_config") as mock:
        config = Mock()
        config.api_base_url = "http://test-api:8000"
        config.system_id = 1
        mock.return_value = config
        yield mock


@pytest.fixture
def client(mock_config):
    """Create an API client with mocked config."""
    return APIClient()


class TestAPIClient:
    """Tests for APIClient class."""

    def test_initialization(self, client):
        """Client should initialize with config values."""
        assert client.base_url == "http://test-api:8000"
        assert client.system_id == 1

    def test_get_stop(self, client):
        """Should parse stop response correctly."""
        mock_response = {
            "id": 123,
            "gtfs_stop_id": "STOP123",
            "stop_code": "12345",
            "stop_name": "Test Stop",
            "lat": 48.42,
            "lon": -123.36,
        }
        
        with patch.object(client, "_get", return_value=mock_response):
            stop = client.get_stop(123)
            
            assert isinstance(stop, Stop)
            assert stop.id == 123
            assert stop.stop_name == "Test Stop"
            assert stop.lat == 48.42

    def test_search_stops(self, client):
        """Should parse search results correctly."""
        mock_response = [
            {
                "id": 1,
                "gtfs_stop_id": "S1",
                "stop_code": "100",
                "stop_name": "Stop One",
                "lat": 48.0,
                "lon": -123.0,
            },
            {
                "id": 2,
                "gtfs_stop_id": "S2",
                "stop_code": "200",
                "stop_name": "Stop Two",
                "lat": 48.1,
                "lon": -123.1,
            },
        ]
        
        with patch.object(client, "_get", return_value=mock_response):
            stops = client.search_stops("stop")
            
            assert len(stops) == 2
            assert all(isinstance(s, Stop) for s in stops)
            assert stops[0].stop_name == "Stop One"

    def test_get_arrivals_success(self, client):
        """Should parse arrivals correctly from predictions API format."""
        mock_stop = {
            "id": 123,
            "gtfs_stop_id": "S123",
            "stop_code": "12345",
            "stop_name": "Test Stop",
            "lat": 48.42,
            "lon": -123.36,
        }
        
        # Predictions API format uses predicted_minutes and route_name
        mock_arrivals = {
            "stop_id": "S123",
            "stop_name": "Test Stop",
            "arrivals": [
                {
                    "vehicle_id": "V001",
                    "route_id": "10-VIC",
                    "route_name": "10",
                    "route_color": "FF5733",
                    "headsign": "Downtown",
                    "predicted_minutes": 5.0,
                    "predicted_seconds": 300,
                    "current_delay_minutes": 2.0,
                },
            ],
            "timestamp": "2025-12-06T09:30:00Z",
        }
        
        def mock_get(endpoint, params=None):
            if "arrivals" in endpoint:
                return mock_arrivals
            return mock_stop
        
        with patch.object(client, "_get", side_effect=mock_get):
            response = client.get_arrivals(123)
            
            assert isinstance(response, ArrivalsResponse)
            assert response.is_connected
            assert len(response.arrivals) == 1
            assert response.arrivals[0].route_short_name == "10"
            assert response.arrivals[0].minutes_away == 5
            assert response.arrivals[0].is_realtime == True

    def test_get_arrivals_handles_connection_error(self, client):
        """Should return disconnected status on error."""
        import requests
        
        with patch.object(client, "_get", side_effect=requests.RequestException("timeout")):
            response = client.get_arrivals(123)
            
            assert isinstance(response, ArrivalsResponse)
            assert not response.is_connected
            assert response.error is not None

    def test_get_arrivals_uses_predicted_minutes(self, client):
        """Should use predicted_minutes from predictions API."""
        mock_stop = {
            "id": 123,
            "gtfs_stop_id": "S123",
            "stop_code": "12345",
            "stop_name": "Test Stop",
            "lat": 48.42,
            "lon": -123.36,
        }
        
        mock_arrivals = {
            "arrivals": [
                {
                    "route_name": "14",
                    "headsign": "University",
                    "predicted_minutes": 12.5,
                    "predicted_seconds": 750,
                },
            ]
        }
        
        def mock_get(endpoint, params=None):
            if "arrivals" in endpoint:
                return mock_arrivals
            return mock_stop
        
        with patch.object(client, "_get", side_effect=mock_get):
            response = client.get_arrivals(123)
            
            # Should use predicted_minutes directly (truncated to int)
            assert response.arrivals[0].minutes_away == 12
            assert response.arrivals[0].is_realtime == True


class TestScheduleCache:
    """Tests for schedule caching functionality."""
    
    def test_cache_is_stale_when_missing(self, client):
        """Cache should be stale when file doesn't exist."""
        assert client._cache.is_stale(99999) == True
