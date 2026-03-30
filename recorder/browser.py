"""
browser.py

Launches Brave Browser using the user's real profile (cookies/session)
so duelingbook.com loads replay data correctly.

Uses launch_persistent_context to attach to the existing Brave profile,
then opens the replay URL in a new page in fullscreen mode.

Usage:
    from recorder.browser import ReplayBrowser

    with ReplayBrowser() as rb:
        rb.open(replay_id="578530-80432376")
        # rb.page is the live Playwright Page
"""

import logging
import os
import subprocess
import time

from playwright.sync_api import sync_playwright, Page, BrowserContext, Playwright

logger = logging.getLogger(__name__)

REPLAY_BASE_URL = "https://www.duelingbook.com/replay?id={replay_id}"

BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

# Brave's default profile directory on macOS
BRAVE_USER_DATA_DIR = os.path.expanduser(
    "~/Library/Application Support/BraveSoftware/Brave-Browser"
)

# Timeout (ms) waiting for the play button to become available
PAGE_READY_TIMEOUT = 60_000


class ReplayBrowser:
    """
    Context manager that owns the Playwright browser lifecycle.

    Uses the user's real Brave profile so duelingbook session cookies
    are available and replay data loads correctly.
    """

    def __init__(self, slow_mo: int = 0):
        self.slow_mo = slow_mo
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "ReplayBrowser":
        self._playwright = sync_playwright().start()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self, replay_id: str) -> Page:
        """
        Opens the replay URL in Brave using the user's real profile,
        waits until #play_btn is ready, then sets the window to fullscreen.

        Args:
            replay_id: The duelingbook replay ID (e.g. "578530-80432376").

        Returns:
            The Playwright Page object, ready for ReplayMonitor.
        """
        url = REPLAY_BASE_URL.format(replay_id=replay_id)
        logger.info(f"Opening replay: {url}")

        # launch_persistent_context uses the real Brave profile (cookies/session)
        # and returns a BrowserContext directly (no separate Browser object).
        self._kill_brave()

        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=BRAVE_USER_DATA_DIR,
            executable_path=BRAVE_PATH,
            headless=False,
            slow_mo=self.slow_mo,
            screen={"width": 1920, "height": 1080},
            viewport={"width": 1920, "height": 1080},
            args=[
                "--kiosk",
                "--disable-infobars",
                "--noerrdialogs",
                "--disable-session-crashed-bubble",
                "--window-size=1920,1080",
                "--disable-blink-features=AutomationControlled",
                "--excludeSwitches=enable-automation",
            ],
            ignore_default_args=["--enable-automation"],
        )

        self.page = self._context.new_page()
        self._maximize_to_screen()
        self.page.goto(url, wait_until="domcontentloaded")

        logger.info("Page loaded. Waiting for replay controls to be ready...")
        self._wait_for_controls_ready()

        logger.info("Browser ready for recording.")
        return self.page

    def close(self) -> None:
        """Closes the browser context and stops Playwright. Safe to call multiple times."""
        try:
            if self.page:
                self.page.close()
            if self._context:
                self._context.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")
        finally:
            self._context = None
            self._playwright = None
            self.page = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _kill_brave(self) -> None:
        """
        Gracefully quits Brave if it's running, then waits until the process
        is gone so the profile directory is free for the new instance.
        """
        result = subprocess.run(["pgrep", "-x", "Brave Browser"], capture_output=True)
        if result.returncode != 0:
            logger.info("Brave is not running.")
            return

        logger.info("Brave is running — quitting it to free the profile...")
        subprocess.run(["osascript", "-e", 'quit app "Brave Browser"'], check=False)

        # Wait up to 10 seconds for Brave to exit
        for _ in range(20):
            time.sleep(0.5)
            check = subprocess.run(["pgrep", "-x", "Brave Browser"], capture_output=True)
            if check.returncode != 0:
                logger.info("Brave has exited.")
                return

        # Force kill if it didn't quit gracefully
        logger.warning("Brave didn't quit gracefully — force killing.")
        subprocess.run(["pkill", "-x", "Brave Browser"], check=False)
        time.sleep(1)

    def _maximize_to_screen(self) -> None:
        """
        Sets the browser window to fullscreen via CDP and syncs the
        Playwright viewport to the real screen resolution so the page
        renders at full size (not in a small corner with black around it).
        """
        cdp = self.page.context.new_cdp_session(self.page)

        # Get native screen size from the browser before navigating
        w, h = 1920, 1080
        logger.info(f"Using resolution: {w}x{h}")

        # Set window to fullscreen
        window_info = cdp.send("Browser.getWindowForTarget")
        window_id = window_info["windowId"]
        cdp.send("Browser.setWindowBounds", {
            "windowId": window_id,
            "bounds": {"windowState": "fullscreen"},
        })

        # Sync the viewport so the page renders at full screen size
        self.page.set_viewport_size({"width": w, "height": h})

        cdp.detach()
        logger.info(f"Browser fullscreen and viewport set to {w}x{h}.")

    def _wait_for_controls_ready(self) -> None:
        """
        Waits until #play_btn is in the DOM and enabled.
        Uses JS evaluation because #play_btn has opacity:0 (invisible to Playwright).
        """
        self.page.wait_for_function(
            "() => { const b = document.querySelector('#play_btn'); return b && !b.disabled; }",
            timeout=PAGE_READY_TIMEOUT,
        )
        logger.debug("#play_btn is ready.")
