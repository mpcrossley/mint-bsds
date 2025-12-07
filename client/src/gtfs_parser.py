"""
GTFS ZIP file parser for standalone schedule data.

Downloads, extracts, and parses GTFS files to provide schedule data
without requiring a backend API.
"""

import csv
import io
import logging
import pickle
import zipfile
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests

logger = logging.getLogger(__name__)

# Cache directory for GTFS data
CACHE_DIR = Path(__file__).parent.parent / "cache" / "gtfs"
CACHE_FILE = CACHE_DIR / "gtfs_data.pkl"


@dataclass
class GTFSStop:
    """A stop from stops.txt."""
    stop_id: str
    stop_name: str
    stop_code: Optional[str] = None
    stop_lat: float = 0.0
    stop_lon: float = 0.0


@dataclass
class GTFSRoute:
    """A route from routes.txt."""
    route_id: str
    route_short_name: str
    route_long_name: str
    route_color: str = "000000"
    route_text_color: str = "FFFFFF"


@dataclass
class GTFSTrip:
    """A trip from trips.txt."""
    trip_id: str
    route_id: str
    service_id: str
    trip_headsign: str = ""
    direction_id: int = 0


@dataclass
class GTFSStopTime:
    """A stop time from stop_times.txt."""
    trip_id: str
    stop_id: str
    arrival_time: str  # Format: HH:MM:SS (can be > 24:00)
    departure_time: str
    stop_sequence: int


@dataclass
class GTFSCalendar:
    """Calendar entry from calendar.txt."""
    service_id: str
    monday: bool
    tuesday: bool
    wednesday: bool
    thursday: bool
    friday: bool
    saturday: bool
    sunday: bool
    start_date: str  # YYYYMMDD
    end_date: str


@dataclass
class GTFSCalendarDate:
    """Calendar exception from calendar_dates.txt."""
    service_id: str
    date: str  # YYYYMMDD
    exception_type: int  # 1 = added, 2 = removed


