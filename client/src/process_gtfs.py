"""
Script to pre-process GTFS data on a host machine.

Downloads the GTFS ZIP, parses it, and then "prunes" it to only include
data relevant to the configured stop ID. This creates a tiny cache file
that can be transferred to the Raspberry Pi.
"""

import logging
import sys
from pathlib import Path

# Add src to path if needed to run as script
sys.path.append(str(Path(__file__).parent.parent))

from src.config import get_config
from src.gtfs_parser import get_gtfs_parser, CACHE_FILE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("process_gtfs")

def main():
    logger.info("Starting GTFS Pre-processing...")
    
    # 1. Load Config
    config = get_config()
    stop_id = config.stop_id
    gtfs_url = config.data_source.gtfs_url
    
    if not gtfs_url:
        logger.error("Error: No GTFS URL configured in config.json")
        sys.exit(1)
        
    if not stop_id:
        logger.warning("Warning: No stop_id configured in config.json")
        logger.warning("Will download full GTFS but CANNOT prune it.")
    
    # 2. Initialize Parser
    parser = get_gtfs_parser()
    parser.set_url(gtfs_url)
    
    # 3. Download and Parse (Full)
    logger.info("Downloading and parsing full GTFS...")
    if not parser.download_and_parse():
        logger.error("Failed to download/parse GTFS")
        sys.exit(1)
        
    # Check size of full cache
    if CACHE_FILE.exists():
        size_mb = CACHE_FILE.stat().st_size / (1024 * 1024)
        logger.info(f"Full cache size: {size_mb:.2f} MB")
        
    # 4. Prune Data
    if stop_id:
        logger.info(f"Pruning data for stop_id: {stop_id}")
        removed = parser.prune_data([stop_id])
        
        # 5. Save Pruned Cache
        logger.info("Saving pruned cache...")
        if parser.save_cache():
            size_mb = CACHE_FILE.stat().st_size / (1024 * 1024)
            size_kb = CACHE_FILE.stat().st_size / 1024
            logger.info(f"Pruned cache saved successfully!")
            logger.info(f"New cache size: {size_kb:.2f} KB ({size_mb:.2f} MB)")
            logger.info("-" * 40)
            logger.info("Next steps:")
            logger.info("1. Copy the cache folder to your Pi:")
            logger.info("   rsync -avz cache/ mcrossley@<pi-ip>:~/bsds/cache/")
        else:
            logger.error("Failed to save pruned cache")
    else:
        logger.info("Skipped pruning (no stop_id)")

if __name__ == "__main__":
    main()
