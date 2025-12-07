"""
GTFS API - Serve pruned GTFS data to devices.
"""
import pickle
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Device
from ..services.gtfs_generator import get_gtfs_generator

router = APIRouter()

# Cache directory for generated GTFS files
CACHE_DIR = Path("cache/gtfs")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/light/{stop_code}")
async def get_light_gtfs(
    stop_code: str,
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get pruned GTFS data for a specific stop.
    
    Returns a pickled data file optimized for the stop.
    """
    # Validate token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")
    
    token = authorization[7:]
    result = await db.execute(select(Device).where(Device.api_token == token))
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    if device.stop_code != stop_code:
        raise HTTPException(status_code=403, detail="Stop code mismatch")
    
    # Check cache
    cache_file = CACHE_DIR / f"{stop_code}.pkl"
    
    if not cache_file.exists():
        # Generate GTFS light for this stop
        generator = await get_gtfs_generator(db)
        if not generator:
            raise HTTPException(status_code=503, detail="GTFS not configured")
        
        try:
            data = await generator.generate_for_stop(stop_code)
            with open(cache_file, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate GTFS: {e}")
    
    # Return cached file
    with open(cache_file, "rb") as f:
        content = f.read()
    
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={stop_code}.pkl"}
    )


@router.post("/refresh")
async def refresh_gtfs(
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh GTFS data from source.
    
    Downloads fresh GTFS and clears cache.
    """
    generator = await get_gtfs_generator(db)
    if not generator:
        raise HTTPException(status_code=503, detail="GTFS not configured")
    
    try:
        success = await generator.refresh()
        if success:
            # Clear cache
            for f in CACHE_DIR.glob("*.pkl"):
                f.unlink()
            return {"status": "ok", "message": "GTFS refreshed, cache cleared"}
        else:
            raise HTTPException(status_code=500, detail="Failed to refresh GTFS")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
