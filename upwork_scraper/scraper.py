"""
Playwright scraper for Upwork job search.

First run:
  - Opens a real Chrome browser window
  - User logs in manually (handles Cloudflare, 2FA, CAPTCHA normally)
  - Session is saved to .upwork_auth_state.json

Subsequent runs:
  - Loads saved session (no login needed, no Cloudflare challenge)
  - Automatically searches and extracts job listings
"""
import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from .config import AUTH_STATE_FILE, BASE_DIR, MAX_PAGES_PER_QUERY, SEARCH_QUERIES

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP', 'ja', 'en-US', 'en']});
window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}, app: {}};
Object.defineProperty(navigator, 'permissions', {
  get: () => ({ query: () => Promise.resolve({ state: 'granted' }) })
});
"""

SEL_JOB_TILE = [
    "article[data-test='JobTile']",
    "div[data-test='job-tile']",
    "article.job-tile",
    "[data-ev-job-uid]",
]
SEL_TITLE = ["a[data-test='job-title-link']", "h2 a", ".job-title a", "h3 a"]
SEL_DESC = ["[data-test='job-description-text']", ".job-description", "p.description", "div.description"]
SEL_BUDGET = ["[data-test='job-type-label']", "[data-test='budget']", ".budget", "[data-test='is-fixed-price']"]
SEL_PROPOSALS = ["[data-test='proposals-tier']", "[data-test='proposals']", ".proposals"]
SEL_PAYMENT = ["[data-test='payment-verified']", "[data-test='payment-status']", ".payment-verified"]
SEL_LOCATION = ["[data-test='client-country']", "[data-test='location']", ".client-location"]
SEL_SKILLS = ["[data-test='token']", ".skill-badge", ".air3-token", ".up-skill-badge"]
SEL_POSTED = ["[data-test='posted-on']", "[data-test='posted']", ".posted-on", "time"]


async def _first(element, selectors):
    for sel in selectors:
        try:
            el = await element.query_selector(sel)
            if el:
                return el
        except Exception:
            pass
    return None


async def _text(element, selectors, default=""):
    el = await _first(element, selectors)
    try:
        return (await el.inner_text()).strip() if el else default
    except Exception:
        return default


async def _extract_job(card):
    try:
        title_el = await _first(card, SEL_TITLE)
        if not title_el:
            return None
        title = (await title_el.inner_text()).strip()
        href = (await title_el.get_attribute("href")) or ""
        if not title:
            return None
        m = re.search(r"_~([0-9a-zA-Z]+)", href) or re.search(r"~([0-9a-zA-Z]+)", href)
        job_id = m.group(1) if m else re.sub(r"[^a-z0-9]", "", href.lower())[-20:]
        if not job_id:
            return None
        description = await _text(card, SEL_DESC)
        budget_text = await _text(card, SEL_BUDGET)
        proposals_text = await _text(card, SEL_PROPOSALS)
        client_location = await _text(card, SEL_LOCATION)
        posted_text = await _text(card, SEL_POSTED)
        payment_el = await _first(card, SEL_PAYMENT)
        payment_verified = payment_el is not None
        skill_els = []
        for sel in SEL_SKILLS:
            skill_els = await card.query_selector_all(sel)
            if skill_els:
                break
        skills = []
        for el in skill_els:
            try:
                t = (await el.inner_text()).strip()
                if t:
                    skills.append(t)
            except Exception:
                pass
        return {
            "id": job_id,
            "title": title,
            "url": f"https://www.upwork.com{href}" if href.startswith("/") else href,
            "description": description[:1200],
            "budget_text": budget_text,
            "proposals_text": proposals_text,
            "payment_verified": payment_verified,
            "client_location": client_location,
            "skills": skills,
            "posted_text": posted_text,
        }
    except Exception as e:
        print(f"  [warn] card extract error: {e}", file=sys.stderr)
        return None


def _jobs_from_next_data(raw_json):
    try:
        data = json.loads(raw_json)
        candidates = []

        def walk(obj, depth=0):
            if depth > 12:
                return
            if isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)
            elif isinstance(obj, dict):
                if "title" in obj and ("ciphertext" in obj or "jobUid" in obj or "id" in obj):
                    candidates.append(obj)
                for v in obj.values():
                    walk(v, depth + 1)

        walk(data)
        jobs = []
        for obj in candidates:
            title = obj.get("title", "").strip()
            uid = obj.get("ciphertext") or obj.get("jobUid") or obj.get("id", "")
            if not title or not uid:
                continue
            url = f"https://www.upwork.com/jobs/{title.lower().replace(' ', '-')}_{uid}"
            budget_parts = []
            if obj.get("hourlyBudgetMin"):
                budget_parts.append(f"${obj['hourlyBudgetMin']}-${obj.get('hourlyBudgetMax', '?')}/hr")
            elif obj.get("amount", {}).get("amount"):
                budget_parts.append(f"${obj['amount']['amount']}")
            budget_text = " ".join(budget_parts)
            proposals_text = str(obj.get("proposalsTier", obj.get("totalApplicants", "")))
            skills = [s.get("prettyName", s.get("name", "")) for s in obj.get("skills", []) if isinstance(s, dict)]
            client = obj.get("client", {}) or {}
            payment_verified = bool(
                client.get("paymentVerificationStatus") == "VERIFIED" or client.get("paymentVerified")
            )
            location = client.get("location", {})
            client_location = location.get("country", "") if isinstance(location, dict) else str(location)
            jobs.append({
                "id": str(uid),
                "title": title,
                "url": url,
                "description": obj.get("description", obj.get("snippet", ""))[:1200],
                "budget_text": budget_text,
                "proposals_text": proposals_text,
                "payment_verified": payment_verified,
                "client_location": client_location,
                "skills": [s for s in skills if s],
                "posted_text": obj.get("publishTime", obj.get("createdOn", "")),
            })
        return jobs
    except Exception as e:
        print(f"  [warn] __NEXT_DATA__ parse error: {e}", file=sys.stderr)
        return []


async def _search_page_jobs(page, query, page_num):
    url = f"https://www.upwork.com/nx/search/jobs/?q={query.replace(' ', '+')}&sort=recency&page={page_num}"
    print(f"    GET {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"    [warn] page load error: {e}", file=sys.stderr)
        return []

    # Method 1: __NEXT_DATA__ JSON
    try:
        next_data = await page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : ''; }"
        )
        if next_data:
            jobs = _jobs_from_next_data(next_data)
            if jobs:
                print(f"    Found {len(jobs)} jobs via __NEXT_DATA__")
                return jobs
    except Exception as e:
        print(f"    [warn] __NEXT_DATA__ eval error: {e}", file=sys.stderr)

    # Method 2: DOM scraping
    cards = []
    for sel in SEL_JOB_TILE:
        cards = await page.query_selector_all(sel)
        if cards:
            break
    print(f"    Found {len(cards)} job cards via DOM")
    if not cards:
        debug_png = BASE_DIR / f"upwork_search_debug_p{page_num}.png"
        try:
            await page.screenshot(path=str(debug_png), full_page=False)
            print(f"    [debug] screenshot saved: {debug_png}", file=sys.stderr)
        except Exception:
            pass
        return []
    jobs = []
    for card in cards:
        job = await _extract_job(card)
        if job:
            jobs.append(job)
    return jobs


async def _ensure_logged_in(context):
    page = await context.new_page()
    await page.add_init_script(STEALTH_SCRIPT)
    print("  Checking Upwork session...")
    await page.goto("https://www.upwork.com/nx/find-work/", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    if "login" not in page.url and "account-security" not in page.url:
        print("  Session is valid - skipping login.")
        return page
    print()
    print("  ★ ブラウザウィンドウが開きます。Upworkに普通にログインしてください。")
    print("  ★ Cloudflare/2FAも普通に対応してOKです。")
    print("  ★ ログイン完了後、自動的に続きが動きます（最大5分待ちます）。")
    print()
    await page.goto("https://www.upwork.com/ab/account-security/login", wait_until="domcontentloaded", timeout=30000)

    def is_logged_in(url):
        return "login" not in url and "account-security" not in url and "signup" not in url and "upwork.com" in url

    try:
        await page.wait_for_url(is_logged_in, timeout=300_000)
    except Exception:
        raise RuntimeError("ログインが5分以内に完了しませんでした。もう一度実行してください。")
    print(f"  ログイン確認: {page.url}")
    await context.storage_state(path=str(AUTH_STATE_FILE))
    print(f"  セッションを保存しました → {AUTH_STATE_FILE}")
    return page


async def scrape_all():
    all_jobs = {}
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=False,
                channel="chrome",
                slow_mo=30,
                args=["--disable-blink-features=AutomationControlled"],
            )
            print("  Using system Chrome.")
        except Exception:
            browser = await pw.chromium.launch(
                headless=False,
                slow_mo=30,
                args=["--disable-blink-features=AutomationControlled"],
            )
            print("  Using Playwright Chromium (Chrome not found).")

        storage_state = str(AUTH_STATE_FILE) if AUTH_STATE_FILE.exists() else None
        context = await browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await context.add_init_script(STEALTH_SCRIPT)

        home_page = await _ensure_logged_in(context)
        await home_page.close()

        page = await context.new_page()
        await page.add_init_script(STEALTH_SCRIPT)

        for query in SEARCH_QUERIES:
            print(f"\n[scraper] Query: '{query}'")
            query_new = 0
            for pnum in range(1, MAX_PAGES_PER_QUERY + 1):
                jobs = await _search_page_jobs(page, query, pnum)
                if not jobs:
                    break
                for job in jobs:
                    if job["id"] not in all_jobs:
                        all_jobs[job["id"]] = job
                        query_new += 1
                await asyncio.sleep(1.5)
            print(f"  -> {query_new} new unique jobs from this query")

        await page.close()
        await browser.close()

    print(f"\n[scraper] Total unique jobs: {len(all_jobs)}")
    return list(all_jobs.values())
