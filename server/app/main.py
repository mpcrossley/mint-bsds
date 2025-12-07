"""
BSDS Server - Central management for bus stop displays.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import init_db
from .api import devices, admin, gtfs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="BSDS Server",
    description="Central management for bus stop display devices",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# Include API routers
app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(gtfs.router, prefix="/api/gtfs", tags=["gtfs"])


@app.get("/")
async def root():
    """Redirect to admin dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
