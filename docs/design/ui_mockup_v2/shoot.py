"""Render the v2 mockup: one PNG per frame (frame_1_review.png, frame_2_run.png, frame_3_finished.png) at
1440 px wide, and the three stacked as for_him_ui_v2_composite.png.

    .venv/bin/python docs/design/ui_mockup_v2/shoot.py

Needs the Python ``playwright`` package with its Chromium (``playwright install chromium``), as in
``docs/design/ui_mockup/shoot.py``. The mockup is static HTML with no script, so every picture is a pure
function of index.html and tokens.css.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FRAMES = [("frame-1", "frame_1_review.png"), ("frame-2", "frame_2_run.png"), ("frame-3", "frame_3_finished.png")]


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto((HERE / "index.html").as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        for frame_id, name in FRAMES:
            page.locator(f"#{frame_id}").screenshot(path=str(HERE / name))
            print(HERE / name)
        page.screenshot(path=str(HERE / "for_him_ui_v2_composite.png"), full_page=True)
        print(HERE / "for_him_ui_v2_composite.png")
        browser.close()


if __name__ == "__main__":
    main()
