"""
BSDS - Bus Stop Display System

Main entry point that runs the display update loop and web server.
"""

import logging
import signal
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from .config import get_config, get_config_manager
from .display_driver import get_display_driver
from .power_manager import get_power_manager
from .renderer import get_renderer
from .schedule_provider import get_schedule_provider, GTFSProvider
from .web.app import run_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


class BSDS:
    """Main application controller."""
    
    def __init__(self):
        self.running = False
        self._display_thread: Optional[threading.Thread] = None
        self._web_thread: Optional[threading.Thread] = None
        self._last_data_refresh: Optional[datetime] = None
        
        # Initialize components
        self.config_manager = get_config_manager()
        self.display_driver = get_display_driver()
        self.renderer = get_renderer()
        self.power_manager = get_power_manager()
    
    def start(self) -> None:
        """Start the BSDS application."""
        logger.info("Starting BSDS - Bus Stop Display System")
        logger.info(f"Mock mode: {self.display_driver.mock}")
        
        config = get_config()
        logger.info(f"Data source mode: {config.data_source.mode}")
        
        self.running = True
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        # Clear display on startup
        self.display_driver.clear()
        
        # Initial data refresh on startup
        self._maybe_refresh_data(force=False)
        
        # Start web server in background thread
        self._web_thread = threading.Thread(target=self._run_web_server, daemon=True)
        self._web_thread.start()
        logger.info("Web server started on http://0.0.0.0:5000")
        
        # Run display update loop in main thread
        self._run_display_loop()
    
    def _run_web_server(self) -> None:
        """Run the Flask web server."""
        try:
            run_server(host="0.0.0.0", port=5000, debug=False)
        except Exception as e:
            logger.error(f"Web server error: {e}")
    
    def _run_display_loop(self) -> None:
        """Main display update loop."""
        logger.info("Starting display update loop")
        
        while self.running:
            try:
                # Check if we should update
                if not self.power_manager.should_update_display():
                    time.sleep(60)  # Check again in 1 minute
                    continue
                
                # Refresh data daily
                self._maybe_refresh_data()
                
                # Get current config
                config = get_config()
                
                if config.stop_id is None:
                    # No stop configured - show placeholder
                    provider = get_schedule_provider()
                    if not provider.is_ready():
                        if config.data_source.mode == "gtfs":
                            image = self.renderer.render_placeholder(
                                "Configure GTFS URL in web interface"
                            )
                        else:
                            image = self.renderer.render_placeholder(
                                "Configure MINT API in web interface"
                            )
                    else:
                        image = self.renderer.render_placeholder()
                    self.display_driver.display(image)
                else:
                    # Fetch arrivals and update display
                    self._update_display(config.stop_id)
                
                # Sleep until next update
                sleep_duration = self.power_manager.get_sleep_duration()
                logger.debug(f"Sleeping for {sleep_duration}s")
                
                # Sleep in smaller increments to allow quick shutdown
                for _ in range(sleep_duration):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in display loop: {e}")
                time.sleep(10)  # Back off on error
    
    def _maybe_refresh_data(self, force: bool = False) -> None:
        """Refresh schedule data daily or on force."""
        config = get_config()
        provider = get_schedule_provider()
        
        now = datetime.now()
        
        # Check if we should refresh (daily or forced)
        should_refresh = force
        if not should_refresh and self._last_data_refresh:
            age = now - self._last_data_refresh
            should_refresh = age > timedelta(days=1)
        elif not should_refresh and self._last_data_refresh is None:
            # If never refreshed in this session, only refresh if provider isn't ready
            if not provider.is_ready():
                should_refresh = True
        
        # For GTFS mode, also check if data needs refresh (staleness)
        if isinstance(provider, GTFSProvider) and provider.needs_refresh():
            should_refresh = True
        
        if should_refresh:
            logger.info(f"Refreshing schedule data ({config.data_source.mode} mode)")
            try:
                success = provider.refresh()
                if success:
                    self._last_data_refresh = now
                    logger.info("Schedule data refreshed successfully")
                else:
                    logger.warning("Failed to refresh schedule data")
            except Exception as e:
                logger.warning(f"Failed to refresh data: {e}")
    
    def _update_display(self, stop_id: str) -> None:
        """Fetch arrivals and update the display."""
        logger.info(f"Updating display for stop {stop_id}")
        
        try:
            # Fetch arrivals using the schedule provider
            provider = get_schedule_provider()
            arrivals = provider.get_arrivals(stop_id)
            
            if arrivals.is_connected:
                logger.info(f"Got {len(arrivals.arrivals)} arrivals")
            elif arrivals.is_cached:
                logger.info(f"Got {len(arrivals.arrivals)} arrivals (cached)")
            else:
                logger.warning(f"Failed to get arrivals: {arrivals.error}")
            
            # Render and display
            image = self.renderer.render(arrivals)
            self.display_driver.display(image)
            
        except Exception as e:
            logger.error(f"Failed to update display: {e}")
            # Show error on display
            image = self.renderer.render_placeholder(f"Error: {str(e)[:40]}")
            self.display_driver.display(image)
    
    def _handle_shutdown(self, signum, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received")
        self.stop()
    
    def stop(self) -> None:
        """Stop the BSDS application."""
        logger.info("Stopping BSDS")
        self.running = False
        
        # Clear display
        self.display_driver.clear()
        self.display_driver.sleep()
        
        logger.info("BSDS stopped")


def main():
    """Main entry point."""
    app = BSDS()
    app.start()


if __name__ == "__main__":
    main()
