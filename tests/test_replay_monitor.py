"""
tests/test_replay_monitor.py

Unit tests for ReplayMonitor using a mocked Playwright Page.
Run with: pytest tests/test_replay_monitor.py -v
"""

from unittest.mock import MagicMock, patch, call
import pytest

from recorder.replay_monitor import ReplayMonitor, WARMUP_DELAY


def make_page(
    ready=True,
    arr_length=10,
    next_btn_disabled=False,
    duel_over=False,
    next_game_available=False,
):
    """Creates a mock Playwright Page with configurable JS evaluation results."""
    page = MagicMock()

    def evaluate_side_effect(expr):
        if "ready" in expr and "replay_arr" not in expr:
            return ready
        if "replay_arr.length === 0" in expr:
            return arr_length == 0
        if "next_btn" in expr and "next_game" not in expr and "disabled" in expr:
            return next_btn_disabled
        if "Duel Over" in expr:
            return duel_over
        if "next_game_btn" in expr:
            return next_game_available
        if "replay_arr.length" in expr:
            return arr_length
        return None

    page.evaluate.side_effect = evaluate_side_effect
    page.query_selector.return_value = MagicMock(get_attribute=MagicMock(return_value=None))
    return page


# ------------------------------------------------------------------
# _is_replay_done
# ------------------------------------------------------------------

class TestIsReplayDone:
    def test_not_done_when_no_signals(self):
        page = make_page(arr_length=100, next_btn_disabled=False, duel_over=False)
        monitor = ReplayMonitor(page)
        assert monitor._is_replay_done() is False

    def test_not_done_with_only_one_signal(self):
        page = make_page(arr_length=0, next_btn_disabled=False, duel_over=False)
        monitor = ReplayMonitor(page)
        assert monitor._is_replay_done() is False

    def test_done_with_two_signals(self):
        page = make_page(arr_length=0, next_btn_disabled=True, duel_over=False)
        monitor = ReplayMonitor(page)
        assert monitor._is_replay_done() is True

    def test_done_with_all_three_signals(self):
        page = make_page(arr_length=0, next_btn_disabled=True, duel_over=True)
        monitor = ReplayMonitor(page)
        assert monitor._is_replay_done() is True

    def test_returns_false_on_evaluate_exception(self):
        page = MagicMock()
        page.evaluate.side_effect = Exception("page crashed")
        monitor = ReplayMonitor(page)
        assert monitor._is_replay_done() is False



# ------------------------------------------------------------------
# run() — high-level behavior
# ------------------------------------------------------------------

class TestRun:
    @patch("recorder.replay_monitor.time.sleep")
    def test_exits_when_replay_done(self, mock_sleep):
        page = make_page(arr_length=0, next_btn_disabled=True, duel_over=True)
        monitor = ReplayMonitor(page, click_interval=0)
        # Should not raise, should return after detecting done
        monitor.run()

    @patch("recorder.replay_monitor.time.sleep")
    @patch("recorder.replay_monitor.time.time")
    def test_raises_timeout_when_replay_never_ends(self, mock_time, mock_sleep):
        # Simulate time advancing past deadline immediately
        mock_time.side_effect = [0, 0, 99999]
        page = make_page(arr_length=100, next_btn_disabled=False, duel_over=False)
        monitor = ReplayMonitor(page, click_interval=0)
        with pytest.raises(TimeoutError):
            monitor.run()
