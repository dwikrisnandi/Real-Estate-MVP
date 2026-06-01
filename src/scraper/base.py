"""
Base Scraper (Abstract)
=======================
Defines the interface that all platform scrapers must implement.
Enforces consistent structure across different platform adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScrapedUser:
    """Represents a single scraped user profile."""
    username: str
    display_name: Optional[str] = None
    profile_url: Optional[str] = None
    scraped_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "display_name": self.display_name or "",
            "profile_url": self.profile_url or "",
            "scraped_at": self.scraped_at,
        }


@dataclass
class ScrapeResult:
    """Container for a full scrape operation result."""
    users: list[ScrapedUser] = field(default_factory=list)
    pages_scraped: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0

    def finalize(self, start_time: float) -> None:
        """Mark the result as complete with timing info."""
        import time
        self.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.duration_seconds = round(time.time() - start_time, 2)

    @property
    def success(self) -> bool:
        return len(self.users) > 0


class BaseScraper(ABC):
    """
    Abstract base class for platform scrapers.

    Subclass this to implement scraping for a specific platform.
    The interface enforces:
      1. Authentication (if required)
      2. Scraping logic
      3. Clean shutdown
    """

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Login to the platform if authentication is required.

        Returns:
            True if login succeeded or no login needed, False otherwise.
        """
        ...

    @abstractmethod
    async def scrape(self) -> ScrapeResult:
        """
        Execute the scraping operation.

        Returns:
            A ScrapeResult containing all extracted users and metadata.
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up browser resources and sessions."""
        ...
