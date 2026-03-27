"""Playwright-based Upwork scraper with login + session reuse."""
import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from .config import (
    AUTH_STATE_FILE,
    MAX_PAGES_PER_QUERY,
    SEARCH_QUERIES,
    UPWORK_EMAIL,
    UPWORK_PASSWORD,
)

# ── selectors (update here if Upwork changes HTML) ─────────────────────────
SEL_JOB_TILE = "article[data-test='JobTile'], div[data-test='job-tile'], section.up-card-section"
SEL_TITLE_LINK = "a[data-test='job-title-link'], h2 a, .job-title a"
SEL_DESCRIPTION = "[data-test='job-description-text'], .job-description, p.description"
SEL_BUDGET = "[data-test='job-type-label'], [data-test='budget'], .budget"
SEL_PROPOSALS = "[data-test='proposals-tier'], [data-test='proposals'], .proposals"
SEL_PAYMENT = "[data-test='payment-verified'], [data-test='payment-status']"
SEL_LOCATION = "[data-test='client-country'], [data-test='location']"
SEL_SKILLS = "[data-test='token'], .skill-badge, .air3-token"
SEL_POSTED = "[data-test='posted-on'], [data-test='posted'], .posted-on"


async def _try_text(el_handle, default: str = "") -> str:
    try:
        return (await el_handle.inner_text()).strip() if el_handle else default
    except Exception:
        return default


async def _extract_job(card) -> dict | None:
    """Extract structured data from a single job card."""
    try:
        title_el = await card.query_selector(SEL_TITLE_LINK)
        if not title_el:
            return None

        title = await _try_text(title_el)
        href = await title_el.get_attribute("href") or ""

        # Extract Upwork job ID from URL  (~017f3abc... or _~017f3...)
        m = re.search(r"_~([0-9a-zA-Z]+)", href) or re.search(r"~([0-9a-zA-Z]+)", href)
        job_id = m.group(1) if m else re.sub(r"[^a-z0-9]", "", href)[-20:]

        desc_el = await card.query_selector(SEL_DESCRIPTION)
        description = await _try_text(desc_el)

        budget_el = await card.query_selector(SEL_BUDGET)
        budget_text = await _try_text(budget_el)

        proposals_el = await card.query_selector(SEL_PROPOSALS)
        proposals_text = await _try_text(proposals_el)

        payment_el = await card.query_selector(SEL_PAYMENT)
        payment_verified = payment_el is not None

        location_el = await card.query_selector(SEL_LOCATION)
        client_location = await _try_text(location_el)

        skill_els = await card.query_selector_all(SEL_SKILLS)
        skills = [await _try_text(e) for e in skill_els if await _try_text(e)]

        posted_el = await card.query_selector(SEL_POSTED)
        posted_text = await _try_text(posted_el)

        if not title or not job_id:
            return None

        return {
            "id": job_id,
            "title": title,
            "url": f"https://www.upwork.com{href}" if href.startswith("/") else href,
            "description": description[:1200],
            "budget_text": budget_text,
            "proposals_text": proposals_text,
            "payment_verified": payment_verified,
            "client_location": client_location,
            "skills": [s for s in skills if s],
            "posted_text": posted_text,
        }
    except Exception as e:
        print(f"  [warn] extract_job error: {e}", file=sys.stderr)
        return None


