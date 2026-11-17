"""Render study/static/study/icons/icon.svg to the PNG sizes the web app manifest needs.

Run once after changing the SVG: `uv run python scripts/make_icons.py`.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

ICONS = Path(__file__).resolve().parent.parent / "study" / "static" / "study" / "icons"
# name → (size, padding fraction). Maskable icons keep the art inside the 80% safe zone.
OUTPUTS = {
    "icon-192.png": (192, 0.0),
    "icon-512.png": (512, 0.0),
    "maskable-512.png": (512, 0.1),
    "apple-touch-icon.png": (180, 0.0),
}


def main() -> None:
    svg = (ICONS / "icon.svg").read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (size, pad) in OUTPUTS.items():
            page = browser.new_page(viewport={"width": size, "height": size})
            inner = round(size * (1 - 2 * pad))
            page.set_content(
                f'<body style="margin:0;background:#1C1E22;display:grid;place-items:center;'
                f'width:{size}px;height:{size}px">'
                f'<div style="width:{inner}px;height:{inner}px">{svg}</div></body>'
            )
            page.screenshot(path=str(ICONS / name), omit_background=False)
            page.close()
            print(ICONS / name)
        browser.close()


if __name__ == "__main__":
    main()
