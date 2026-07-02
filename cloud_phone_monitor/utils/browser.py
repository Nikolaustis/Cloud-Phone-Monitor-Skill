from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright


def new_browser_context(browser: Browser, storage_state: Path | None = None) -> BrowserContext:
    state_arg = str(storage_state) if storage_state and storage_state.exists() else None
    return browser.new_context(
        viewport={"width": 1440, "height": 1200},
        locale="en-US",
        storage_state=state_arg,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )


@contextmanager
def launch_browser(
    headless: bool = True,
    storage_state: Path | None = None,
) -> Iterator[tuple[Playwright, Browser, BrowserContext]]:
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    context = new_browser_context(browser, storage_state)
    try:
        yield pw, browser, context
    finally:
        context.close()
        browser.close()
        pw.stop()
