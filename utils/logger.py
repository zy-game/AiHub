import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from config import LOG_LEVEL

def setup_logger(name: str = "aihub") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(console_handler)
        
        # File handler with daily rotation
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # Use current date for log filename
        log_filename = log_dir / f"log_{datetime.now().strftime('%Y_%m_%d')}.log"
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()

def get_provider_logger(provider_name: str) -> logging.Logger:
    """Get a logger for a specific provider"""
    return setup_logger(f"provider.{provider_name}")
