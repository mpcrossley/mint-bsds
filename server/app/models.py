"""
SQLAlchemy models for BSDS server.
"""
import uuid
import secrets
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import String, DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class DeviceStatus(PyEnum):
    """Device status enum."""
    PENDING = "pending"      # Registered but not paired
    PAIRED = "paired"        # Paired with stop but not yet confirmed active
    ACTIVE = "active"        # Operating normally
    OFFLINE = "offline"      # No heartbeat received


def generate_claim_code() -> str:
    """Generate a 6-character alphanumeric claim code."""
    # Use only uppercase letters and digits, avoiding ambiguous chars (0, O, I, 1, L)
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def generate_api_token() -> str:
    """Generate a secure API token."""
    return secrets.token_urlsafe(32)


class Device(Base):
    """Registered display device."""
    __tablename__ = "devices"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    claim_code: Mapped[str] = mapped_column(
        String(6), 
        unique=True, 
        default=generate_claim_code
    )
    api_token: Mapped[Optional[str]] = mapped_column(
        String(64), 
        nullable=True
    )
    serial_number: Mapped[Optional[str]] = mapped_column(
        String(32), 
        nullable=True
    )
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus), 
        default=DeviceStatus.PENDING
    )
    
    # Stop assignment
    stop_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    stop_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Monitoring
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    software_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now()
    )
    paired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class GTFSConfig(Base):
    """GTFS source configuration."""
    __tablename__ = "gtfs_configs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    gtfs_url: Mapped[str] = mapped_column(String(500))
    gtfs_rt_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_fetched: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