class GTFSParser:
    """
    Parses GTFS ZIP files and provides schedule queries.
    
    Caches parsed data locally for performance.
    """
    
    def __init__(self, gtfs_url: Optional[str] = None):
        self.gtfs_url = gtfs_url
        self._stops: Dict[str, GTFSStop] = {}
        self._routes: Dict[str, GTFSRoute] = {}
        self._trips: Dict[str, GTFSTrip] = {}
        self._stop_times: Dict[str, List[GTFSStopTime]] = {}  # keyed by stop_id
        self._calendars: Dict[str, GTFSCalendar] = {}
        self._calendar_dates: Dict[str, List[GTFSCalendarDate]] = {}  # keyed by service_id
        self._loaded = False
        self._last_download: Optional[datetime] = None
        
        # Real-time state
        self._rt_updates: Dict[str, Dict[str, int]] = {}  # trip_id -> stop_id -> delay
        self._rt_last_update: Optional[datetime] = None
        
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Try to load from cache on startup
        self.load_cache()
    
    def set_url(self, url: str) -> None:
        """Set the GTFS URL and mark as needing reload."""
        if url != self.gtfs_url:
            self.gtfs_url = url
            self._loaded = False
    
    def is_loaded(self) -> bool:
        """Check if GTFS data is loaded."""
        return self._loaded and len(self._stops) > 0
    
    def needs_refresh(self, max_age_hours: int = 24) -> bool:
        """Check if GTFS data should be refreshed."""
        if not self._loaded:
            return True
        if self._last_download is None:
            return True
        age = datetime.now() - self._last_download
        return age > timedelta(hours=max_age_hours)
        
    def save_cache(self) -> bool:
        """Save parsed data to cache file."""
        if not self._loaded:
            return False
            
        try:
            logger.info(f"Saving GTFS cache to {CACHE_FILE}...")
            data = {
                "stops": self._stops,
                "routes": self._routes,
                "trips": self._trips,
                "stop_times": self._stop_times,
                "calendars": self._calendars,
                "calendar_dates": self._calendar_dates,
                "last_download": self._last_download,
                "url": self.gtfs_url
            }
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(data, f)
            logger.info("GTFS cache saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save GTFS cache: {e}")
            return False

    def load_cache(self) -> bool:
        """Load parsed data from cache file."""
        if not CACHE_FILE.exists():
            return False
            
        try:
            logger.info(f"Loading GTFS cache from {CACHE_FILE}...")
            with open(CACHE_FILE, "rb") as f:
                data = pickle.load(f)
            
            # Verify URL matches if set
            if self.gtfs_url and data.get("url") != self.gtfs_url:
                logger.info("Cache URL mismatch, ignoring cache")
                return False
                
            self._stops = data["stops"]
            self._routes = data["routes"]
            self._trips = data["trips"]
            self._stop_times = data["stop_times"]
            self._calendars = data["calendars"]
            self._calendar_dates = data["calendar_dates"]
            self._last_download = data["last_download"]
            
            # Update URL if not set
            if not self.gtfs_url:
                self.gtfs_url = data.get("url")
                
            self._loaded = True
            logger.info(f"Loaded GTFS from cache: {len(self._stops)} stops")
            return True
        except Exception as e:
            logger.error(f"Failed to load GTFS cache: {e}")
            return False
    
    def download_and_parse(self) -> bool:
        """
        Download GTFS ZIP from URL and parse it.
        
        Returns True on success, False on failure.
        """
        if not self.gtfs_url:
            logger.error("No GTFS URL configured")
            return False
        
        logger.info(f"Downloading GTFS from {self.gtfs_url}")
        
        try:
            # Download ZIP
            response = requests.get(self.gtfs_url, timeout=60)
            response.raise_for_status()
            
            # Parse ZIP contents
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                self._parse_zip(zf)
            
            self._loaded = True
            self._last_download = datetime.now()
            
            logger.info(f"Loaded GTFS: {len(self._stops)} stops, "
                       f"{len(self._routes)} routes, {len(self._trips)} trips")
            
            # Save to cache
            self.save_cache()
            
            return True
            
        except requests.RequestException as e:
            logger.error(f"Failed to download GTFS: {e}")
            return False
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid GTFS ZIP file: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to parse GTFS: {e}")
            return False
    
    def prune_data(self, keep_stop_ids: List[str]) -> Tuple[int, int, int]:
        """
        Prune dataset to keep only data relevant to the given stop IDs.
        
        Removes unrelated stops, stop_times, trips, routes, calendars, and dates.
        Returns a tuple of (stops_removed, trips_removed, routes_removed).
        """
        if not self._loaded:
            logger.warning("Cannot prune: data not loaded")
            return (0, 0, 0)
            
        initial_stops = len(self._stops)
        initial_trips = len(self._trips)
        initial_routes = len(self._routes)
        
        logger.info(f"Pruning GTFS data for stops: {keep_stop_ids}")
        logger.info(f"Before: {initial_stops} stops, {initial_trips} trips, {initial_routes} routes")
        
        # 1. Identify all relevant stops (target stops + potentially parents/children if we had logic for that)
        # For now, strictly keep target stops
        relevant_stop_ids = set(keep_stop_ids)
        
        # 2. Filter Stop Times & Identify Relevant Trips
        new_stop_times: Dict[str, List[GTFSStopTime]] = {}
        relevant_trip_ids = set()
        
        for stop_id in relevant_stop_ids:
            if stop_id in self._stop_times:
                # Keep ALL stop times for the target stop
                # (We don't need stop times for other stops on the same trip for basic display)
                times = self._stop_times[stop_id]
                new_stop_times[stop_id] = times
                
                # Collect all trip IDs that pass through this stop
                for st in times:
                    relevant_trip_ids.add(st.trip_id)
        
        # 3. Filter Trips & Identify Relevant Routes / Services
        new_trips: Dict[str, GTFSTrip] = {}
        relevant_route_ids = set()
        relevant_service_ids = set()
        
        for trip_id in relevant_trip_ids:
            if trip_id in self._trips:
                trip = self._trips[trip_id]
                new_trips[trip_id] = trip
                relevant_route_ids.add(trip.route_id)
                relevant_service_ids.add(trip.service_id)
        
        # 4. Filter Routes
        new_routes: Dict[str, GTFSRoute] = {}
        for route_id in relevant_route_ids:
            if route_id in self._routes:
                new_routes[route_id] = self._routes[route_id]
        
        # 5. Filter Stops
        # Only keep stops that we explicitly asked for
        new_stops: Dict[str, GTFSStop] = {}
        for stop_id in relevant_stop_ids:
            if stop_id in self._stops:
                new_stops[stop_id] = self._stops[stop_id]
        
        # 6. Filter Calendars
        new_calendars: Dict[str, GTFSCalendar] = {}
        for service_id in relevant_service_ids:
            if service_id in self._calendars:
                new_calendars[service_id] = self._calendars[service_id]
                
        # 7. Filter Calendar Dates
        new_calendar_dates: Dict[str, List[GTFSCalendarDate]] = {}
        for service_id in relevant_service_ids:
            if service_id in self._calendar_dates:
                new_calendar_dates[service_id] = self._calendar_dates[service_id]
        
        # Apply changes
        self._stops = new_stops
        self._routes = new_routes
        self._trips = new_trips
        self._stop_times = new_stop_times
        self._calendars = new_calendars
        self._calendar_dates = new_calendar_dates
        
        removed_stops = initial_stops - len(self._stops)
        removed_trips = initial_trips - len(self._trips)
        removed_routes = initial_routes - len(self._routes)
        
        logger.info(f"After: {len(self._stops)} stops, {len(self._trips)} trips, {len(self._routes)} routes")
        logger.info(f"Pruning complete. Removed {removed_stops} stops, {removed_trips} trips, {removed_routes} routes")
        
        return (removed_stops, removed_trips, removed_routes)

    def _parse_zip(self, zf: zipfile.ZipFile) -> None:
        """Parse all required files from GTFS ZIP."""
        # Parse stops.txt
        if "stops.txt" in zf.namelist():
            self._parse_stops(zf.read("stops.txt").decode("utf-8-sig"))
        
        # Parse routes.txt
        if "routes.txt" in zf.namelist():
            self._parse_routes(zf.read("routes.txt").decode("utf-8-sig"))
        
        # Parse trips.txt
        if "trips.txt" in zf.namelist():
            self._parse_trips(zf.read("trips.txt").decode("utf-8-sig"))
        
        # Parse stop_times.txt
        if "stop_times.txt" in zf.namelist():
            self._parse_stop_times(zf.read("stop_times.txt").decode("utf-8-sig"))
        
        # Parse calendar.txt
        if "calendar.txt" in zf.namelist():
            self._parse_calendar(zf.read("calendar.txt").decode("utf-8-sig"))
        
        # Parse calendar_dates.txt
        if "calendar_dates.txt" in zf.namelist():
            self._parse_calendar_dates(zf.read("calendar_dates.txt").decode("utf-8-sig"))
    
    def _parse_stops(self, content: str) -> None:
        """Parse stops.txt content."""
        self._stops.clear()
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            stop = GTFSStop(
                stop_id=row["stop_id"],
                stop_name=row.get("stop_name", ""),
                stop_code=row.get("stop_code"),
                stop_lat=float(row.get("stop_lat", 0) or 0),
                stop_lon=float(row.get("stop_lon", 0) or 0),
            )
            self._stops[stop.stop_id] = stop
    
    def _parse_routes(self, content: str) -> None:
        """Parse routes.txt content."""
        self._routes.clear()
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            route = GTFSRoute(
                route_id=row["route_id"],
                route_short_name=row.get("route_short_name", ""),
                route_long_name=row.get("route_long_name", ""),
                route_color=row.get("route_color", "000000") or "000000",
                route_text_color=row.get("route_text_color", "FFFFFF") or "FFFFFF",
            )
            self._routes[route.route_id] = route
    
    def _parse_trips(self, content: str) -> None:
        """Parse trips.txt content."""
        self._trips.clear()
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            trip = GTFSTrip(
                trip_id=row["trip_id"],
                route_id=row["route_id"],
                service_id=row["service_id"],
                trip_headsign=row.get("trip_headsign", ""),
                direction_id=int(row.get("direction_id", 0) or 0),
            )
            self._trips[trip.trip_id] = trip
    
    def _parse_stop_times(self, content: str) -> None:
        """Parse stop_times.txt content."""
        self._stop_times.clear()
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            stop_time = GTFSStopTime(
                trip_id=row["trip_id"],
                stop_id=row["stop_id"],
                arrival_time=row.get("arrival_time", ""),
                departure_time=row.get("departure_time", ""),
                stop_sequence=int(row.get("stop_sequence", 0) or 0),
            )
            if stop_time.stop_id not in self._stop_times:
                self._stop_times[stop_time.stop_id] = []
            self._stop_times[stop_time.stop_id].append(stop_time)
    
    def _parse_calendar(self, content: str) -> None:
        """Parse calendar.txt content."""
        self._calendars.clear()
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            cal = GTFSCalendar(
                service_id=row["service_id"],
                monday=row.get("monday") == "1",
                tuesday=row.get("tuesday") == "1",
                wednesday=row.get("wednesday") == "1",
                thursday=row.get("thursday") == "1",
                friday=row.get("friday") == "1",
                saturday=row.get("saturday") == "1",
                sunday=row.get("sunday") == "1",
                start_date=row.get("start_date", ""),
                end_date=row.get("end_date", ""),
            )
            self._calendars[cal.service_id] = cal
    
    def _parse_calendar_dates(self, content: str) -> None:
        """Parse calendar_dates.txt content."""
        self._calendar_dates.clear()
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            cd = GTFSCalendarDate(
                service_id=row["service_id"],
                date=row.get("date", ""),
                exception_type=int(row.get("exception_type", 0) or 0),
            )
            if cd.service_id not in self._calendar_dates:
                self._calendar_dates[cd.service_id] = []
            self._calendar_dates[cd.service_id].append(cd)
    
    def search_stops(self, query: str, limit: int = 20) -> List[GTFSStop]:
        """Search stops by name or code."""
        query_lower = query.lower()
        results = []
        
        for stop in self._stops.values():
            if (query_lower in stop.stop_name.lower() or 
                (stop.stop_code and query_lower in stop.stop_code.lower()) or
                query_lower in stop.stop_id.lower()):
                results.append(stop)
                if len(results) >= limit:
                    break
        
        return results
    
    def get_stop(self, stop_id: str) -> Optional[GTFSStop]:
        """Get a stop by ID."""
        return self._stops.get(stop_id)
    
    def is_service_active(self, service_id: str, check_date: date) -> bool:
        """Check if a service is active on a given date."""
        date_str = check_date.strftime("%Y%m%d")
        
        # Check calendar_dates exceptions first
        if service_id in self._calendar_dates:
            for cd in self._calendar_dates[service_id]:
                if cd.date == date_str:
                    return cd.exception_type == 1  # 1 = added, 2 = removed
        
        # Check regular calendar
        if service_id in self._calendars:
            cal = self._calendars[service_id]
            
            # Check date range
            if cal.start_date and date_str < cal.start_date:
                return False
            if cal.end_date and date_str > cal.end_date:
                return False
            
            # Check day of week
            weekday = check_date.weekday()
            days = [cal.monday, cal.tuesday, cal.wednesday, cal.thursday,
                    cal.friday, cal.saturday, cal.sunday]
            return days[weekday]
        
        return False
    
    def update_realtime(self, rt_url: str) -> bool:
        """
        Fetch and parse real-time updates from GTFS-RT feed.
        
        Populates self._rt_updates with {trip_id: {stop_id: delay_seconds}}.
        Returns True if updates were successfully processed.
        """
        try:
            from google.transit import gtfs_realtime_pb2
            
            # Check throttle (e.g. 30s)
            now = datetime.now()
            if self._rt_last_update and (now - self._rt_last_update).total_seconds() < 30:
                return True  # Considered success (cached)
                
            logger.info(f"Fetching GTFS-RT from {rt_url}")
            response = requests.get(rt_url, timeout=10)
            response.raise_for_status()
            
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            new_updates = {}
            count = 0
            
            for entity in feed.entity:
                if entity.HasField('trip_update'):
                    tu = entity.trip_update
                    trip_id = tu.trip.trip_id
                    
                    # Map stop_id -> delay
                    stop_delays = {}
                    for stu in tu.stop_time_update:
                        if stu.stop_id:
                            # Use arrival delay if available, else departure
                            delay = 0
                            if stu.HasField('arrival'):
                                delay = stu.arrival.delay
                            elif stu.HasField('departure'):
                                delay = stu.departure.delay
                            
                            stop_delays[stu.stop_id] = delay
                    
                    if stop_delays:
                        new_updates[trip_id] = stop_delays
                        count += 1
            
            self._rt_updates = new_updates
            self._rt_last_update = now
            logger.info(f"Processed {count} trip updates")
            return True
            
        except ImportError:
            logger.error("gtfs-realtime-bindings not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to fetch GTFS-RT: {e}")
            return False

    def get_arrivals(self, stop_id: str, limit: int = 10) -> List[dict]:
        """
        Get upcoming arrivals for a stop.
        
        Returns list of arrival dicts sorted by time.
        """
        if stop_id not in self._stop_times:
            return []
        
        now = datetime.now()
        today = now.date()
        current_time = now.strftime("%H:%M:%S")
        
        # Convert current time to seconds for comparison
        current_seconds = self._time_to_seconds(current_time)
        
        arrivals = []
        
        for st in self._stop_times.get(stop_id, []):
            trip = self._trips.get(st.trip_id)
            if not trip:
                continue
            
            # Check if service is active today
            if not self.is_service_active(trip.service_id, today):
                continue
            
            # Parse arrival time
            arrival_seconds = self._time_to_seconds(st.arrival_time)
            
            # Check for Realtime Update
            delay = 0
            is_realtime = False
            
            if trip.trip_id in self._rt_updates:
                trip_updates = self._rt_updates[trip.trip_id]
                if stop_id in trip_updates:
                    delay = trip_updates[stop_id]
                    is_realtime = True
            
            # Apply delay
            arrival_seconds += delay
            
            # Handle times after midnight (>24:00:00) are simply larger values relative to today's midnight
            if arrival_seconds < current_seconds:
                continue  # Already passed
            
            # Calculate minutes away
            minutes_away = (arrival_seconds - current_seconds) // 60
            
            if minutes_away > 60:  # Only show next hour
                continue
            
            route = self._routes.get(trip.route_id)
            
            arrivals.append({
                "route_short_name": route.route_short_name if route else trip.route_id,
                "route_color": route.route_color if route else "000000",
                "headsign": trip.trip_headsign,
                "scheduled_time": st.arrival_time,
                "minutes_away": minutes_away,
                "is_realtime": is_realtime,
                "delay": delay
            })
        
        # Sort by minutes away and limit
        arrivals.sort(key=lambda x: x["minutes_away"])
        return arrivals[:limit]
    
    def _time_to_seconds(self, time_str: str) -> int:
        """Convert HH:MM:SS to seconds since midnight."""
        if not time_str:
            return 0
        try:
            parts = time_str.split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            seconds = int(parts[2]) if len(parts) > 2 else 0
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            return 0


# Global parser instance
_parser: Optional[GTFSParser] = None


def get_gtfs_parser() -> GTFSParser:
    """Get the global GTFS parser instance."""
    global _parser
    if _parser is None:
        _parser = GTFSParser()
    return _parser
