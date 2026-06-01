"""
Enterprise Logger Setup
=======================
Configures structured, high-performance logging using Loguru.
Features:
- Console output with rich colors
- File output with automated rotation and retention
- JSON serialization for log aggregators (Elasticsearch/Datadog)
"""

import sys
from pathlib import Path
from loguru import logger

def setup_logger(
    name: str,
    log_dir: str = "./logs",
    level: str = "INFO",
    log_to_file: bool = True,
    json_format: bool = False
):
    """
    Configures Loguru globally for the application.

    Args:
        name:        Logger application name (added to context).
        log_dir:     Directory to store log files.
        level:       Minimum log level (DEBUG, INFO, WARNING, ERROR).
        log_to_file: Whether to write logs to disk.
        json_format: Whether to output logs in JSON format for external parsing.
    """
    # Remove default handler
    logger.remove()

    # Determine console formatting
    if json_format:
        console_format = "{message}"
    else:
        console_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

    # Add Console Handler
    logger.add(
        sys.stderr,
        level=level.upper(),
        format=console_format,
        colorize=not json_format,
        serialize=json_format
    )

    # Add File Handler (Enterprise rotation & retention)
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        file_path = log_path / f"{name}_{{time:YYYYMMDD}}.log"
        
        logger.add(
            str(file_path),
            level="DEBUG", # Always save debug logs to file for troubleshooting
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            serialize=json_format
        )
    
    # Bind the app name context
    return logger.bind(app=name)
