# BSDS Configuration Guide

All configuration is stored in `config.json` and can be edited via the web interface at `http://<pi-ip>:5000`.

## Configuration File

```json
{
  "stop_id": "100254",
  "stop_name": "Gorge Rd E at Garbally Rd",
  "refresh_interval_seconds": 60,
  "data_source": {
    "mode": "gtfs",
    "gtfs_url": "https://example.com/gtfs.zip",
    "gtfs_rt_url": "https://example.com/tripupdates.pb",
    "mint_api_url": "http://10.10.1.196:8000",
    "mint_system_id": 1
  },
  "display": {
    "driver": "waveshare_epd.epd7in5_V2",
    "width": 800,
    "height": 480,
    "rotation": 0
  },
  "power": {
    "quiet_hours_start": "23:00",
    "quiet_hours_end": "06:00"
  }
}
```

## Data Source Modes

### GTFS Mode

Uses static GTFS schedule with optional GTFS-RT real-time updates:

| Setting | Description |
|---------|-------------|
| `gtfs_url` | URL to GTFS ZIP file |
| `gtfs_rt_url` | Optional URL to GTFS-RT TripUpdates feed |

```json
{
  "data_source": {
    "mode": "gtfs",
    "gtfs_url": "https://bctransit.com/data/gtfs.zip",
    "gtfs_rt_url": "https://bctransit.com/data/tripupdates.pb"
  }
}
```

### MINT Mode

Uses MINT/MIXRE API for ML-enhanced predictions with GTFS fallback:

| Setting | Description |
|---------|-------------|
| `mint_api_url` | URL to MINT API server |
| `mint_system_id` | Transit system ID (default: 1) |
| `gtfs_url` | Optional fallback GTFS URL |

```json
{
  "data_source": {
    "mode": "mint",
    "mint_api_url": "http://10.10.1.196:8000",
    "mint_system_id": 1,
    "gtfs_url": "https://bctransit.com/data/gtfs.zip"
  }
}
```

When MINT API is unavailable, BSDS falls back to static GTFS schedule automatically.

## Display Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `driver` | Auto-detect | omni-epd driver name |
| `width` | 800 | Display width in pixels |
| `height` | 480 | Display height in pixels  |
| `rotation` | 0 | Rotation (0, 90, 180, 270) |

## Power Management

| Setting | Description |
|---------|-------------|
| `quiet_hours_start` | Time to stop display updates (HH:MM) |
| `quiet_hours_end` | Time to resume display updates (HH:MM) |

During quiet hours, the display keeps the last image but stops refreshing.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BSDS_MOCK_DISPLAY` | Set to `1` to use mock display |
| `BSDS_CONFIG_PATH` | Path to config.json (default: `./config.json`) |
| `BSDS_WEB_PORT` | Web interface port (default: 5000) |

## Command Line Options

```bash
python -m src.main [OPTIONS]

Options:
  --mock          Run with mock display (no hardware)
  --no-web        Disable web interface
  --config PATH   Path to config file
```
