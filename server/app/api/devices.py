"""
Device API - Called by Pi devices for registration and updates.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Device, DeviceStatus, generate_api_token

router = APIRouter()


class RegisterRequest(BaseModel):
    """Device registration request."""
    claim_code: str
    serial_number: Optional[str] = None


class RegisterResponse(BaseModel):
    """Device registration response."""
    status: str
    poll_interval: int = 10


class StatusResponse(BaseModel):
    """Device status response."""
    status: str
    api_token: Optional[str] = None
    stop_code: Optional[str] = None
    stop_name: Optional[str] = None
    gtfs_url: Optional[str] = None


class HeartbeatRequest(BaseModel):
    """Device heartbeat request."""
    software_version: Optional[str] = None


@router.post("/register", response_model=RegisterResponse)
async def register_device(
    request: Request,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new device with a claim code.
    
    Called by Pi on first boot after generating a claim code.
    """
    # Check if claim code already exists
    result = await db.execute(
        select(Device).where(Device.claim_code == data.claim_code.upper())
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        return RegisterResponse(
            status=existing.status.value,
            poll_interval=10,
        )
    
    # Create new device
    device = Device(
        claim_code=data.claim_code.upper(),
        serial_number=data.serial_number,
        ip_address=request.client.host if request.client else None,
        last_seen=datetime.utcnow(),
    )
    db.add(device)
    await db.flush()
    
    return RegisterResponse(
        status="pending",
        poll_interval=10,
    )


@router.get("/status", response_model=StatusResponse)
async def get_status(
    claim_code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Poll for device status.
    
    Called by Pi to check if it has been paired.
    """
    result = await db.execute(
        select(Device).where(Device.claim_code == claim_code.upper())
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    response = StatusResponse(status=device.status.value)
    
    if device.status in (DeviceStatus.PAIRED, DeviceStatus.ACTIVE):
        response.api_token = device.api_token
        response.stop_code = device.stop_code
        response.stop_name = device.stop_name
    
    return response


@router.post("/heartbeat")
async def heartbeat(
    request: Request,
    data: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str = None,
):
    """
    Device heartbeat - report health and get updates.
    
    Called periodically by paired devices.
    """
    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")
    
    token = auth_header[7:]
    
    result = await db.execute(
        select(Device).where(Device.api_token == token)
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Update device status
    device.last_seen = datetime.utcnow()
    device.ip_address = request.client.host if request.client else None
    device.status = DeviceStatus.ACTIVE
    if data.software_version:
        device.software_version = data.software_version
    
    return {
        "status": "ok",
        "stop_code": device.stop_code,
        "stop_name": device.stop_name,
    }
