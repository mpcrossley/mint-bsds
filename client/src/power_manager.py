"""
Power management for battery optimization.

Handles quiet hours, sleep modes, and power-saving features.
"""

import logging
from datetime import datetime, time
from typing import Optional

from .config import get_config

logger = logging.getLogger(__name__)


class PowerManager:
    """Manages power-saving features for battery operation."""
    
    def __init__(self):
        self._is_sleeping = False
    
    def is_quiet_hours(self) -> bool:
        """
        Check if currently in quiet hours.
        
        During quiet hours, the display can enter deep sleep to save power.
        """
        config = get_config()
        power_config = config.power
        
        if not power_config.quiet_hours_start or not power_config.quiet_hours_end:
            return False
        
        try:
            start = self._parse_time(power_config.quiet_hours_start)
            end = self._parse_time(power_config.quiet_hours_end)
            now = datetime.now().time()
            
            # Handle overnight ranges (e.g., 23:00 to 05:00)
            if start <= end:
                return start <= now <= end
            else:
                return now >= start or now <= end
        
        except ValueError:
            return False
    
    def _parse_time(self, time_str: str) -> time:
        """Parse a time string (HH:MM) to a time object."""
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    
    def should_update_display(self) -> bool:
        """
        Determine if the display should be updated.
        
        Returns False during quiet hours when sleep is enabled.
        """
        if not self.is_quiet_hours():
            return True
        
        config = get_config()
        if config.power.sleep_between_updates:
            logger.info("In quiet hours with sleep enabled - skipping update")
            return False
        
        return True
    
    def get_sleep_duration(self) -> int:
        """
        Get the recommended sleep duration in seconds.
        
        Returns longer sleep during quiet hours to save power.
        """
        config = get_config()
        
        if self.is_quiet_hours():
            # Sleep for 5 minutes during quiet hours
            return 300
        
        return config.refresh_interval_seconds
    
    def enter_sleep(self) -> None:
        """Enter low-power sleep mode."""
        if self._is_sleeping:
            return
        
        logger.info("Entering power-saving sleep mode")
        self._is_sleeping = True
        
        # Future: Could use RPi.GPIO to control power states
        # or use systemd to suspend the system
    
    def wake_up(self) -> None:
        """Wake from sleep mode."""
        if not self._is_sleeping:
            return
        
        logger.info("Waking from sleep mode")
        self._is_sleeping = False


# Global power manager instance
_power_manager: Optional[PowerManager] = None


def get_power_manager() -> PowerManager:
    """Get the global power manager instance."""
    global _power_manager
    if _power_manager is None:
        _power_manager = PowerManager()
    return _power_manager
