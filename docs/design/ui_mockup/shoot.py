"""Render index.html to for_him_ui_composite.png at 1440 px wide (full page, device scale 1).

    python3 docs/design/ui_mockup/shoot.py

Needs the Python ``playwright`` package with its Chromium (``playwright install chromium``).
The mockup is static HTML with no script, so the picture is a pure function of the two files.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto((HERE / "index.html").as_uri())
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(HERE / "for_him_ui_composite.png"), full_page=True)
        browser.close()
    print(HERE / "for_him_ui_composite.png")


if __name__ == "__main__":
    main()