async def _first_visible(page: Page, selectors: list[str], timeout: int = 2500):
    """Return the first visible locator from the list, or None."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=timeout)
            return loc, sel
        except Exception:
            pass
    return None, None


async def _login(page: Page) -> bool:
    """
    Robust Upwork login that tries multiple selectors and saves
    debug screenshots on failure.
    """
    print("  Navigating to Upwork login...")
    await page.goto(
        "https://www.upwork.com/ab/account-security/login",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    await page.wait_for_timeout(2500)

    EMAIL_SELECTORS = [
        'input[type="email"]',
        'input[name="login[username]"]',
        "#login_username",
        'input[name*="username"]',
        'input[id*="username"]',
        'input[autocomplete="username"]',
        'input[placeholder*="email" i]',
        'input[aria-label*="email" i]',
    ]

    PRE_LOGIN_BTNS = [
        'button:has-text("Continue with Email")',
        'button:has-text("Continue with email")',
        'button:has-text("Log in with Email")',
        'a:has-text("Log in")',
        'a:has-text("Login")',
    ]

    PASSWORD_SELECTORS = [
        'input[type="password"]',
        'input[name="login[password]"]',
        "#login_password",
        'input[autocomplete="current-password"]',
        'input[aria-label*="password" i]',
        'input[placeholder*="password" i]',
    ]

    SUBMIT_SELECTORS = [
        'button[type="submit"]',
        'button:has-text("Continue")',
        'button:has-text("Next")',
        'button:has-text("Log In")',
        'button:has-text("Login")',
        'button:has-text("Sign In")',
    ]

    BASE_DIR = Path(__file__).parent.parent

    # ── Step 1: find email input ──────────────────────────────────
    email_box, used = await _first_visible(page, EMAIL_SELECTORS, timeout=3000)

    if email_box is None:
        # Try clicking a button that reveals the email form
        for sel in PRE_LOGIN_BTNS:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1200):
                    print(f"  Clicking pre-login button: {sel}")
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    break
            except Exception:
                pass
        email_box, used = await _first_visible(page, EMAIL_SELECTORS, timeout=5000)

    if email_box is None:
        debug_html = BASE_DIR / "upwork_login_debug.html"
        debug_png = BASE_DIR / "upwork_login_debug.png"
        debug_html.write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(debug_png), full_page=True)
        print(
            f"  [error] Could not find email input.\n"
            f"  Debug files saved:\n    {debug_png}\n    {debug_html}",
            file=sys.stderr,
        )
        return False

    print(f"  Found email input via: {used}")
    await email_box.fill(UPWORK_EMAIL)

    # Click Continue/Next after email
    for sel in SUBMIT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1200):
                print(f"  Clicking after-email button: {sel}")
                await btn.click()
                await page.wait_for_timeout(1500)
                break
        except Exception:
            pass

    # ── Step 2: find password input ──────────────────────────────
    pwd_box, used = await _first_visible(page, PASSWORD_SELECTORS, timeout=8000)

    if pwd_box is None:
        debug_html = BASE_DIR / "upwork_password_debug.html"
        debug_png = BASE_DIR / "upwork_password_debug.png"
        debug_html.write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(debug_png), full_page=True)
        print(
            f"  [error] Could not find password input.\n"
            f"  Debug files saved:\n    {debug_png}\n    {debug_html}",
            file=sys.stderr,
        )
        return False

    print(f"  Found password input via: {used}")
    await pwd_box.fill(UPWORK_PASSWORD)

    # Submit login
    clicked = False
    for sel in SUBMIT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1200):
                print(f"  Clicking submit: {sel}")
                await btn.click()
                clicked = True
                break
        except Exception:
            pass
    if not clicked:
        await pwd_box.press("Enter")

    await page.wait_for_timeout(3000)
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    current_url = page.url
    if "login" in current_url or "account-security" in current_url:
        debug_png = BASE_DIR / "upwork_after_login_debug.png"
        await page.screenshot(path=str(debug_png), full_page=True)
        print(
            f"  [warn] Still on login page after submit — 2FA or CAPTCHA?\n"
            f"  Screenshot saved: {debug_png}",
            file=sys.stderr,
        )
        return False

    print(f"  Login succeeded (url: {current_url})")
    return True


async def _get_jobs_for_query(context: BrowserContext, query: str) -> list[dict]:
    """Scrape job listings for a single search query."""
    jobs = []
    page = await context.new_page()

    for page_num in range(1, MAX_PAGES_PER_QUERY + 1):
        url = (
            f"https://www.upwork.com/nx/search/jobs/"
            f"?q={query.replace(' ', '+')}&sort=recency&page={page_num}"
        )
        print(f"    Fetching: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)  # let React render
        except Exception as e:
            print(f"    [warn] page load error: {e}", file=sys.stderr)
            break

        cards = await page.query_selector_all(SEL_JOB_TILE)
        print(f"    Found {len(cards)} job cards on page {page_num}")

        if not cards:
            break

        for card in cards:
            job = await _extract_job(card)
            if job and job["id"] not in {j["id"] for j in jobs}:
                jobs.append(job)

        await page.wait_for_timeout(1500)  # polite delay

    await page.close()
    return jobs


async def scrape_all() -> list[dict]:
    """
    Main entry point.
    - Loads saved auth state if available, otherwise performs login.
    - Iterates all SEARCH_QUERIES and collects job listings.
    - Returns deduplicated list of raw job dicts.
    """
    if not UPWORK_EMAIL or not UPWORK_PASSWORD:
        raise RuntimeError(
            "UPWORK_EMAIL / UPWORK_PASSWORD not set in environment. "
            "Copy .env.example to .env and fill in your credentials."
        )

    all_jobs: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # False = ブラウザ画面が見えるﾈ2FA対応）

        # Restore session if available
        storage_state = str(AUTH_STATE_FILE) if AUTH_STATE_FILE.exists() else None
        context = await browser.new_context(
            storage_state=storage_state,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        # Verify session is alive
        page = await context.new_page()
        await page.goto("https://www.upwork.com/nx/find-work/", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        if "login" in page.url or "signup" in page.url or "account-security" in page.url:
            print("Session expired or no saved session — logging in...")
            success = await _login(page)
            if not success:
                await browser.close()
                raise RuntimeError(
                    "Login failed. ブラウザのスクリーンショットを確認してください: upwork_login_debug.png"
                )
            # Save new auth state
            await context.storage_state(path=str(AUTH_STATE_FILE))
            print(f"  Auth state saved to {AUTH_STATE_FILE}")
        else:
            print("Using saved Upwork session.")

        await page.close()

        # Scrape each query
        for query in SEARCH_QUERIES:
            print(f"\n[scraper] Query: '{query}'")
            try:
                jobs = await _get_jobs_for_query(context, query)
                for job in jobs:
                    all_jobs[job["id"]] = job  # dedup by id
                print(f"  -> {len(jobs)} jobs found (total unique so far: {len(all_jobs)})")
            except Exception as e:
                print(f"  [error] Query '{query}' failed: {e}", file=sys.stderr)

        await browser.close()

    return list(all_jobs.values())
