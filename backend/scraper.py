"""
scraper.py
──────────
Auto-login + live part-number search across supplier portals using Playwright.

Design goals
------------
* Persistent per-supplier browser sessions so logins stay warm ("always
  logged in"). We use a single Chromium instance with one persistent context
  per supplier (storage_state on disk), so cookies survive restarts.
* Credentials are pulled at runtime from credentials.py (env vars / encrypted
  vault) — never hard-coded.
* Every method is defensive: if a portal changes its markup, blocks the bot,
  or has no credentials, we fall back to a deep-link result rather than
  crashing the whole search.

NOTE: Every supplier portal has different HTML. The `login()` and `search()`
selectors below are sensible defaults; adjust the per-supplier selectors in
`PORTAL_SELECTORS` to match the real pages you are automating.
"""

import os
import asyncio
import logging
from pathlib import Path
from urllib.parse import quote_plus

from credentials import get_credentials, has_credentials

logger = logging.getLogger("partfinder.scraper")

HEADLESS = os.environ.get("PARTFINDER_HEADLESS", "1") != "0"
STATE_DIR = Path(os.environ.get("PF_STATE_DIR", "/tmp/pf_sessions"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Per-portal CSS selectors. Tune these to each real portal.
PORTAL_SELECTORS = {
    "Ferguson": {
        "user": "#username", "pass": "#password", "submit": "button[type=submit]",
        "logged_in": "text=Sign Out",
        "result_price": ".product-price, [data-testid='price']",
        "result_stock": ".availability, [data-testid='availability']",
    },
    "Grainger": {
        "user": "#username", "pass": "#password", "submit": "button[type=submit]",
        "logged_in": "text=Sign Out",
        "result_price": ".price, [data-testid='product-price']",
        "result_stock": ".availability-message",
    },
    "PartsTown": {
        "user": "#email", "pass": "#password", "submit": "button[type=submit]",
        "logged_in": "text=My Account",
        "result_price": ".price, .js-price",
        "result_stock": ".stock-status, .availability",
    },
    "AllPoints": {
        "user": "#email", "pass": "#password", "submit": "button[type=submit]",
        "logged_in": "text=Log Out",
        "result_price": ".price", "result_stock": ".availability",
    },
    "Johnstone Supply": {
        "user": "#email", "pass": "#password", "submit": "button[type=submit]",
        "logged_in": "text=Sign Out",
        "result_price": ".price", "result_stock": ".stock",
    },
    "Amazon": {
        "user": "#ap_email", "pass": "#ap_password", "submit": "#signInSubmit",
        "logged_in": "#nav-link-accountList",
        "result_price": ".a-price .a-offscreen", "result_stock": "#availability",
    },
}


class Scraper:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._contexts = {}   # supplier name -> browser context
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        if self._browser:
            return
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        logger.info("Chromium launched (headless=%s).", HEADLESS)

    def _state_path(self, name: str) -> Path:
        safe = name.lower().replace(" ", "_")
        return STATE_DIR / f"{safe}.json"

    async def _get_context(self, supplier: dict):
        name = supplier["name"]
        if name in self._contexts:
            return self._contexts[name]
        await self._ensure_browser()
        state = self._state_path(name)
        ctx = await self._browser.new_context(
            storage_state=str(state) if state.exists() else None,
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/121.0 Safari/537.36"),
            viewport={"width": 1366, "height": 768},
        )
        self._contexts[name] = ctx
        return ctx

    async def _save_state(self, supplier: dict, ctx):
        try:
            await ctx.storage_state(path=str(self._state_path(supplier["name"])))
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not persist session for %s: %s", supplier["name"], e)

    async def login(self, supplier: dict) -> bool:
        """Log into a supplier portal and persist the session. Returns True on success."""
        name = supplier["name"]
        if supplier.get("type") != "portal" or not has_credentials(supplier):
            return False
        sel = PORTAL_SELECTORS.get(name, {})
        login_url = supplier.get("login_url") or supplier.get("portal_url")
        if not login_url:
            return False
        creds = get_credentials(supplier)
        ctx = await self._get_context(supplier)
        page = await ctx.new_page()
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
            # Already logged in from a persisted session?
            if sel.get("logged_in"):
                try:
                    await page.wait_for_selector(sel["logged_in"], timeout=3000)
                    logger.info("%s: already logged in (persistent session).", name)
                    await page.close()
                    return True
                except Exception:
                    pass
            if sel.get("user"):
                await page.fill(sel["user"], creds["login_email"])
            if sel.get("pass"):
                await page.fill(sel["pass"], creds["login_password"])
            if sel.get("submit"):
                await page.click(sel["submit"])
            await page.wait_for_load_state("networkidle", timeout=30000)
            if sel.get("logged_in"):
                await page.wait_for_selector(sel["logged_in"], timeout=8000)
            await self._save_state(supplier, ctx)
            logger.info("%s: login OK, session saved.", name)
            await page.close()
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("%s: login failed (%s). Will fall back to deep-link.", name, e)
            try:
                await page.close()
            except Exception:
                pass
            return False

    async def search(self, supplier: dict, part_number: str) -> dict:
        """Search a supplier for a part number. Returns a result dict."""
        name = supplier["name"]
        deep = self._deep_link_result(supplier, part_number)

        if supplier.get("type") != "portal" or not supplier.get("search_url"):
            return deep
        if not has_credentials(supplier):
            return deep  # cannot log in -> just return the portal link

        sel = PORTAL_SELECTORS.get(name, {})
        try:
            await self.login(supplier)  # ensures session is warm
            ctx = await self._get_context(supplier)
            page = await ctx.new_page()
            url = supplier["search_url"] + quote_plus(part_number)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_load_state("networkidle", timeout=20000)

            price = await self._text(page, sel.get("result_price"))
            stock = await self._text(page, sel.get("result_stock"))
            await self._save_state(supplier, ctx)
            await page.close()

            result = dict(deep)
            result.update({
                "price": price or "",
                "stock_status": stock or "See portal",
                "availability": stock or "Logged in — see live results",
                "has_live_price": bool(price),
                "search_url": url,
            })
            return result
        except Exception as e:  # noqa: BLE001
            logger.warning("%s: live search failed (%s). Falling back to deep-link.", name, e)
            return deep

    async def _text(self, page, selector):
        if not selector:
            return ""
        try:
            el = await page.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    def _deep_link_result(self, supplier: dict, part_number: str) -> dict:
        search_url = ""
        if supplier.get("search_url") and part_number:
            search_url = supplier["search_url"] + quote_plus(part_number)
        elif supplier.get("portal_url"):
            search_url = supplier["portal_url"]
        return {
            "name": supplier["name"],
            "type": supplier.get("type", "portal"),
            "account_number": supplier.get("account_number", ""),
            "rep_name": supplier.get("rep_name", ""),
            "email": supplier.get("email", ""),
            "phone": supplier.get("phone", ""),
            "cell": supplier.get("cell", ""),
            "portal_url": supplier.get("portal_url", ""),
            "search_url": search_url,
            "price": "",
            "stock_status": "Login Required" if supplier.get("type") == "portal" else "Call Rep",
            "availability": f"Opens {supplier['name']} search" if search_url else "Contact rep",
            "has_live_price": False,
            "has_credentials": has_credentials(supplier),
        }

    async def close(self):
        for ctx in self._contexts.values():
            try:
                await ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None


# ── Module-level singleton + public helpers used by serve_all.py ───────────
_scraper: Scraper | None = None


def get_scraper() -> Scraper:
    global _scraper
    if _scraper is None:
        _scraper = Scraper()
    return _scraper


async def warm_all_sessions(suppliers: list):
    """Log into every portal that has credentials so sessions stay warm."""
    sc = get_scraper()
    for s in suppliers:
        if s.get("type") == "portal" and has_credentials(s):
            try:
                await sc.login(s)
            except Exception as e:  # noqa: BLE001
                logger.warning("Warm session failed for %s: %s", s["name"], e)


async def scrape_all_suppliers(suppliers: list, part_number: str) -> list:
    """Search all suppliers concurrently for a part number."""
    sc = get_scraper()
    tasks = [sc.search(s, part_number) for s in suppliers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for s, r in zip(suppliers, results):
        if isinstance(r, Exception):
            logger.error("Search error for %s: %s", s["name"], r)
            out.append(sc._deep_link_result(s, part_number))
        else:
            out.append(r)
    return out


def session_status(suppliers: list) -> dict:
    return {
        s["name"]: ("credentials-set" if has_credentials(s) else "no-credentials")
        for s in suppliers
    }


async def shutdown_scraper():
    global _scraper
    if _scraper:
        await _scraper.close()
        _scraper = None
