"""Tests for config module."""

import json
import tempfile
from pathlib import Path

import pytest

from src.config import Config, ConfigManager, DisplayConfig, PowerConfig, DataSourceConfig


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        config = Config()
        
        # New structure: data_source contains API settings
        assert config.data_source.mode == "gtfs"
        assert config.data_source.mint_api_url == "http://localhost:8000"
        assert config.data_source.mint_system_id == 1
        assert config.stop_id is None
        assert config.refresh_interval_seconds == 30
        assert config.display.max_arrivals == 8  # Updated default
        assert config.power.quiet_hours_start is None

    def test_to_dict(self):
        """Config should convert to dictionary."""
        config = Config(stop_id="123", stop_name="Test Stop")
        data = config.to_dict()
        
        assert data["stop_id"] == "123"
        assert data["stop_name"] == "Test Stop"
        assert "display" in data
        assert "power" in data
        assert "data_source" in data

    def test_from_dict(self):
        """Config should be created from dictionary."""
        data = {
            "stop_id": "456",
            "stop_name": "Main St",
            "refresh_interval_seconds": 60,
            "display": {"orientation": 180, "max_arrivals": 8},
            "power": {"quiet_hours_start": "23:00", "quiet_hours_end": "06:00"},
            "data_source": {
                "mode": "mint",
                "mint_api_url": "http://api.example.com",
                "mint_system_id": 2,
            },
        }
        
        config = Config.from_dict(data)
        
        assert config.data_source.mint_api_url == "http://api.example.com"
        assert config.data_source.mint_system_id == 2
        assert config.stop_id == "456"
        assert config.display.orientation == 180
        assert config.power.quiet_hours_start == "23:00"


class TestConfigManager:
    """Tests for ConfigManager."""

    def test_load_creates_default_when_no_file(self):
        """Should create default config when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager(Path(tmpdir) / "config.json")
            config = manager.load()
            
            assert config.data_source.mode == "gtfs"

    def test_save_and_load(self):
        """Should persist config to file and reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            manager = ConfigManager(config_path)
            
            # Modify and save
            manager.config.stop_id = "789"
            manager.config.stop_name = "Saved Stop"
            manager.save()
            
            # Load with new manager
            manager2 = ConfigManager(config_path)
            loaded = manager2.load()
            
            assert loaded.stop_id == "789"
            assert loaded.stop_name == "Saved Stop"

    def test_update(self):
        """Should update config values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager(Path(tmpdir) / "config.json")
            
            manager.update(stop_id="100", refresh_interval_seconds=45)
            
            assert manager.config.stop_id == "100"
            assert manager.config.refresh_interval_seconds == 45

    def test_handles_invalid_json(self):
        """Should handle corrupted config files gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            # Write invalid JSON
            config_path.write_text("{invalid json}")
            
            manager = ConfigManager(config_path)
            config = manager.load()
            
            # Should return defaults
            assert config.data_source.mode == "gtfs"
