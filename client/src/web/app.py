"""
Flask web application for BSDS configuration.

Provides a web interface for:
- Searching and selecting stops
- Configuring data source (GTFS or MINT)
- Previewing the display
- Adjusting settings
"""

import io
import logging
from flask import Flask, jsonify, render_template, request, send_file

from ..config import get_config_manager
from ..display_driver import get_display_driver
from ..renderer import get_renderer
from ..schedule_provider import (
    get_schedule_provider, 
    reset_provider, 
    ArrivalsResponse,
    Stop,
    Arrival,
)

logger = logging.getLogger(__name__)

app = Flask(__name__, 
            template_folder="templates",
            static_folder="static")


@app.route("/")
def index():
    """Render the main configuration page."""
    config = get_config_manager().config
    return render_template("index.html", config=config)


@app.route("/api/config", methods=["GET"])
def get_config_api():
    """Get current configuration."""
    config = get_config_manager().config
    return jsonify(config.to_dict())


@app.route("/api/config", methods=["POST"])
def update_config():
    """Update configuration."""
    data = request.json
    manager = get_config_manager()
    
    # Update stop fields
    if "stop_id" in data:
        manager.config.stop_id = str(data["stop_id"]) if data["stop_id"] else None
    if "stop_name" in data:
        manager.config.stop_name = data["stop_name"]
    if "refresh_interval_seconds" in data:
        manager.config.refresh_interval_seconds = int(data["refresh_interval_seconds"])
    if "quiet_hours_start" in data:
        manager.config.power.quiet_hours_start = data["quiet_hours_start"] or None
    if "quiet_hours_end" in data:
        manager.config.power.quiet_hours_end = data["quiet_hours_end"] or None
    
    manager.save()
    
    return jsonify({"success": True, "config": manager.config.to_dict()})


@app.route("/api/config/data-source", methods=["POST"])
def update_data_source():
    """Update data source configuration."""
    data = request.json
    manager = get_config_manager()
    ds = manager.config.data_source
    
    # Update data source fields
    if "mode" in data:
        ds.mode = data["mode"]
    if "gtfs_url" in data:
        ds.gtfs_url = data["gtfs_url"] or None
    if "gtfs_rt_url" in data:
        ds.gtfs_rt_url = data["gtfs_rt_url"] or None
    if "mint_api_url" in data:
        ds.mint_api_url = data["mint_api_url"]
    if "mint_system_id" in data:
        ds.mint_system_id = int(data["mint_system_id"])
    
    # Clear selected stop when switching modes
    if "mode" in data:
        manager.config.stop_id = None
        manager.config.stop_name = None
    
    manager.save()
    
    # Reset provider to pick up new config
    reset_provider()
    
    return jsonify({"success": True, "config": manager.config.to_dict()})


@app.route("/api/gtfs/refresh", methods=["POST"])
def refresh_gtfs():
    """Download and refresh GTFS data."""
    config = get_config_manager().config
    
    if config.data_source.mode != "gtfs":
        return jsonify({"success": False, "error": "Not in GTFS mode"})
    
    if not config.data_source.gtfs_url:
        return jsonify({"success": False, "error": "No GTFS URL configured"})
    
    try:
        provider = get_schedule_provider()
        success = provider.refresh()
        
        if success:
            return jsonify({
                "success": True,
                "message": "GTFS data refreshed successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to download or parse GTFS data"
            })
    except Exception as e:
        logger.error(f"GTFS refresh failed: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/gtfs/status")
def gtfs_status():
    """Get GTFS data status."""
    config = get_config_manager().config
    
    if config.data_source.mode != "gtfs":
        return jsonify({"mode": "mint"})
    
    from ..gtfs_parser import get_gtfs_parser
    parser = get_gtfs_parser()
    
    return jsonify({
        "mode": "gtfs",
        "loaded": parser.is_loaded(),
        "needs_refresh": parser.needs_refresh(),
        "url": config.data_source.gtfs_url,
        "stops_count": len(parser._stops) if parser.is_loaded() else 0,
        "routes_count": len(parser._routes) if parser.is_loaded() else 0,
    })


@app.route("/api/stops/search")
def search_stops():
    """Search for stops by name or code."""
    query = request.args.get("q", "")
    if len(query) < 2:
        return jsonify([])
    
    try:
        provider = get_schedule_provider()
        
        # Make sure GTFS is loaded if in GTFS mode
        if not provider.is_ready():
            config = get_config_manager().config
            if config.data_source.mode == "gtfs":
                return jsonify({"error": "GTFS data not loaded. Please configure and download GTFS first."}), 400
        
        stops = provider.search_stops(query, limit=10)
        return jsonify([
            {
                "id": s.stop_id,
                "stop_code": s.stop_code,
                "stop_name": s.stop_name,
            }
            for s in stops
        ])
    except Exception as e:
        logger.error(f"Stop search failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/preview")
def get_preview():
    """Get the current display preview as PNG."""
    config = get_config_manager().config
    renderer = get_renderer()
    
    if config.stop_id is None:
        # No stop configured - show placeholder
        image = renderer.render_placeholder()
    else:
        # Fetch arrivals and render
        try:
            provider = get_schedule_provider()
            arrivals = provider.get_arrivals(config.stop_id)
            image = renderer.render(arrivals)
        except Exception as e:
            logger.error(f"Failed to render preview: {e}")
            image = renderer.render_placeholder(f"Error: {str(e)[:50]}")
    
    # Convert to PNG bytes
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    
    return send_file(buffer, mimetype="image/png")


@app.route("/api/refresh", methods=["POST"])
def trigger_refresh():
    """Trigger a manual display refresh."""
    config = get_config_manager().config
    
    if config.stop_id is None:
        return jsonify({"success": False, "error": "No stop configured"})
    
    try:
        # Fetch and render
        provider = get_schedule_provider()
        arrivals = provider.get_arrivals(config.stop_id)
        
        renderer = get_renderer()
        image = renderer.render(arrivals)
        
        # Update display
        driver = get_display_driver()
        driver.display(image)
        
        return jsonify({
            "success": True,
            "arrivals_count": len(arrivals.arrivals),
            "is_connected": arrivals.is_connected,
        })
    except Exception as e:
        logger.error(f"Refresh failed: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/status")
def get_status():
    """Get system status."""
    config = get_config_manager().config
    driver = get_display_driver()
    provider = get_schedule_provider()
    
    return jsonify({
        "stop_configured": config.stop_id is not None,
        "stop_name": config.stop_name,
        "mock_mode": driver.mock,
        "refresh_interval": config.refresh_interval_seconds,
        "data_source_mode": config.data_source.mode,
        "provider_ready": provider.is_ready(),
    })


def run_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Run the Flask development server."""
    app.run(host=host, port=port, debug=debug, threaded=True)
