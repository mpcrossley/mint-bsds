"""
Configuration management for BSDS.

Handles loading, saving, and validating configuration settings.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class DisplayConfig:
    """Display-related settings."""
    orientation: int = 0  # 0, 90, 180, or 270 degrees
    max_arrivals: int = 8  # Maximum arrivals to show


@dataclass
class PowerConfig:
    """Power management settings."""
    quiet_hours_start: Optional[str] = None  # e.g., "23:00"
    quiet_hours_end: Optional[str] = None  # e.g., "05:00"
    sleep_between_updates: bool = False  # Deep sleep to save power


@dataclass
class DataSourceConfig:
    """Data source configuration for schedule data."""
    mode: str = "gtfs"  # "gtfs" (standalone) or "mint" (MINT API)
    
    # GTFS mode settings
    gtfs_url: Optional[str] = None  # URL to GTFS ZIP file
    gtfs_rt_url: Optional[str] = None  # Optional GTFS-RT feed URL
    
    # MINT mode settings  
    mint_api_url: str = "http://localhost:8000"
    mint_system_id: int = 1


@dataclass
class Config:
    """Main configuration container."""
    # Stop configuration (uses GTFS stop_id string)
    stop_id: Optional[str] = None
    stop_name: Optional[str] = None
    
    # Refresh settings
    refresh_interval_seconds: int = 30
    
    # Data source settings
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    
    # Display settings
    display: DisplayConfig = field(default_factory=DisplayConfig)
    
    # Power settings
    power: PowerConfig = field(default_factory=PowerConfig)
    
    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Create config from dictionary."""
        display_data = data.pop("display", {})
        power_data = data.pop("power", {})
        data_source_data = data.pop("data_source", {})
        
        # Handle legacy config that may have old fields
        data.pop("api_base_url", None)
        data.pop("system_id", None)
        data.pop("stop_code", None)
        
        # Convert stop_id to string if it's an int (legacy)
        if "stop_id" in data and data["stop_id"] is not None:
            data["stop_id"] = str(data["stop_id"])
        
        return cls(
            display=DisplayConfig(**display_data),
            power=PowerConfig(**power_data),
            data_source=DataSourceConfig(**data_source_data),
            **data
        )


class ConfigManager:
    """Manages configuration persistence."""
    
    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.json"
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Optional[Config] = None
    
    @property
    def config(self) -> Config:
        """Get current configuration, loading from file if needed."""
        if self._config is None:
            self._config = self.load()
        return self._config
    
    def load(self) -> Config:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                return Config.from_dict(data)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                print(f"Warning: Failed to load config: {e}. Using defaults.")
        
        return Config()
    
    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file."""
        if config is not None:
            self._config = config
        
        if self._config is None:
            return
        
        # Ensure parent directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, "w") as f:
            json.dump(self._config.to_dict(), f, indent=2)
    
    def update(self, **kwargs) -> Config:
        """Update configuration with new values."""
        config = self.config
        
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
            elif hasattr(config.display, key):
                setattr(config.display, key, value)
            elif hasattr(config.power, key):
                setattr(config.power, key, value)
            elif hasattr(config.data_source, key):
                setattr(config.data_source, key, value)
        
        self.save(config)
        return config


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global config manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> Config:
    """Get the current configuration."""
    return get_config_manager().config
