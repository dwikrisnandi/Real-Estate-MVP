"""
Platform Scraper
================
Concrete scraper implementation that navigates membership platform
pages and extracts publicly visible usernames.

Supports three pagination strategies:
  - scroll:    Infinite scroll (lazy-loaded content)
  - click:     "Next page" / "Load more" button
  - url_param: Page number in the URL query string
"""

import asyncio
import time
from typing import Optional
from urllib.parse import urljoin
from loguru import logger

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.core import Config
from src.scraper.base import BaseScraper, ScrapedUser, ScrapeResult
from src.scraper.session_manager import BrowserSessionManager
from src.utils.rate_limiter import RateLimiter, RateLimiterConfig
from src.utils.decorators import with_retry, safe_execute



class PlatformScraper(BaseScraper):
    """
    Scrapes usernames from a membership platform page.

    Configurable via YAML — selectors, auth flow, pagination,
    and rate limits are all defined in the config file.
    """

    def __init__(self, config: Config):
        self._config = config
        self._session: Optional[BrowserSessionManager] = None
        self._page: Optional[Page] = None

        # Build rate limiter from config
        rl_cfg = RateLimiterConfig(
            min_delay=config.get("rate_limit", "min_delay_seconds", default=1.5),
            max_delay=config.get("rate_limit", "max_delay_seconds", default=4.0),
            backoff_multiplier=config.get("rate_limit", "backoff_multiplier", default=2.0),
            max_backoff=config.get("rate_limit", "max_backoff_seconds", default=60.0),
        )
        self._rate_limiter = RateLimiter(rl_cfg)

    async def _init_browser(self) -> None:
        """Initialize the browser session."""
        browser_cfg = self._config.get("browser") or {}
        self._session = BrowserSessionManager(
            headless=browser_cfg.get("headless", True),
            viewport_width=browser_cfg.get("viewport_width", 1920),
            viewport_height=browser_cfg.get("viewport_height", 1080),
            user_agent=browser_cfg.get("user_agent", ""),
            navigation_timeout=browser_cfg.get("navigation_timeout", 30),
            cookie_file="./data/cookies_scraper.json",
        )
        self._page = await self._session.start()

    # ──────────────────────────────────────────
    # Authentication
    # ──────────────────────────────────────────
    @with_retry(max_retries=3, delay=5.0, exceptions=(PlaywrightTimeout, Exception))
    async def authenticate(self) -> bool:
        """
        Login to the platform using credentials from the config.
        Skipped if auth.required is False.
        """
        auth_cfg = self._config.get("auth") or {}
        if not auth_cfg.get("required", False):
            logger.info("Authentication not required — skipping login")
            return True

        login_url = auth_cfg.get("login_url", "")
        creds = auth_cfg.get("credentials", {})
        selectors = auth_cfg.get("selectors", {})

        if not login_url or not creds.get("username") or not creds.get("password"):
            logger.error("Auth is required but credentials are missing in config")
            return False

        logger.info("Navigating to login page: %s", login_url)

        try:
            await self._page.goto(login_url, wait_until="networkidle")

            # Type credentials with human-like delays
            username_field = await self._page.wait_for_selector(
                selectors.get("username_field", "input[name='email']"),
                timeout=10000,
            )
            await username_field.click()
            await username_field.type(creds["username"], delay=80)

            password_field = await self._page.wait_for_selector(
                selectors.get("password_field", "input[name='password']"),
                timeout=5000,
            )
            await password_field.click()
            await password_field.type(creds["password"], delay=80)

            # Submit the form
            submit_btn = await self._page.wait_for_selector(
                selectors.get("submit_button", "button[type='submit']"),
                timeout=5000,
            )
            await submit_btn.click()

            # Wait for login to complete
            post_wait = auth_cfg.get("post_login_wait", 3)
            await asyncio.sleep(post_wait)
            await self._page.wait_for_load_state("networkidle")

            # Save session cookies
            await self._session.save_cookies()

            logger.info("[OK] Login successful")
            return True

        except PlaywrightTimeout:
            logger.error("[FAIL] Login failed -- timed out waiting for form elements")
            return False
        except Exception as e:
            logger.error("[FAIL] Login failed: %s", e)
            return False

    # ──────────────────────────────────────────
    # Scraping
    # ──────────────────────────────────────────
    async def scrape(self) -> ScrapeResult:
        """
        Execute the full scrape operation.

        Flow:
          1. Launch browser
          2. Authenticate (if required)
          3. Navigate to target page
          4. Extract usernames using configured pagination strategy
          5. Return deduplicated results
        """
        start_time = time.time()
        result = ScrapeResult()

        try:
            # Init browser
            await self._init_browser()

            # Authenticate
            if not await self.authenticate():
                result.errors.append("Authentication failed")
                result.finalize(start_time)
                return result

            # Navigate to target
            base_url = self._config.require("target", "base_url")
            logger.info("Navigating to target: %s", base_url)
            await self._page.goto(base_url, wait_until="networkidle")

            # Determine pagination strategy
            pagination = self._config.get("target", "pagination") or {}
            strategy = pagination.get("strategy", "none")

            logger.info("Using pagination strategy: %s", strategy)

            if strategy == "scroll":
                users = await self._scrape_with_scroll(pagination)
            elif strategy == "url_param":
                users = await self._scrape_with_url_params(base_url, pagination)
            elif strategy == "click":
                users = await self._scrape_with_click(pagination)
            else:
                users = await self._extract_users_from_page()

            # Deduplicate
            seen = set()
            for user in users:
                key = user.username.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    result.users.append(user)

            result.pages_scraped = self._rate_limiter.actions_performed or 1

        except Exception as e:
            logger.error("Scrape failed with error: %s", e, exc_info=True)
            result.errors.append(str(e))

        finally:
            result.finalize(start_time)

        logger.info(
            "Scrape complete: %d users in %.1fs (%d pages, %d errors)",
            len(result.users),
            result.duration_seconds,
            result.pages_scraped,
            len(result.errors),
        )
        return result

    # ── Pagination: Infinite Scroll ──
    async def _scrape_with_scroll(self, pagination: dict) -> list[ScrapedUser]:
        """Handle infinite scroll / lazy-loaded pages."""
        max_scrolls = pagination.get("max_scrolls", 100)
        scroll_delay = pagination.get("scroll_delay", 2.0)
        all_users: list[ScrapedUser] = []
        previous_count = 0
        no_change_count = 0

        for i in range(1, max_scrolls + 1):
            # Extract current page users
            users = await self._extract_users_from_page()
            all_users = users  # Full re-extract (includes newly loaded)

            logger.info(
                "Scroll %d/%d — %d users found so far",
                i, max_scrolls, len(all_users),
            )

            # Check if new content loaded
            if len(all_users) == previous_count:
                no_change_count += 1
                if no_change_count >= 3:
                    logger.info("No new content after 3 scrolls — assuming end")
                    break
            else:
                no_change_count = 0

            previous_count = len(all_users)

            # Scroll down
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(scroll_delay)

            self._rate_limiter.wait()

        return all_users

    # ── Pagination: URL Parameter ──
    async def _scrape_with_url_params(
        self, base_url: str, pagination: dict
    ) -> list[ScrapedUser]:
        """Handle page-number-in-URL pagination."""
        max_pages = pagination.get("max_pages", 50)
        param_name = pagination.get("param_name", "page")
        all_users: list[ScrapedUser] = []

        for page_num in range(1, max_pages + 1):
            # Build URL
            separator = "&" if "?" in base_url else "?"
            url = f"{base_url}{separator}{param_name}={page_num}"

            logger.info("Fetching page %d: %s", page_num, url)
            await self._page.goto(url, wait_until="networkidle")

            users = await self._extract_users_from_page()

            if not users:
                logger.info("No users on page %d — stopping", page_num)
                break

            all_users.extend(users)
            logger.info("Page %d: %d users (total: %d)", page_num, len(users), len(all_users))

            self._rate_limiter.wait()

        return all_users

    # ── Pagination: Click "Load More" ──
    async def _scrape_with_click(self, pagination: dict) -> list[ScrapedUser]:
        """Handle 'Load More' or 'Next Page' button pagination."""
        max_pages = pagination.get("max_pages", 50)
        button_selector = pagination.get("button_selector", "button.load-more")
        all_users: list[ScrapedUser] = []

        for page_num in range(1, max_pages + 1):
            users = await self._extract_users_from_page()
            all_users = users

            logger.info("Page %d: %d users total", page_num, len(all_users))

            # Try to click the "load more" button
            try:
                button = await self._page.wait_for_selector(
                    button_selector, timeout=5000
                )
                if button:
                    await button.click()
                    await self._page.wait_for_load_state("networkidle")
                else:
                    logger.info("Load more button not found — stopping")
                    break
            except PlaywrightTimeout:
                logger.info("No more pages to load")
                break

            self._rate_limiter.wait()

        return all_users

    # ── Core extraction logic ──
    @with_retry(max_retries=2, delay=2.0)
    async def _extract_users_from_page(self) -> list[ScrapedUser]:
        """Extract user data from the current page using configured selectors."""
        selectors = self._config.get("target", "selectors") or {}
        container_sel = selectors.get("user_container", ".member-card")
        username_sel = selectors.get("username", ".member-username")
        display_sel = selectors.get("display_name", "")
        link_sel = selectors.get("profile_link", "")

        base_url = self._config.get("target", "base_url", default="")
        users: list[ScrapedUser] = []

        containers = await self._page.query_selector_all(container_sel)

        for container in containers:
            try:
                # Username (required)
                username_el = await container.query_selector(username_sel)
                if not username_el:
                    continue
                username = (await username_el.inner_text()).strip()
                if not username:
                    continue

                # Display name (optional)
                display_name = None
                if display_sel:
                    dn_el = await container.query_selector(display_sel)
                    if dn_el:
                        display_name = (await dn_el.inner_text()).strip()

                # Profile link (optional)
                profile_url = None
                if link_sel:
                    link_el = await container.query_selector(link_sel)
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href:
                            profile_url = urljoin(base_url, href)

                users.append(ScrapedUser(
                    username=username,
                    display_name=display_name,
                    profile_url=profile_url,
                ))

            except Exception as e:
                logger.debug("Error extracting user from container: %s", e)
                continue

        return users

    # ──────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────
    async def shutdown(self) -> None:
        """Close browser and release resources."""
        if self._session:
            await self._session.close()
            logger.info("Browser session closed")
