"""Discord webhook notifications for top-ranked jobs."""
import json
import sys

import requests

from .config import DISCORD_WEBHOOK_URL, TOP_JOBS_TO_NOTIFY


def _score_bar(score: int) -> str:
    """Visual score bar for Discord."""
    clipped = max(0, min(score, 100))
    filled = clipped // 10
    return "🟩" * filled + "⬜" * (10 - filled) + f"  **{score}pt**"


def _job_embed(job: dict, rank: int) -> dict:
    """Build a Discord embed for a single job."""
    title = job.get("title", "No title")
    url = job.get("url", "")
    score = job.get("score", 0)
    reasons = json.loads(job.get("score_reasons") or "[]")
    proposal = job.get("proposal_draft", "")
    budget = job.get("budget_text", "不明")
    proposals_text = job.get("proposals_text", "不明")
    location = job.get("client_location", "不明")
    payment_ok = bool(job.get("payment_verified"))

    reasons_str = "\n".join(f"• {r}" for r in reasons) if reasons else "（詳細なし）"
    payment_icon = "✅" if payment_ok else "❌"

    description_parts = [
        f"{_score_bar(score)}",
        "",
        f"💰 予算: `{budget}`",
        f"📩 提案数: `{proposals_text}`",
        f"🌍 クライアント: `{location}`",
        f"{payment_icon} 支払い認証: {'済み' if payment_ok else '未認証'}",
        "",
        "**スコア詳細:**",
        reasons_str,
    ]

    if proposal:
        description_parts += [
            "",
            "**📝 提案文ドラフト:**",
            f"```\n{proposal[:400]}\n```",
        ]

    return {
        "title": f"#{rank}  {title}",
        "url": url,
        "description": "\n".join(description_parts),
        "color": 0x14A800 if score >= 50 else 0xF2C94C if score >= 20 else 0x9B9B9B,
    }


def send_daily_report(jobs: list[dict]) -> None:
    """
    Send the daily top-jobs report to Discord.
    jobs: list of job dicts (already sorted by score, top N).
    """
    if not DISCORD_WEBHOOK_URL:
        print("[notifier] DISCORD_WEBHOOK_URL not set — skipping notification.", file=sys.stderr)
        return

    if not jobs:
        payload = {
            "content": "📭 **今日の新規案件はありませんでした。** また明日確認します。",
        }
        _send(payload)
        return

    embeds = [_job_embed(job, i + 1) for i, job in enumerate(jobs[:10])]  # Discord limit: 10 embeds

    payload = {
        "content": (
            f"🔍 **今日のUpwork案件レポート** — 上位{len(jobs)}件\n"
            f"👆 確認して気に入った案件の提案文を送信してください！"
        ),
        "embeds": embeds,
    }
    _send(payload)
    print(f"[notifier] Sent Discord report with {len(jobs)} jobs.")


def _send(payload: dict) -> None:
    """POST payload to Discord webhook."""
    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code not in (200, 204):
            print(f"[notifier] Discord returned {resp.status_code}: {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"[notifier] Request error: {e}", file=sys.stderr)
