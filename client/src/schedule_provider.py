"""
Schedule provider abstraction.

Provides a unified interface for schedule data regardless of source
(GTFS file or MINT API).
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class Stop:
    """Represents a transit stop."""
    stop_id: str
    stop_name: str
    stop_code: Optional[str] = None
    lat: float = 0.0
    lon: float = 0.0


@dataclass
class Arrival:
    """Represents an arrival at a stop."""
    route_short_name: str
    route_color: str
    headsign: str
    minutes_away: int
    is_realtime: bool
    scheduled_time: str = ""


@dataclass
class ArrivalsResponse:
    """Response from arrivals query."""
    stop: Stop
    arrivals: List[Arrival]
    timestamp: datetime
    is_connected: bool = True
    is_cached: bool = False
    error: Optional[str] = None


class ScheduleProvider(ABC):
    """Abstract base class for schedule data providers."""
    
    @abstractmethod
    def search_stops(self, query: str, limit: int = 20) -> List[Stop]:
        """Search for stops by name or code."""
        pass
    
    @abstractmethod
    def get_stop(self, stop_id: str) -> Optional[Stop]:
        """Get a stop by ID."""
        pass
    
    @abstractmethod
    def get_arrivals(self, stop_id: str) -> ArrivalsResponse:
        """Get upcoming arrivals for a stop."""
        pass
    
    @abstractmethod
    def refresh(self) -> bool:
        """Refresh data from source. Returns True on success."""
        pass
    
    @abstractmethod
    def is_ready(self) -> bool:
        """Check if provider has data and is ready to serve requests."""
        pass


class GTFSProvider(ScheduleProvider):
    """Schedule provider using static GTFS data."""
    
    def __init__(self, gtfs_url: Optional[str] = None, gtfs_rt_url: Optional[str] = None):
        from .gtfs_parser import get_gtfs_parser
        self._parser = get_gtfs_parser()
        self._rt_url = gtfs_rt_url
        if gtfs_url:
            self._parser.set_url(gtfs_url)
    
    def search_stops(self, query: str, limit: int = 20) -> List[Stop]:
        """Search stops in GTFS data."""
        gtfs_stops = self._parser.search_stops(query, limit)
        return [
            Stop(
                stop_id=s.stop_id,
                stop_name=s.stop_name,
                stop_code=s.stop_code,
                lat=s.stop_lat,
                lon=s.stop_lon,
            )
            for s in gtfs_stops
        ]
    
    def get_stop(self, stop_id: str) -> Optional[Stop]:
        """Get a stop by ID."""
        gtfs_stop = self._parser.get_stop(stop_id)
        if not gtfs_stop:
            return None
        return Stop(
            stop_id=gtfs_stop.stop_id,
            stop_name=gtfs_stop.stop_name,
            stop_code=gtfs_stop.stop_code,
            lat=gtfs_stop.stop_lat,
            lon=gtfs_stop.stop_lon,
        )
    
    def get_arrivals(self, stop_id: str) -> ArrivalsResponse:
        """Get arrivals from GTFS schedule."""
        # Trigger RT update if configured
        if self._rt_url:
            self._parser.update_realtime(self._rt_url)
            
        stop = self.get_stop(stop_id)
        if not stop:
            return ArrivalsResponse(
                stop=Stop(stop_id=stop_id, stop_name="Unknown"),
                arrivals=[],
                timestamp=datetime.now(),
                is_connected=False,
                error="Stop not found",
            )
        
        gtfs_arrivals = self._parser.get_arrivals(stop_id)
        arrivals = [
            Arrival(
                route_short_name=a["route_short_name"],
                route_color=a["route_color"],
                headsign=a["headsign"],
                minutes_away=a["minutes_away"],
                is_realtime=a["is_realtime"],
                scheduled_time=a.get("scheduled_time", ""),
            )
            for a in gtfs_arrivals
        ]
        
        return ArrivalsResponse(
            stop=stop,
            arrivals=arrivals,
            timestamp=datetime.now(),
            is_connected=True,
        )
    
    def refresh(self) -> bool:
        """Download and parse GTFS data."""
        return self._parser.download_and_parse()
    
    def is_ready(self) -> bool:
        """Check if GTFS data is loaded."""
        return self._parser.is_loaded()
    
    def needs_refresh(self) -> bool:
        """Check if GTFS data should be refreshed."""
        return self._parser.needs_refresh()


class MINTProvider(ScheduleProvider):
    """Schedule provider using MINT/MIXRE API."""
    
    def __init__(self, api_url: str, system_id: int):
        self._api_url = api_url.rstrip("/")
        self._system_id = system_id
        self._session = None
        self._connected = False
    
    def _get_session(self):
        """Get or create requests session."""
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session
    
    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make GET request to API."""
        import requests
        url = f"{self._api_url}{endpoint}"
        response = self._get_session().get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def search_stops(self, query: str, limit: int = 20) -> List[Stop]:
        """Search stops via MINT API."""
        try:
            data = self._get("/api/stops", params={
                "system_id": self._system_id,
                "search": query,
                "limit": limit,
            })
            self._connected = True
            return [
                Stop(
                    stop_id=s.get("stop_code") or str(s["id"]),  # Use stop_code as primary ID
                    stop_name=s["stop_name"],
                    stop_code=s.get("stop_code"),
                    lat=s.get("lat", 0),
                    lon=s.get("lon", 0),
                )
                for s in data
            ]
        except Exception as e:
            logger.error(f"MINT API search failed: {e}")
            self._connected = False
            return []
    
    def get_stop(self, stop_id: str) -> Optional[Stop]:
        """Get stop from MINT API using stop_code."""
        try:
            data = self._get(f"/api/stops/{stop_id}")
            self._connected = True
            return Stop(
                stop_id=data.get("stop_code") or str(data["id"]),
                stop_name=data["stop_name"],
                stop_code=data.get("stop_code"),
                lat=data.get("lat", 0),
                lon=data.get("lon", 0),
            )
        except Exception as e:
            logger.error(f"MINT API get_stop failed: {e}")
            self._connected = False
            return None
    
    def get_arrivals(self, stop_id: str) -> ArrivalsResponse:
        """Get arrivals from MINT predictions API."""
        try:
            # First get stop details
            stop = self.get_stop(stop_id)
            if not stop:
                return ArrivalsResponse(
                    stop=Stop(stop_id=stop_id, stop_name="Unknown"),
                    arrivals=[],
                    timestamp=datetime.now(),
                    is_connected=False,
                    error="Stop not found",
                )
            
            # Get predictions using GTFS stop ID
            data = self._get(
                f"/api/predictions/stop/{stop.stop_code or stop_id}/arrivals",
                params={"system_id": self._system_id}
            )
            
            arrivals = [
                Arrival(
                    route_short_name=a.get("route_name", "?"),
                    route_color=a.get("route_color", "000000"),
                    headsign=a.get("headsign", ""),
                    minutes_away=int(a.get("predicted_minutes", 0)),
                    is_realtime=True,
                )
                for a in data.get("arrivals", [])
            ]
            
            # Supplement with scheduled arrivals from GTFS if available
            from . import schedule_provider as sp
            fallback = sp.get_gtfs_fallback()
            if fallback and fallback.is_ready():
                try:
                    scheduled_response = fallback.get_arrivals(stop_id)
                    # Get the max time from predictions to avoid overlap
                    max_predicted_min = max([a.minutes_away for a in arrivals], default=0)
                    
                    # Add scheduled arrivals that are after the last prediction
                    for scheduled in scheduled_response.arrivals:
                        if scheduled.minutes_away > max_predicted_min:
                            # Mark as not realtime (scheduled)
                            scheduled.is_realtime = False
                            arrivals.append(scheduled)
                    
                    # Keep only top 8 arrivals
                    arrivals = arrivals[:8]
                except Exception as e:
                    logger.debug(f"Could not supplement with scheduled: {e}")
            
            self._connected = True
            return ArrivalsResponse(
                stop=stop,
                arrivals=arrivals,
                timestamp=datetime.now(),
                is_connected=True,
            )
            
        except Exception as e:
            logger.warning(f"MINT API get_arrivals failed: {e}, trying GTFS fallback")
            self._connected = False
            
            # Try GTFS fallback if available
            from . import schedule_provider as sp
            fallback = sp.get_gtfs_fallback()
            if fallback and fallback.is_ready():
                logger.info("Using GTFS static fallback for arrivals")
                response = fallback.get_arrivals(stop_id)
                response.is_cached = True  # Mark as fallback data
                response.error = "Using static schedule (API unavailable)"
                return response
            
            return ArrivalsResponse(
                stop=Stop(stop_id=stop_id, stop_name="Error"),
                arrivals=[],
                timestamp=datetime.now(),
                is_connected=False,
                error=f"API unavailable: {e}",
            )
    
    def refresh(self) -> bool:
        """Test API connection."""
        try:
            self._get("/api/health")
            self._connected = True
            return True
        except Exception:
            # Try a simple request instead
            try:
                self._get("/api/stops", params={"system_id": self._system_id, "limit": 1})
                self._connected = True
                return True
            except Exception:
                self._connected = False
                return False
    
    def is_ready(self) -> bool:
        """Check if API is accessible."""
        return self._connected


# Global provider instance
_provider: Optional[ScheduleProvider] = None
_gtfs_fallback: Optional['GTFSProvider'] = None


def get_schedule_provider() -> ScheduleProvider:
    """Get the current schedule provider based on config."""
    global _provider, _gtfs_fallback
    
    from .config import get_config
    config = get_config()
    ds = config.data_source
    
    # Check if we need to create/recreate provider
    if _provider is None:
        if ds.mode == "mint":
            _provider = MINTProvider(ds.mint_api_url, ds.mint_system_id)
            # Also create a GTFS fallback provider for when API is unavailable
            if ds.gtfs_url:
                _gtfs_fallback = GTFSProvider(ds.gtfs_url, ds.gtfs_rt_url)
                logger.info("Created GTFS fallback provider for MINT mode")
        else:
            _provider = GTFSProvider(ds.gtfs_url, ds.gtfs_rt_url)
    
    return _provider


def get_gtfs_fallback() -> Optional['GTFSProvider']:
    """Get the GTFS fallback provider (if available)."""
    global _gtfs_fallback
    return _gtfs_fallback


def reset_provider() -> None:
    """Reset the provider (used when config changes)."""
    global _provider, _gtfs_fallback
    _provider = None
    _gtfs_fallback = None
