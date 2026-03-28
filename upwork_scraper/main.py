"""
Upwork Job Scraper - main orchestrator.

Flow:
  1. Scrape Upwork (Playwright + real Chrome, session reuse)
  2. Filter out already-seen jobs (SQLite dedup)
  3. Score each new job (rule-based)
  4. Generate proposal drafts for top jobs (DeepSeek API)
  5. Save to DB
  6. Send Discord notification with top jobs
"""
import asyncio
import sys
from datetime import datetime

from . import db, notifier, proposal, scorer, scraper
from .config import MIN_SCORE_TO_NOTIFY, TOP_JOBS_TO_NOTIFY


def run():
    print(f"\n{'='*60}")
    print(f"  Upwork Job Scraper  -  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    db.init_db()

    print("[1/5] Scraping Upwork...")
    try:
        raw_jobs = asyncio.run(scraper.scrape_all())
    except RuntimeError as e:
        print(f"\n[FATAL] {e}", file=sys.stderr)
        sys.exit(1)

    total = len(raw_jobs)
    print(f"  Total jobs scraped: {total}")

    if total == 0:
        print(
            "\n[FATAL] 0件取得。考えられる原因:\n"
            "  1. セッション切れ → .upwork_auth_state.json を削除して再実行\n"
            "  2. Upworkのページ構造変更 → scraper.py のセレクタ更新が必要\n"
            "  3. ネットワークエラー → 接続を確認してください",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n[2/5] Filtering duplicates...")
    new_jobs = [j for j in raw_jobs if not db.is_seen(j["id"])]
    print(f"  New jobs: {len(new_jobs)}  (skipped {total - len(new_jobs)} already seen)")

    if not new_jobs:
        print("\n今日は新しい案件がありません。また明日実行してください。")
        notifier.send_daily_report([])
        return

    print("\n[3/5] Scoring jobs...")
    scored = []
    for job in new_jobs:
        score, reasons = scorer.score_job(job)
        job["score"] = score
        job["score_reasons"] = reasons
        scored.append((score, job))
        print(f"  [{score:+4d}] {job['title'][:60]}")

    scored.sort(key=lambda x: x[0], reverse=True)
    top_jobs = [j for s, j in scored if s >= MIN_SCORE_TO_NOTIFY][:TOP_JOBS_TO_NOTIFY]

    if not top_jobs:
        print(f"\n  スコア{MIN_SCORE_TO_NOTIFY}以上の案件なし。config.py の MIN_SCORE_TO_NOTIFY を下げると表示されます。")

    print(f"\n[4/5] Generating proposal drafts for top {len(top_jobs)} jobs...")
    for i, job in enumerate(top_jobs):
        print(f"  ({i+1}/{len(top_jobs)}) {job['title'][:55]}...")
        draft = proposal.generate_proposal(job)
        job["proposal_draft"] = draft

    print("\n[5/5] Saving to database...")
    for _, job in scored:
        db.save_job(job)
    print(f"  Saved {len(scored)} jobs.")

    print("\n[notifier] Sending Discord report...")
    notifier.send_daily_report(top_jobs)
    db.mark_notified([j["id"] for j in top_jobs])

    print(f"\nDone! {len(top_jobs)} jobs sent to Discord.\n")
