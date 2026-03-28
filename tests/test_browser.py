"""
tests/test_browser.py

Unit tests for ReplayBrowser using mocked Playwright.
Run with: pytest tests/test_browser.py -v
"""

from unittest.mock import MagicMock, patch
import pytest

from recorder.browser import ReplayBrowser, REPLAY_BASE_URL, PAGE_READY_TIMEOUT


def make_playwright_stack():
    """
    Returns a mock (playwright, context, page) stack wired so that
    launch_persistent_context returns the context and new_page returns the page.
    """
    mock_page = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_chromium = MagicMock()
    mock_chromium.launch_persistent_context.return_value = mock_context

    mock_playwright = MagicMock()
    mock_playwright.chromium = mock_chromium

    return mock_playwright, mock_context, mock_page


@patch("recorder.browser.sync_playwright")
class TestReplayBrowserOpen:
    def test_navigates_to_correct_url(self, mock_sync_pw):
        pw, ctx, page = make_playwright_stack()
        mock_sync_pw.return_value.__enter__.return_value = pw

        rb = ReplayBrowser()
        rb._playwright = pw
        rb.open("578530-80432376")

        expected_url = REPLAY_BASE_URL.format(replay_id="578530-80432376")
        page.goto.assert_called_once_with(expected_url, wait_until="domcontentloaded")

    def test_waits_for_play_btn(self, mock_sync_pw):
        pw, ctx, page = make_playwright_stack()
        mock_sync_pw.return_value.__enter__.return_value = pw

        rb = ReplayBrowser()
        rb._playwright = pw
        rb.open("123")

        page.wait_for_function.assert_called_once_with(
            "() => { const b = document.querySelector('#play_btn'); return b && !b.disabled; }",
            timeout=PAGE_READY_TIMEOUT,
        )

    def test_launches_with_kiosk_flag(self, mock_sync_pw):
        pw, ctx, page = make_playwright_stack()
        mock_sync_pw.return_value.__enter__.return_value = pw

        rb = ReplayBrowser()
        rb._playwright = pw
        rb.open("123")

        call_args = pw.chromium.launch_persistent_context.call_args
        assert "--kiosk" in call_args.kwargs.get("args", [])

    def test_launches_in_headed_mode(self, mock_sync_pw):
        pw, ctx, page = make_playwright_stack()
        mock_sync_pw.return_value.__enter__.return_value = pw

        rb = ReplayBrowser()
        rb._playwright = pw
        rb.open("123")

        call_args = pw.chromium.launch_persistent_context.call_args
        assert call_args.kwargs.get("headless") is False

    def test_returns_page(self, mock_sync_pw):
        pw, ctx, page = make_playwright_stack()
        mock_sync_pw.return_value.__enter__.return_value = pw

        rb = ReplayBrowser()
        rb._playwright = pw
        result = rb.open("123")

        assert result is page
        assert rb.page is page


@patch("recorder.browser.sync_playwright")
class TestReplayBrowserClose:
    def test_close_cleans_up_resources(self, mock_sync_pw):
        pw, ctx, page = make_playwright_stack()

        rb = ReplayBrowser()
        rb._playwright = pw
        rb._context = ctx
        rb.page = page

        rb.close()

        ctx.close.assert_called_once()
        pw.stop.assert_called_once()

    def test_close_clears_references(self, mock_sync_pw):
        pw, ctx, page = make_playwright_stack()

        rb = ReplayBrowser()
        rb._playwright = pw
        rb._context = ctx
        rb.page = page

        rb.close()

        assert rb.page is None
        assert rb._context is None
        assert rb._playwright is None

    def test_close_is_safe_when_already_closed(self, mock_sync_pw):
        rb = ReplayBrowser()
        rb.close()  # should not raise


@patch("recorder.browser.sync_playwright")
class TestContextManager:
    def test_context_manager_calls_close_on_exit(self, mock_sync_pw):
        pw, ctx, page = make_playwright_stack()
        mock_sync_pw.return_value.start.return_value = pw

        with ReplayBrowser() as rb:
            rb._context = ctx
            rb.page = page

        ctx.close.assert_called_once()
