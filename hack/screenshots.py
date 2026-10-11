#!/usr/bin/env python3
"""Capture the README screenshots from a running, seeded instance.

    pip install playwright            # uses your installed Chrome, no browser download
    python hack/seed_demo.py --password changeme --run
    python hack/screenshots.py --password changeme

Writes PNGs to docs/images/.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
VIEWPORT = {"width": 1440, "height": 900}


def open_page(browser, url: str, theme: str) -> Page:
    ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
    ctx.add_init_script(f"localStorage.setItem('playbook-theme', '{theme}')")
    page = ctx.new_page()
    page.goto(url)
    page.wait_for_load_state("networkidle")
    return page


def shot(page: Page, name: str) -> None:
    page.wait_for_timeout(600)  # let transitions settle
    page.screenshot(path=str(OUT / name))
    print("wrote", OUT / name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--password", required=True)
    ap.add_argument("--channel", default="chrome", help="installed browser to drive (chrome/msedge)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    base = args.url.rstrip("/")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=args.channel)

        for theme in ("dark", "light"):
            page = open_page(browser, base + "/", theme)
            page.wait_for_selector("#board .card")
            shot(page, f"dashboard-{theme}.png")
            page.context.close()

        # Run an action and capture the live log + artifacts.
        page = open_page(browser, base + "/", "dark")
        page.get_by_text("Deploy service", exact=True).first.click()
        page.wait_for_selector("#modal.open, #modal.show, #modal:not(.hidden)")
        page.click("#m-execute")
        page.wait_for_selector("#m-status:has-text('Success')", timeout=60_000)
        shot(page, "execution.png")
        page.context.close()

        page = open_page(browser, base + "/", "dark")
        page.click("#history-toggle")
        page.wait_for_selector("#history-list > *")
        shot(page, "history.png")
        page.context.close()

        page = open_page(browser, base + "/admin", "dark")
        page.fill("#password", args.password)
        page.click("#login-btn")
        page.wait_for_selector("#action-list > *")
        # Frame the Actions section (the tag bank sits above it).
        page.evaluate("window.scrollTo(0, document.getElementById('new-action').getBoundingClientRect().top + window.scrollY - 100)")
        shot(page, "admin.png")
        page.locator("#action-list > *", has_text="Deploy service").locator("button").first.click()
        page.wait_for_selector("#params > *")
        shot(page, "admin-editor.png")
        page.locator("#add-param").scroll_into_view_if_needed()
        page.evaluate("document.getElementById('add-param').scrollIntoView({block: 'start'})")
        shot(page, "admin-params.png")
        page.context.close()

        browser.close()


if __name__ == "__main__":
    main()
