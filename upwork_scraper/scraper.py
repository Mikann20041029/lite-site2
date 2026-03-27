"""RSS-based Upwork scraper — no login, no Playwright, no Cloudflare issues."""
import re
import sys
from html import unescape

import feedparser
import requests

from .config import MAX_PAGES_PER_QUERY, SEARCH_QUERIES

# Upwork RSS endpoint
RSS_BASE = "https://www.upwork.com/ab/feed/jobs/rss"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _parse_description(html: str) -> dict:
    """
    Extract structured fields from Upwork's RSS <description> HTML.
    Returns dict with keys: description, budget_text, skills, client_location,
    payment_verified, proposals_text.
    """
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"\s+", " ", text).strip()

    result = {
        "description": "",
        "budget_text": "",
        "skills": [],
        "client_location": "",
        "payment_verified": False,
        "proposals_text": "",
    }

    # Pull out description (everything before the meta fields)
    desc_match = re.split(r"(?:Budget|Hourly Range|Fixed Price|Skills|Country|Payment):", text, maxsplit=1)
    result["description"] = desc_match[0].strip()[:1200]

    # Budget / Hourly
    m = re.search(r"(?:Hourly Range|Budget|Fixed Price)[:\s]+([^\n]+?)(?:\s{2,}|$)", text)
    if m:
        result["budget_text"] = m.group(1).strip()

    # Skills
    m = re.search(r"Skills[:\s]+([^\n]+?)(?:\s{2,}|$)", text)
    if m:
        result["skills"] = [s.strip() for s in m.group(1).split(",") if s.strip()]

    # Country
    m = re.search(r"Country[:\s]+([^\n]+?)(?:\s{2,}|$)", text)
    if m:
        result["client_location"] = m.group(1).strip()

    # Payment verified (Upwork sometimes includes this)
    if "payment verified" in text.lower():
        result["payment_verified"] = True

    # Proposals
    m = re.search(r"Proposals[:\s]+([^\n]+?)(?:\s{2,}|$)", text)
    if m:
        result["proposals_text"] = m.group(1).strip()

    return result


def _job_id_from_url(url: str) -> str:
    """Extract job ID from Upwork job URL."""
    m = re.search(r"_~([0-9a-zA-Z]+)", url) or re.search(r"~([0-9a-zA-Z]+)", url)
    if m:
        return m.group(1)
    # Fallback: use last path segment
    return re.sub(r"[^a-z0-9]", "", url.lower())[-24:]


def _fetch_rss(query: str, paging: int = 0) -> list[dict]:
    """Fetch one page of RSS results for a query."""
    params = {
        "q": query,
        "sort": "recency",
        "paging": f"{paging};10",
    }
    try:
        resp = requests.get(RSS_BASE, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [warn] RSS fetch failed for '{query}': {e}", file=sys.stderr)
        return []

    feed = feedparser.parse(resp.text)
    jobs = []

    for entry in feed.entries:
        url = entry.get("link", "")
        job_id = _job_id_from_url(url)
        title = entry.get("title", "").strip()

        if not title or not job_id:
            continue

        desc_html = entry.get("summary", "") or entry.get("description", "")
        parsed = _parse_description(desc_html)

        jobs.append({
            "id": job_id,
            "title": title,
            "url": url,
            "description": parsed["description"],
            "budget_text": parsed["budget_text"],
            "proposals_text": parsed["proposals_text"],
            "payment_verified": parsed["payment_verified"],
            "client_location": parsed["client_location"],
            "skills": parsed["skills"],
            "posted_text": entry.get("published", ""),
        })

    return jobs


def scrape_all() -> list[dict]:
    """
    Fetch jobs from Upwork RSS feeds for all configured search queries.
    Returns a deduplicated list of raw job dicts.
    No login, no browser, no Cloudflare issues.
    """
    all_jobs: dict[str, dict] = {}

    for query in SEARCH_QUERIES:
        print(f"\n[scraper] Query: '{query}'")
        query_count = 0

        for page in range(MAX_PAGES_PER_QUERY):
            paging = page * 10
            jobs = _fetch_rss(query, paging=paging)
            print(f"  page {page + 1}: {len(jobs)} jobs")

            if not jobs:
                break

            for job in jobs:
                if job["id"] not in all_jobs:
                    all_jobs[job["id"]] = job
                    query_count += 1

        print(f"  -> {query_count} new unique jobs from this query")

    print(f"\n[scraper] Total unique jobs: {len(all_jobs)}")
    return list(all_jobs.values())
