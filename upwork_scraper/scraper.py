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

# ── selectors (update here if Upwork changes HTML) ──────────────────────────
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


async def _login(page: Page) -> bool:
    """Perform Upwork login. Returns True on success."""
    print("  Navigating to Upwork login...")
    await page.goto("https://www.upwork.com/login", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # Step 1: email
    try:
        email_input = await page.wait_for_selector(
            'input[name="login[username]"], input[type="email"], #login_username',
            timeout=8000,
        )
        await email_input.fill(UPWORK_EMAIL)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  [error] Could not find email input: {e}", file=sys.stderr)
        return False

    # Step 2: password
    try:
        pw_input = await page.wait_for_selector(
            'input[name="login[password]"], input[type="password"], #login_password',
            timeout=8000,
        )
        await pw_input.fill(UPWORK_PASSWORD)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(4000)
    except Exception as e:
        print(f"  [error] Could not find password input: {e}", file=sys.stderr)
        return False

    # Check success
    current_url = page.url
    if "login" in current_url:
        print("  [warn] Still on login page — check credentials or 2FA", file=sys.stderr)
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
        browser = await pw.chromium.launch(headless=True)

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

        if "login" in page.url or "signup" in page.url:
            print("Session expired or no saved session — logging in...")
            await page.goto("https://www.upwork.com/login", wait_until="domcontentloaded", timeout=20000)
            success = await _login(page)
            if not success:
                await browser.close()
                raise RuntimeError(
                    "Login failed. If you have 2FA enabled, run with headless=False "
                    "to complete it manually, then re-run."
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
