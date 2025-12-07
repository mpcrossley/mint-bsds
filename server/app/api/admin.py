"""
Admin API - Called by admin dashboard.
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Device, DeviceStatus, generate_api_token, GTFSConfig

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


class DeviceResponse(BaseModel):
    """Device info for admin."""
    id: str
    claim_code: str
    status: str
    stop_code: Optional[str]
    stop_name: Optional[str]
    last_seen: Optional[datetime]
    ip_address: Optional[str]
    software_version: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AssignStopRequest(BaseModel):
    """Request to assign a stop to a device."""
    stop_code: str
    stop_name: str


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Render admin dashboard."""
    result = await db.execute(select(Device).order_by(Device.created_at.desc()))
    devices = result.scalars().all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "devices": devices,
    })


@router.get("/devices", response_model=List[DeviceResponse])
async def list_devices(
    db: AsyncSession = Depends(get_db),
):
    """List all registered devices."""
    result = await db.execute(select(Device).order_by(Device.created_at.desc()))
    devices = result.scalars().all()
    
    return [
        DeviceResponse(
            id=str(d.id),
            claim_code=d.claim_code,
            status=d.status.value,
            stop_code=d.stop_code,
            stop_name=d.stop_name,
            last_seen=d.last_seen,
            ip_address=str(d.ip_address) if d.ip_address else None,
            software_version=d.software_version,
            created_at=d.created_at,
        )
        for d in devices
    ]


@router.post("/devices/{device_id}/assign")
async def assign_stop(
    device_id: UUID,
    data: AssignStopRequest,
    db: AsyncSession = Depends(get_db),
):
    """Assign a stop to a device."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Generate API token if not already set
    if not device.api_token:
        device.api_token = generate_api_token()
    
    # Assign stop
    device.stop_code = data.stop_code
    device.stop_name = data.stop_name
    device.status = DeviceStatus.PAIRED
    device.paired_at = datetime.utcnow()
    
    return {
        "status": "ok",
        "device_id": str(device.id),
        "stop_code": device.stop_code,
    }


@router.post("/devices/pair")
async def pair_by_claim_code(
    claim_code: str,
    data: AssignStopRequest,
    db: AsyncSession = Depends(get_db),
):
    """Pair a device using its claim code."""
    result = await db.execute(
        select(Device).where(Device.claim_code == claim_code.upper())
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Generate API token
    device.api_token = generate_api_token()
    device.stop_code = data.stop_code
    device.stop_name = data.stop_name
    device.status = DeviceStatus.PAIRED
    device.paired_at = datetime.utcnow()
    
    return {
        "status": "ok",
        "device_id": str(device.id),
        "claim_code": device.claim_code,
        "stop_code": device.stop_code,
    }


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Remove a device."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    await db.delete(device)
    return {"status": "ok"}


@router.get("/gtfs/config")
async def get_gtfs_config(
    db: AsyncSession = Depends(get_db),
):
    """Get current GTFS configuration."""
    result = await db.execute(select(GTFSConfig).limit(1))
    config = result.scalar_one_or_none()
    
    if not config:
        return {"configured": False}
    
    return {
        "configured": True,
        "gtfs_url": config.gtfs_url,
        "gtfs_rt_url": config.gtfs_rt_url,
        "last_fetched": config.last_fetched,
    }


@router.post("/gtfs/config")
async def set_gtfs_config(
    gtfs_url: str,
    gtfs_rt_url: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Set GTFS source configuration."""
    result = await db.execute(select(GTFSConfig).limit(1))
    config = result.scalar_one_or_none()
    
    if config:
        config.gtfs_url = gtfs_url
        config.gtfs_rt_url = gtfs_rt_url
    else:
        config = GTFSConfig(gtfs_url=gtfs_url, gtfs_rt_url=gtfs_rt_url)
        db.add(config)
    
    return {"status": "ok"}
