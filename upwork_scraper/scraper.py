"""
Gmail IMAP-based Upwork job scraper.

How it works:
  1. User sets up Upwork saved searches with instant email alerts
  2. Upwork sends HTML emails to Gmail when new matching jobs appear
  3. This script reads those unread emails via Gmail IMAP
  4. Parses job listings from the email HTML
  5. Returns structured job dicts for scoring/notification

Setup (one-time):
  - Enable Upwork job alerts: Upwork → Find Work → Saved Searches → turn on alerts
  - Create Gmail App Password: myaccount.google.com → Security → 2-Step Verification → App passwords
  - Add GMAIL_EMAIL and GMAIL_APP_PASSWORD to .env
"""
import email
import imaplib
import re
import sys
from email.header import decode_header
from html import unescape

from bs4 import BeautifulSoup

from .config import GMAIL_APP_PASSWORD, GMAIL_EMAIL


def _connect() -> imaplib.IMAP4_SSL:
    if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "GMAIL_EMAIL / GMAIL_APP_PASSWORD が .env に設定されていません。\n"
            "Googleアカウントでアプリパスワードを作成して設定してください。"
        )
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        return mail
    except imaplib.IMAP4.error as e:
        raise RuntimeError(
            f"Gmail ログイン失敗: {e}\n"
            "GMAIL_APP_PASSWORD が正しいか確認してください。\n"
            "通常のパスワードではなく「アプリパスワード」(16文字)が必要です。"
        )


def _job_id(url: str) -> str:
    m = re.search(r"_~([0-9a-zA-Z]+)", url) or re.search(r"~([0-9a-zA-Z]+)", url)
    if m:
        return m.group(1)
    return re.sub(r"[^a-z0-9]", "", url.lower())[-20:]


def _parse_email_html(html: str) -> list[dict]:
    """
    Parse Upwork job alert email HTML and return list of job dicts.
    Upwork emails list multiple jobs per message.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    seen_ids = set()

    job_links = soup.find_all(
        "a",
        href=re.compile(r"https?://www\.upwork\.com/jobs/"),
    )

    for link in job_links:
        href = link.get("href", "").split("?")[0]
        title = link.get_text(strip=True)

        if not title or len(title) < 5:
            continue

        job_id = _job_id(href)
        if not job_id or job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        # Walk up DOM to find container with description/budget
        container = link
        for _ in range(8):
            parent = container.parent
            if parent is None:
                break
            if len(parent.get_text(strip=True)) > 200:
                container = parent
                break
            container = parent

        ctx = container.get_text(separator=" ", strip=True)

        budget_m = re.search(
            r"\$[\d,]+(?:\.\d+)?(?:\s*[-\u2013]\s*\$[\d,]+(?:\.\d+)?)?(?:\s*/\s*hr)?",
            ctx,
            re.IGNORECASE,
        )
        budget_text = budget_m.group(0) if budget_m else ""
        description = ctx.replace(title, "").strip()[:1000]

        jobs.append({
            "id": job_id,
            "title": title,
            "url": href,
            "description": description,
            "budget_text": budget_text,
            "proposals_text": "",
            "payment_verified": False,
            "client_location": "",
            "skills": [],
            "posted_text": "",
        })

    return jobs


def _get_html_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="ignore")
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="ignore")
    return ""


def _subject(msg) -> str:
    raw = msg.get("Subject") or ""
    parts = decode_header(raw)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="ignore"))
        else:
            result.append(str(part))
    return " ".join(result)


def scrape_all() -> list[dict]:
    """
    Read unread Upwork job alert emails from Gmail and return job listings.
    Marks processed emails as read so they are not re-processed next run.
    """
    print(f"  Connecting to Gmail ({GMAIL_EMAIL})...")
    mail = _connect()
    all_jobs: dict[str, dict] = {}

    try:
        mail.select("INBOX")
        _, data = mail.search(None, '(UNSEEN FROM "no-reply@upwork.com")')
        msg_ids = data[0].split() if data[0] else []
        print(f"  Unread Upwork emails: {len(msg_ids)}")

        if not msg_ids:
            print(
                "  メールが0件です。\n"
                "  Upworkの「保存検索」でメールアラートをONにしてください。\n"
                "  Upwork → Find Work → Saved Searches → toggle alerts"
            )

        for msg_id in msg_ids:
            _, raw = mail.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            subj = _subject(msg)
            print(f"    Subject: {subj[:70]}")

            html = _get_html_body(msg)
            if not html:
                continue

            jobs = _parse_email_html(html)
            print(f"    -> {len(jobs)} jobs found")

            for job in jobs:
                if job["id"] not in all_jobs:
                    all_jobs[job["id"]] = job

            mail.store(msg_id, "+FLAGS", "\\Seen")

    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass

    print(f"\n[scraper] Total unique jobs: {len(all_jobs)}")
    return list(all_jobs.values())
