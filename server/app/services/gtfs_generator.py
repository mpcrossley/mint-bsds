"""
GTFS Generator - Downloads and prunes GTFS data for specific stops.
"""
import io
import logging
import pickle
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GTFSConfig

logger = logging.getLogger(__name__)

# Global instance
_generator: Optional["GTFSGenerator"] = None


class GTFSGenerator:
    """Generates pruned GTFS data for specific stops."""
    
    def __init__(self, gtfs_url: str, gtfs_rt_url: Optional[str] = None):
        self.gtfs_url = gtfs_url
        self.gtfs_rt_url = gtfs_rt_url
        self._data: Dict[str, Any] = {}
        self._loaded = False
    
    async def refresh(self) -> bool:
        """Download and parse GTFS data."""
        logger.info(f"Downloading GTFS from {self.gtfs_url}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.gtfs_url, timeout=60)
                response.raise_for_status()
                
            # Parse GTFS ZIP
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                self._data = self._parse_gtfs(zf)
                
            self._loaded = True
            logger.info(f"GTFS loaded: {len(self._data.get('stops', {}))} stops")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load GTFS: {e}")
            return False
    
    def _parse_gtfs(self, zf: zipfile.ZipFile) -> Dict[str, Any]:
        """Parse GTFS files into data structures."""
        data = {
            "stops": {},
            "routes": {},
            "trips": {},
            "stop_times": {},
            "calendar": {},
            "calendar_dates": {},
        }
        
        # Parse stops.txt
        if "stops.txt" in zf.namelist():
            content = zf.read("stops.txt").decode("utf-8-sig")
            for row in self._parse_csv(content):
                data["stops"][row["stop_id"]] = row
        
        # Parse routes.txt
        if "routes.txt" in zf.namelist():
            content = zf.read("routes.txt").decode("utf-8-sig")
            for row in self._parse_csv(content):
                data["routes"][row["route_id"]] = row
        
        # Parse trips.txt
        if "trips.txt" in zf.namelist():
            content = zf.read("trips.txt").decode("utf-8-sig")
            for row in self._parse_csv(content):
                data["trips"][row["trip_id"]] = row
        
        # Parse stop_times.txt
        if "stop_times.txt" in zf.namelist():
            content = zf.read("stop_times.txt").decode("utf-8-sig")
            for row in self._parse_csv(content):
                stop_id = row["stop_id"]
                if stop_id not in data["stop_times"]:
                    data["stop_times"][stop_id] = []
                data["stop_times"][stop_id].append(row)
        
        # Parse calendar.txt
        if "calendar.txt" in zf.namelist():
            content = zf.read("calendar.txt").decode("utf-8-sig")
            for row in self._parse_csv(content):
                data["calendar"][row["service_id"]] = row
        
        # Parse calendar_dates.txt
        if "calendar_dates.txt" in zf.namelist():
            content = zf.read("calendar_dates.txt").decode("utf-8-sig")
            for row in self._parse_csv(content):
                service_id = row["service_id"]
                if service_id not in data["calendar_dates"]:
                    data["calendar_dates"][service_id] = []
                data["calendar_dates"][service_id].append(row)
        
        return data
    
    def _parse_csv(self, content: str):
        """Simple CSV parser."""
        lines = content.strip().split("\n")
        if not lines:
            return
        
        headers = [h.strip() for h in lines[0].split(",")]
        for line in lines[1:]:
            values = line.split(",")
            if len(values) >= len(headers):
                yield dict(zip(headers, [v.strip() for v in values[:len(headers)]]))
    
    async def generate_for_stop(self, stop_code: str) -> Dict[str, Any]:
        """Generate pruned GTFS data for a specific stop."""
        if not self._loaded:
            await self.refresh()
        
        if not self._loaded:
            raise RuntimeError("GTFS data not available")
        
        # Find stop by stop_code
        target_stop = None
        for stop_id, stop in self._data["stops"].items():
            if stop.get("stop_code") == stop_code or stop_id == stop_code:
                target_stop = stop
                break
        
        if not target_stop:
            raise ValueError(f"Stop {stop_code} not found")
        
        target_stop_id = target_stop.get("stop_id")
        
        # Get stop times for this stop
        stop_times = self._data["stop_times"].get(target_stop_id, [])
        
        # Get trips that serve this stop
        trip_ids = set(st["trip_id"] for st in stop_times)
        trips = {tid: self._data["trips"][tid] for tid in trip_ids if tid in self._data["trips"]}
        
        # Get routes for those trips
        route_ids = set(t.get("route_id") for t in trips.values())
        routes = {rid: self._data["routes"][rid] for rid in route_ids if rid in self._data["routes"]}
        
        # Get service IDs for calendar
        service_ids = set(t.get("service_id") for t in trips.values())
        calendar = {sid: self._data["calendar"][sid] for sid in service_ids if sid in self._data["calendar"]}
        calendar_dates = {
            sid: self._data["calendar_dates"].get(sid, []) 
            for sid in service_ids
        }
        
        return {
            "stop": target_stop,
            "stop_times": stop_times,
            "trips": trips,
            "routes": routes,
            "calendar": calendar,
            "calendar_dates": calendar_dates,
            "gtfs_rt_url": self.gtfs_rt_url,
            "generated_at": datetime.utcnow().isoformat(),
        }
    
    def search_stops(self, query: str, limit: int = 20):
        """Search stops by name or code."""
        if not self._loaded:
            return []
        
        query_lower = query.lower()
        results = []
        
        for stop_id, stop in self._data["stops"].items():
            name = stop.get("stop_name", "").lower()
            code = stop.get("stop_code", "").lower()
            
            if query_lower in name or query_lower in code or query_lower in stop_id.lower():
                results.append(stop)
                if len(results) >= limit:
                    break
        
        return results


async def get_gtfs_generator(db: AsyncSession) -> Optional[GTFSGenerator]:
    """Get or create GTFS generator from database config."""
    global _generator
    
    result = await db.execute(select(GTFSConfig).limit(1))
    config = result.scalar_one_or_none()
    
    if not config:
        return None
    
    if _generator is None or _generator.gtfs_url != config.gtfs_url:
        _generator = GTFSGenerator(config.gtfs_url, config.gtfs_rt_url)
    
    return _generator
