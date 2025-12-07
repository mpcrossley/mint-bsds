"""
API client for the mixre backend.

Fetches real-time arrivals, stop details, and schedules.
Includes offline schedule caching for when the API is unavailable.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional

import requests

from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class Arrival:
    """Represents a single bus arrival."""
    route_short_name: str
    route_color: str
    headsign: str
    scheduled_time: str
    predicted_time: Optional[str]
    minutes_away: int
    is_realtime: bool
    delay_seconds: int = 0


@dataclass
class Stop:
    """Represents a bus stop."""
    id: int
    gtfs_stop_id: str
    stop_code: str
    stop_name: str
    lat: float
    lon: float


@dataclass
class ArrivalsResponse:
    """Response from the arrivals endpoint."""
    stop: Stop
    arrivals: List[Arrival]
    timestamp: datetime
    is_connected: bool = True
    is_cached: bool = False
    error: Optional[str] = None


class ScheduleCache:
    """Caches static schedule data for offline operation."""
    
    CACHE_DIR = Path(__file__).parent.parent / "cache"
    CACHE_DAYS = 1  # Refresh cache daily
    
    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, stop_id: int) -> Path:
        """Get the cache file path for a stop."""
        return self.CACHE_DIR / f"schedule_{stop_id}.json"
    
    def is_stale(self, stop_id: int) -> bool:
        """Check if cache is stale and needs refresh."""
        cache_path = self._get_cache_path(stop_id)
        if not cache_path.exists():
            return True
        
        # Check file modification time
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        age = datetime.now() - mtime
        return age > timedelta(days=self.CACHE_DAYS)
    
    def save(self, stop_id: int, stop: Stop, schedule: List[dict]) -> None:
        """Save schedule to cache."""
        cache_path = self._get_cache_path(stop_id)
        data = {
            "stop": {
                "id": stop.id,
                "gtfs_stop_id": stop.gtfs_stop_id,
                "stop_code": stop.stop_code,
                "stop_name": stop.stop_name,
                "lat": stop.lat,
                "lon": stop.lon,
            },
            "schedule": schedule,
            "cached_at": datetime.now().isoformat(),
        }
        
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Cached schedule for stop {stop_id} ({len(schedule)} arrivals)")
    
    def load(self, stop_id: int) -> Optional[tuple]:
        """Load schedule from cache. Returns (stop, arrivals) or None."""
        cache_path = self._get_cache_path(stop_id)
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            
            stop = Stop(**data["stop"])
            schedule = data["schedule"]
            
            return stop, schedule
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to load cache for stop {stop_id}: {e}")
            return None


class APIClient:
    """Client for the mixre backend API."""
    
    def __init__(self, base_url: Optional[str] = None, system_id: Optional[int] = None):
        config = get_config()
        self.base_url = (base_url or config.api_base_url).rstrip("/")
        self.system_id = system_id or config.system_id
        self.timeout = 10  # seconds
        self._session = requests.Session()
        self._cache = ScheduleCache()
    
    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the API."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self._session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
    
    def get_stop(self, stop_id: int) -> Stop:
        """Get stop details by ID."""
        data = self._get(f"/api/stops/{stop_id}")
        return Stop(
            id=data["id"],
            gtfs_stop_id=data["gtfs_stop_id"],
            stop_code=data.get("stop_code", ""),
            stop_name=data["stop_name"],
            lat=data["lat"],
            lon=data["lon"],
        )
    
    def search_stops(self, query: str, limit: int = 20) -> List[Stop]:
        """Search for stops by name or code."""
        data = self._get("/api/stops", params={
            "system_id": self.system_id,
            "search": query,
            "limit": limit,
        })
        return [
            Stop(
                id=s["id"],
                gtfs_stop_id=s["gtfs_stop_id"],
                stop_code=s.get("stop_code", ""),
                stop_name=s["stop_name"],
                lat=s["lat"],
                lon=s["lon"],
            )
            for s in data
        ]
    
    def get_arrivals(self, stop_id: int) -> ArrivalsResponse:
        """
        Get real-time arrivals for a stop.
        
        Falls back to cached schedule if API is unavailable.
        """
        try:
            # Get stop details first
            stop = self.get_stop(stop_id)
            
            # Use gtfs_stop_id (the stop code) for the predictions endpoint
            # The predictions API expects the GTFS stop ID, not the database ID
            gtfs_stop_id = stop.gtfs_stop_id
            
            # Get real-time arrivals from predictions API
            data = self._get(
                f"/api/predictions/stop/{gtfs_stop_id}/arrivals",
                params={"system_id": self.system_id}
            )
            
            arrivals = []
            for arr in data.get("arrivals", []):
                # The predictions API returns predicted_minutes directly
                minutes_away = int(arr.get("predicted_minutes", 0))
                
                arrivals.append(Arrival(
                    route_short_name=arr.get("route_name", "?"),
                    route_color=arr.get("route_color", "000000"),
                    headsign=arr.get("headsign") or "",
                    scheduled_time="",
                    predicted_time=None,  # Predictions API doesn't return absolute times
                    minutes_away=minutes_away,
                    is_realtime=True,  # Predictions are always real-time based
                    delay_seconds=int(arr.get("current_delay_minutes", 0) * 60),
                ))
            
            # Update cache in background if it's stale
            if self._cache.is_stale(stop_id):
                self._refresh_schedule_cache(stop_id, stop)
            
            return ArrivalsResponse(
                stop=stop,
                arrivals=arrivals,
                timestamp=datetime.now(),
                is_connected=True,
            )
        
        except requests.RequestException as e:
            logger.error(f"Failed to get arrivals: {e}")
            
            # Try to use cached schedule
            return self._get_cached_arrivals(stop_id, str(e))
    
    def _get_cached_arrivals(self, stop_id: int, error: str) -> ArrivalsResponse:
        """Get arrivals from cached schedule when API is unavailable."""
        cached = self._cache.load(stop_id)
        
        if cached is None:
            return ArrivalsResponse(
                stop=Stop(id=stop_id, gtfs_stop_id="", stop_code="", 
                         stop_name="Error", lat=0, lon=0),
                arrivals=[],
                timestamp=datetime.now(),
                is_connected=False,
                error=error,
            )
        
        stop, schedule = cached
        arrivals = self._schedule_to_arrivals(schedule)
        
        logger.info(f"Using cached schedule for stop {stop_id} ({len(arrivals)} arrivals)")
        
        return ArrivalsResponse(
            stop=stop,
            arrivals=arrivals,
            timestamp=datetime.now(),
            is_connected=False,
            is_cached=True,
            error=error,
        )
    
    def _schedule_to_arrivals(self, schedule: List[dict]) -> List[Arrival]:
        """Convert cached schedule to arrivals with calculated minutes away."""
        now = datetime.now()
        arrivals = []
        
        for item in schedule:
            # Parse scheduled time (format: "HH:MM:SS")
            time_str = item.get("arrival_time", "")
            if not time_str:
                continue
            
            try:
                # Handle times after midnight (e.g., "25:30:00")
                parts = time_str.split(":")
                hours = int(parts[0])
                minutes = int(parts[1])
                
                # Create datetime for today
                scheduled_dt = now.replace(
                    hour=hours % 24,
                    minute=minutes,
                    second=0,
                    microsecond=0
                )
                
                # If time has passed today, skip
                if scheduled_dt < now:
                    continue
                
                # If hours >= 24, it's tomorrow
                if hours >= 24:
                    scheduled_dt += timedelta(days=1)
                
                minutes_away = int((scheduled_dt - now).total_seconds() / 60)
                
                # Only show arrivals within next 60 minutes
                if minutes_away > 60:
                    continue
                
                arrivals.append(Arrival(
                    route_short_name=item.get("route_short_name", "?"),
                    route_color=item.get("route_color", "000000"),
                    headsign=item.get("headsign", ""),
                    scheduled_time=time_str,
                    predicted_time=None,
                    minutes_away=minutes_away,
                    is_realtime=False,
                    delay_seconds=0,
                ))
            except (ValueError, IndexError):
                continue
        
        # Sort by minutes away
        arrivals.sort(key=lambda a: a.minutes_away)
        return arrivals[:10]  # Return top 10
    
    def _refresh_schedule_cache(self, stop_id: int, stop: Stop) -> None:
        """Refresh the schedule cache for a stop."""
        try:
            schedule = self.get_schedule(stop_id)
            raw_schedule = [
                {
                    "route_short_name": a.route_short_name,
                    "route_color": a.route_color,
                    "headsign": a.headsign,
                    "arrival_time": a.scheduled_time,
                }
                for a in schedule
            ]
            self._cache.save(stop_id, stop, raw_schedule)
        except Exception as e:
            logger.warning(f"Failed to refresh schedule cache: {e}")
    
    def refresh_cache_for_stop(self, stop_id: int) -> bool:
        """
        Manually refresh schedule cache for a stop.
        
        Call this once a day to ensure offline data is fresh.
        """
        try:
            stop = self.get_stop(stop_id)
            self._refresh_schedule_cache(stop_id, stop)
            return True
        except Exception as e:
            logger.error(f"Failed to refresh cache: {e}")
            return False
    
    def get_schedule(self, stop_id: int, schedule_date: Optional[str] = None) -> List[Arrival]:
        """Get scheduled arrivals from the static schedule."""
        params = {}
        if schedule_date:
            params["date"] = schedule_date
        
        data = self._get(f"/api/stops/{stop_id}/schedule", params=params)
        
        arrivals = []
        for item in data.get("schedule", []):
            arrivals.append(Arrival(
                route_short_name=item.get("route_short_name", "?"),
                route_color=item.get("route_color", "000000"),
                headsign=item.get("headsign", ""),
                scheduled_time=item.get("arrival_time", ""),
                predicted_time=None,
                minutes_away=0,
                is_realtime=False,
            ))
        
        return arrivals


# Global client instance
_client: Optional[APIClient] = None


def get_api_client() -> APIClient:
    """Get the global API client instance."""
    global _client
    if _client is None:
        _client = APIClient()
    return _client
