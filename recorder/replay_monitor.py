"""
replay_monitor.py

Advances a duelingbook.com replay by repeatedly clicking #next_btn,
and detects when the replay (including multi-game duels) has ended.

Usage:
    from recorder.replay_monitor import ReplayMonitor

    monitor = ReplayMonitor(page)
    monitor.wait_for_replay_start()
    monitor.run()   # blocks until replay is fully done
"""

import time
import logging

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# How often (seconds) to click #next_btn to advance the replay
CLICK_INTERVAL = 0.5

# How often (in click cycles) to check end-of-replay signals
CHECK_EVERY_N_CLICKS = 6  # every ~3 seconds

# Max seconds to wait for the entire replay to finish (2 hours)
REPLAY_TIMEOUT = 7200

# Seconds to wait after clicking play before starting the click loop
# (gives the JS engine time to start populating replay_arr)
WARMUP_DELAY = 3.0


class ReplayMonitor:
    def __init__(self, page: Page, click_interval: float = CLICK_INTERVAL):
        self.page = page
        self.click_interval = click_interval

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def wait_for_replay_start(self) -> None:
        """
        Waits until replay_arr is populated (all actions loaded), then
        clicks #show2_rb to show opponent's hand and clicks play.
        """
        logger.info("Waiting for replay_arr to be populated...")
        time.sleep(8)  # Let JS finish executing after domcontentloaded
        deadline = time.time() + 90
        while time.time() < deadline:
            actions = self.page.evaluate(
                "() => typeof replay_arr !== 'undefined' ? replay_arr.length : -1"
            )
            logger.info(f"replay_arr check: {actions}")
            if actions > 0:
                logger.info(f"replay_arr loaded with {actions} actions.")
                break
            time.sleep(2)
        else:
            raise TimeoutError("replay_arr never populated — page may not have loaded correctly.")

        # Show opponent's hand before starting
        self.page.evaluate(
            "() => { const rb = document.querySelector('#show2_rb'); if (rb) rb.click(); }"
        )
        logger.info("Replay ready — starting next_btn loop.")

        # Give the JS engine a moment to start filling replay_arr
        time.sleep(WARMUP_DELAY)

    def run(self) -> None:
        """
        Main loop: clicks #next_btn every CLICK_INTERVAL seconds to advance
        the replay as fast as possible, periodically checking for end conditions.

        Handles multi-game duels by detecting and clicking #next_game_btn
        between games.

        Blocks until the replay is fully done or REPLAY_TIMEOUT is reached.
        Raises TimeoutError if the replay doesn't finish in time.
        """
        logger.info("Starting replay advance loop...")
        deadline = time.time() + REPLAY_TIMEOUT
        click_count = 0

        while time.time() < deadline:
            # --- Click next_btn to advance the replay ---
            self._click_if_available("#next_btn")
            click_count += 1
            time.sleep(self.click_interval)

            # --- Periodically check for end conditions ---
            if click_count % CHECK_EVERY_N_CLICKS != 0:
                continue

            # Check if the full replay has ended
            if self._is_replay_done():
                logger.info("Replay finished.")
                return

            remaining = int(deadline - time.time())
            actions = self._get_remaining_actions()
            logger.debug(f"Still running — replay_arr: {actions} actions left, {remaining}s remaining")

        raise TimeoutError(
            f"Replay did not finish within {REPLAY_TIMEOUT} seconds. "
            "Consider increasing REPLAY_TIMEOUT."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _click_if_available(self, selector: str) -> bool:
        """
        Clicks the element via JS if it exists and is not disabled.
        Uses JS click because duelingbook buttons have opacity:0 and
        Playwright's normal click rejects invisible elements.
        Returns True if clicked, False otherwise.
        """
        try:
            clicked = self.page.evaluate(
                f"() => {{ const b = document.querySelector('{selector}'); "
                f"if (b && !b.disabled) {{ b.click(); return true; }} return false; }}"
            )
            return bool(clicked)
        except Exception as e:
            logger.debug(f"Could not click {selector}: {e}")
        return False

    def _is_replay_done(self) -> bool:
        """
        Returns True when at least 2 of 3 end-of-replay signals are active.
        Using multiple signals avoids false positives during loading.

        Signals:
          1. replay_arr is empty (all actions consumed)
          2. #next_btn is disabled (controls locked)
          3. 'Duel Over' text is visible on the page
        """
        try:
            arr_empty = self.page.evaluate(
                "() => typeof replay_arr !== 'undefined' && replay_arr.length === 0"
            )
            next_btn_disabled = self.page.evaluate(
                "() => { const b = document.querySelector('#next_btn'); return b ? b.disabled : false; }"
            )
            duel_over = self.page.evaluate(
                "() => document.body.innerText.includes('Duel Over')"
            )

            signals = [arr_empty, next_btn_disabled, duel_over]
            active = sum(signals)
            logger.debug(
                f"End signals — arr_empty={arr_empty}, next_btn_disabled={next_btn_disabled}, "
                f"duel_over={duel_over} ({active}/3 active)"
            )
            return active >= 2

        except Exception as e:
            logger.warning(f"Error evaluating end signals: {e}")
            return False

    def _get_remaining_actions(self) -> int:
        """Returns replay_arr.length for progress logging. Returns -1 on error."""
        try:
            return self.page.evaluate(
                "() => typeof replay_arr !== 'undefined' ? replay_arr.length : -1"
            )
        except Exception:
            return -1
