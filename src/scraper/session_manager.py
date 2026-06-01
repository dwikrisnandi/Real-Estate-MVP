"""
Browser Session Manager
=======================
Manages Playwright browser lifecycle: launch, context creation,
cookie persistence, and automatic session recovery.
"""

import json
from pathlib import Path
from typing import Optional
from loguru import logger

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from src.utils.user_agents import get_random_user_agent



class BrowserSessionManager:
    """
    Manages a Playwright browser instance with:
    - Configurable headless/headed mode
    - User-Agent rotation
    - Cookie persistence for session reuse
    - Automatic cleanup on exit
    """

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        user_agent: str = "",
        navigation_timeout: int = 30,
        cookie_file: str = "",
    ):
        self._headless = headless
        self._viewport = {"width": viewport_width, "height": viewport_height}
        self._user_agent = user_agent or get_random_user_agent()
        self._nav_timeout = navigation_timeout * 1000  # Playwright uses ms
        self._cookie_file = cookie_file

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> Page:
        """
        Launch the browser and return a ready-to-use Page.

        Returns:
            A Playwright Page instance.
        """
        logger.info("Launching browser (headless=%s)", self._headless)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
        )

        self._context = await self._browser.new_context(
            viewport=self._viewport,
            user_agent=self._user_agent,
            locale="en-US",
            timezone_id="America/New_York",
            # Reduce bot detection signals
            java_script_enabled=True,
            bypass_csp=False,
        )

        # Set default navigation timeout
        self._context.set_default_navigation_timeout(self._nav_timeout)
        self._context.set_default_timeout(self._nav_timeout)

        # Restore cookies if available
        await self._load_cookies()

        self._page = await self._context.new_page()

        # Block unnecessary resources to speed up scraping
        await self._page.route(
            "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot}",
            lambda route: route.abort(),
        )

        logger.info("Browser ready — UA: %s", self._user_agent[:60] + "...")
        return self._page

    async def save_cookies(self) -> None:
        """Persist current session cookies to disk."""
        if not self._cookie_file or not self._context:
            return

        cookies = await self._context.cookies()
        path = Path(self._cookie_file)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        logger.debug("Saved %d cookies to %s", len(cookies), path)

    async def _load_cookies(self) -> None:
        """Load previously saved cookies into the browser context."""
        if not self._cookie_file or not self._context:
            return

        path = Path(self._cookie_file)
        if not path.exists():
            logger.debug("No cookie file found at %s", path)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            await self._context.add_cookies(cookies)
            logger.info("Restored %d cookies from %s", len(cookies), path)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to load cookies: %s", e)

    async def close(self) -> None:
        """Save cookies and close all browser resources."""
        try:
            await self.save_cookies()
        except Exception as e:
            logger.warning("Error saving cookies on close: %s", e)

        if self._browser:
            await self._browser.close()
            logger.info("Browser closed")

        if self._playwright:
            await self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
