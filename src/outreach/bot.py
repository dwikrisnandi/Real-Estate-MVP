"""
Outreach Bot
============
Core outreach engine that logs into the creator account,
reads the scraped user list, and sends personalized messages
via the platform's native messaging interface.

Safety features:
  - Configurable rate limiting with human-like timing
  - Daily / hourly message caps
  - Skip already-messaged users
  - Full audit logging (who was messaged, when, status)
  - Automatic session recovery
  - Graceful shutdown on errors
"""

import asyncio
import time
from datetime import datetime
from typing import Optional
from loguru import logger

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.core import Config
from src.outreach.message_handler import MessageHandler
from src.scraper.session_manager import BrowserSessionManager
from src.utils.csv_handler import CSVHandler
from src.utils.rate_limiter import RateLimiter, RateLimiterConfig, RateLimitExceeded
from src.utils.decorators import with_retry, safe_execute



class OutreachBot:
    """
    Automated outreach bot for membership platforms.

    Workflow:
      1. Load config and message template
      2. Read the scraped user list (CSV)
      3. Filter out already-messaged users
      4. Login to the creator account
      5. Sequentially message each user with rate limiting
      6. Log every action to the audit trail
    """

    def __init__(self, config: Config):
        self._config = config
        self._session: Optional[BrowserSessionManager] = None
        self._page: Optional[Page] = None
        self._message_handler: Optional[MessageHandler] = None

        # Build rate limiter from config
        rl = config.get("rate_limit") or {}
        rl_cfg = RateLimiterConfig(
            min_delay=rl.get("min_delay_seconds", 30),
            max_delay=rl.get("max_delay_seconds", 90),
            jitter=rl.get("jitter", True),
            max_per_hour=rl.get("messages_per_hour", 15),
            max_per_day=rl.get("daily_limit", 50),
            batch_size=rl.get("batch_size", 5),
            batch_pause_seconds=rl.get("batch_pause_minutes", 10) * 60,
        )
        self._rate_limiter = RateLimiter(rl_cfg)

        # Stats
        self._sent = 0
        self._failed = 0
        self._skipped = 0

    # ──────────────────────────────────────────
    # Browser & Auth
    # ──────────────────────────────────────────
    async def _init_browser(self) -> None:
        """Launch browser session."""
        browser_cfg = self._config.get("browser") or {}
        self._session = BrowserSessionManager(
            headless=browser_cfg.get("headless", True),
            viewport_width=browser_cfg.get("viewport_width", 1920),
            viewport_height=browser_cfg.get("viewport_height", 1080),
            navigation_timeout=browser_cfg.get("navigation_timeout", 30),
            cookie_file="./data/cookies_outreach.json",
        )
        self._page = await self._session.start()

    @with_retry(max_retries=3, delay=5.0, exceptions=(PlaywrightTimeout, Exception))
    async def _login(self) -> bool:
        """Login to the creator account."""
        account = self._config.get("account") or {}
        login_url = account.get("login_url", "")
        creds = account.get("credentials", {})
        selectors = account.get("selectors", {})

        if not login_url or not creds.get("username"):
            logger.error("Account credentials missing in config")
            return False

        logger.info("Logging into creator account at %s", login_url)

        try:
            await self._page.goto(login_url, wait_until="networkidle")

            # Fill credentials with human-like typing
            username_field = await self._page.wait_for_selector(
                selectors.get("username_field", "input[name='email']"),
                timeout=10000,
            )
            await username_field.click()
            await username_field.type(creds["username"], delay=100)

            password_field = await self._page.wait_for_selector(
                selectors.get("password_field", "input[name='password']"),
                timeout=5000,
            )
            await password_field.click()
            await password_field.type(creds["password"], delay=100)

            submit = await self._page.wait_for_selector(
                selectors.get("submit_button", "button[type='submit']"),
                timeout=5000,
            )
            await submit.click()

            post_wait = account.get("post_login_wait", 3)
            await asyncio.sleep(post_wait)
            await self._page.wait_for_load_state("networkidle")

            await self._session.save_cookies()
            logger.info("[OK] Creator account login successful")
            return True

        except PlaywrightTimeout:
            logger.error("[FAIL] Login timed out")
            return False
        except Exception as e:
            logger.error("[FAIL] Login failed: %s", e)
            return False

    # ──────────────────────────────────────────
    # Message Sending
    # ──────────────────────────────────────────
    @safe_execute(default_return=False)
    @with_retry(max_retries=2, delay=2.0)
    async def _send_message(self, username: str, message: str) -> bool:
        """
        Send a single message to a user on the platform.

        This method handles:
          1. Navigating to the user's message/DM page
          2. Typing the message with human-like delays
          3. Clicking send
          4. Verifying delivery

        Returns:
            True if message was sent successfully, False otherwise.
        """
        msg_cfg = self._config.get("message", "selectors") or {}

        try:
            # Navigate to user's profile or DM page
            # This URL pattern should be customized per platform
            # Example: https://platform.com/messages/{username}
            base = self._config.get("account", "login_url", default="")
            dm_url = f"{base.rsplit('/', 1)[0]}/messages/{username}"

            await self._page.goto(dm_url, wait_until="networkidle")

            # Click the message button (if needed to open compose)
            message_btn_sel = msg_cfg.get("message_button")
            if message_btn_sel:
                try:
                    msg_btn = await self._page.wait_for_selector(
                        message_btn_sel, timeout=5000
                    )
                    if msg_btn:
                        await msg_btn.click()
                        await asyncio.sleep(1)
                except PlaywrightTimeout:
                    pass  # May already be on the compose page

            # Type the message
            input_sel = msg_cfg.get("message_input", "textarea.message-input")
            msg_input = await self._page.wait_for_selector(input_sel, timeout=10000)
            await msg_input.click()
            await msg_input.type(message, delay=50)

            # Small pause before sending (human behavior)
            await asyncio.sleep(0.5 + (len(message) * 0.01))

            # Click send
            send_sel = msg_cfg.get("send_button", "button.send-btn")
            send_btn = await self._page.wait_for_selector(send_sel, timeout=5000)
            await send_btn.click()

            # Verify send (optional)
            success_sel = msg_cfg.get("success_indicator")
            if success_sel:
                try:
                    await self._page.wait_for_selector(success_sel, timeout=5000)
                except PlaywrightTimeout:
                    logger.warning("Send confirmation not detected for %s", username)

            logger.info("[OK] Message sent to @%s", username)
            return True

        except PlaywrightTimeout:
            logger.error("[FAIL] Timeout sending message to @%s", username)
            return False
        except Exception as e:
            logger.error("[FAIL] Failed to message @%s: %s", username, e)
            return False

    # ──────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────
    def _log_action(
        self, username: str, status: str, error: str = ""
    ) -> None:
        """Write an entry to the outreach audit log CSV."""
        log_path = self._config.get("logging", "message_log", default="./logs/outreach_logger.csv")
        CSVHandler.append_log_entry(log_path, {
            "username": username,
            "status": status,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": error,
        })

    # ──────────────────────────────────────────
    # Main Run Loop
    # ──────────────────────────────────────────
    async def run(self) -> dict:
        """
        Execute the full outreach workflow.

        Returns:
            Summary dict with sent/failed/skipped counts.
        """
        start_time = time.time()

        logger.info("=" * 55)
        logger.info("Outreach Bot — Starting")
        logger.info("=" * 55)

        # ── Load message template ──
        template_path = self._config.get(
            "message", "template_file", default="./config/message_template.txt"
        )
        self._message_handler = MessageHandler(template_path)
        logger.info("Message preview:\n%s", self._message_handler.preview())

        # ── Load user list ──
        input_cfg = self._config.get("input") or {}
        csv_path = input_cfg.get("csv_path", "./output/scraped_users_latest.csv")
        username_col = input_cfg.get("username_column", "username")

        try:
            users = CSVHandler.read_users(csv_path, username_col)
            logger.info("Loaded %d users from %s", len(users), csv_path)
        except (FileNotFoundError, ValueError) as e:
            logger.error("Failed to load user list: %s", e)
            return self._summary(start_time)

        # ── Filter already-messaged users ──
        skip_messaged = input_cfg.get("skip_already_messaged", True)
        if skip_messaged:
            log_path = self._config.get(
                "logging", "message_log", default="./logs/outreach_logger.csv"
            )
            already_messaged = CSVHandler.get_messaged_users(log_path, "username")
            original_count = len(users)
            users = [
                u for u in users
                if u.get(username_col, "").strip().lower() not in already_messaged
            ]
            skipped_prev = original_count - len(users)
            if skipped_prev:
                logger.info(
                    "Skipped %d already-messaged users (%d remaining)",
                    skipped_prev, len(users),
                )
            self._skipped += skipped_prev

        if not users:
            logger.info("No users to message — all have been contacted")
            return self._summary(start_time)

        # ── Launch browser and login ──
        await self._init_browser()
        if not await self._login():
            logger.error("Cannot proceed without login")
            return self._summary(start_time)

        # ── Send messages ──
        logger.info("Starting outreach to %d users...", len(users))

        for i, user in enumerate(users, 1):
            username = user.get(username_col, "").strip()
            display_name = user.get("display_name", "").strip() or None

            if not username:
                continue

            logger.info(
                "[%d/%d] Messaging @%s...",
                i, len(users), username,
            )

            # Rate limit
            try:
                delay = self._rate_limiter.wait()
                logger.debug("Rate limiter delay: %.1fs", delay)
            except RateLimitExceeded as e:
                logger.warning("Rate limit reached: %s", e)
                self._log_action(username, "rate_limited", str(e))
                break

            # Personalize and send
            message = self._message_handler.personalize(
                username=username,
                display_name=display_name,
            )

            success = await self._send_message(username, message)

            if success:
                self._sent += 1
                self._log_action(username, "sent")
            else:
                self._failed += 1
                self._log_action(username, "failed", "send_error")

                # If too many consecutive failures, stop
                if self._failed >= 5 and self._sent == 0:
                    logger.error(
                        "5 consecutive failures with no successes — "
                        "stopping to prevent issues"
                    )
                    break

        # ── Cleanup ──
        await self.shutdown()

        summary = self._summary(start_time)
        logger.info("=" * 55)
        logger.info(
            "Outreach complete: %d sent, %d failed, %d skipped (%.1fs)",
            summary["sent"], summary["failed"], summary["skipped"],
            summary["duration_seconds"],
        )
        logger.info("=" * 55)

        return summary

    async def shutdown(self) -> None:
        """Close browser resources."""
        if self._session:
            await self._session.close()

    def _summary(self, start_time: float) -> dict:
        """Generate a summary dict."""
        return {
            "sent": self._sent,
            "failed": self._failed,
            "skipped": self._skipped,
            "duration_seconds": round(time.time() - start_time, 2),
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
