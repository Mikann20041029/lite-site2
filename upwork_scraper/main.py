"""
Upwork Job Scraper — main orchestrator.

Flow:
  1. Scrape Upwork RSS feeds (no login, no browser needed)
  2. Filter out already-seen jobs (SQLite)
  3. Score each new job (rule-based)
  4. Generate proposal drafts for top jobs (DeepSeek API)
  5. Save to DB
  6. Send Discord notification with top jobs
"""
import sys
from datetime import datetime

from . import db, notifier, proposal, scorer, scraper
from .config import MIN_SCORE_TO_NOTIFY, TOP_JOBS_TO_NOTIFY


def run() -> None:
    print(f"\n{'='*60}")
    print(f"  Upwork Job Scraper  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    # 1. Init DB
    db.init_db()

    # 2. Scrape Upwork via RSS
    print("[1/5] Scraping Upwork RSS feeds...")
    raw_jobs = scraper.scrape_all()
    print(f"  Total jobs scraped: {len(raw_jobs)}")

    # 3. Filter already-seen jobs
    print("\n[2/5] Filtering duplicates...")
    new_jobs = [j for j in raw_jobs if not db.is_seen(j["id"])]
    print(f"  New jobs: {len(new_jobs)}  (skipped {len(raw_jobs) - len(new_jobs)} duplicates)")

    if not new_jobs:
        print("\nNo new jobs today.")
        notifier.send_daily_report([])
        return

    # 4. Score + generate proposals for top candidates
    print("\n[3/5] Scoring jobs...")
    scored: list[tuple[int, dict]] = []
    for job in new_jobs:
        score, reasons = scorer.score_job(job)
        job["score"] = score
        job["score_reasons"] = reasons
        scored.append((score, job))
        print(f"  [{score:+4d}] {job['title'][:60]}")

    scored.sort(key=lambda x: x[0], reverse=True)
    top_jobs = [j for s, j in scored if s >= MIN_SCORE_TO_NOTIFY][:TOP_JOBS_TO_NOTIFY]

    print(f"\n[4/5] Generating proposal drafts for top {len(top_jobs)} jobs...")
    for i, job in enumerate(top_jobs):
        print(f"  ({i+1}/{len(top_jobs)}) {job['title'][:55]}...")
        draft = proposal.generate_proposal(job)
        job["proposal_draft"] = draft

    # 5. Save all new jobs to DB
    print("\n[5/5] Saving to database...")
    for _, job in scored:
        db.save_job(job)
    print(f"  Saved {len(scored)} jobs to DB.")

    # 6. Notify
    print("\n[notifier] Sending Discord report...")
    notifier.send_daily_report(top_jobs)

    # Mark as notified
    db.mark_notified([j["id"] for j in top_jobs])

    print(f"\nDone! {len(top_jobs)} jobs sent to Discord.\n")
