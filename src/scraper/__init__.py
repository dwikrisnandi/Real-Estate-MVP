"""
Scraper Module
==============
Web scraper for extracting usernames from membership platforms.
"""

from src.scraper.base import BaseScraper
from src.scraper.platform_scraper import PlatformScraper
from src.scraper.session_manager import BrowserSessionManager

__all__ = ["BaseScraper", "PlatformScraper", "BrowserSessionManager"]
