import json
import os
import re
import hashlib
import html
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Any

import feedparser
from dateutil import parser as dtparser
from jinja2 import Environment, FileSystemLoader, select_autoescape


DIST_DIR = "dist"
TEMPLATES_DIR = "templates"
ASSETS_DIR = "assets"


@dataclass
class Post:
    title: str
    url: str
    source: str
    published: datetime
    summary: str
    slug: str


def _safe_slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s[:80] if s else "post"


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def _parse_date(entry: Dict[str, Any]) -> datetime:
    for k in ("published", "updated", "created"):
        if k in entry and entry[k]:
            try:
                dt = dtparser.parse(entry[k])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _clean_summary(html_or_text: str) -> str:
    # decode HTML entities (e.g., &#32;)
    text = html.unescape(html_or_text or "")
    # strip tags (simple)
    text = re.sub(r"<[^>]+>", " ", text)
    # normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_config(path: str = "site.config.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_posts(cfg: Dict[str, Any]) -> List[Post]:
    posts: List[Post] = []
    max_items = int(cfg.get("max_items_per_feed", 15))

    for feed_url in cfg.get("feeds", []):
        parsed = feedparser.parse(feed_url)
        source_title = (parsed.feed.get("title") or feed_url).strip()
        source_title = html.unescape(source_title)

        if getattr(parsed, "bozo", 0):
            print(f"[WARN] Feed parse issue: {feed_url}")

        entries = getattr(parsed, "entries", [])[:max_items]
        if not entries:
            print(f"[WARN] No entries: {feed_url}")
            continue

        for e in entries:
            title = html.unescape((e.get("title") or "Untitled").strip())
            url = (e.get("link") or "").strip()
            if not url:
                continue

            summary = _clean_summary(e.get("summary") or e.get("description") or "")
            published = _parse_date(e)

            base_slug = _safe_slug(title)
            slug = f"{base_slug}-{_hash(url)}"

            posts.append(Post(
                title=title,
                url=url,
                source=source_title,
                published=published,
                summary=summary,
                slug=slug
            ))

    posts.sort(key=lambda p: p.published, reverse=True)
    return posts


def ensure_dirs():
    os.makedirs(DIST_DIR, exist_ok=True)
    os.makedirs(os.path.join(DIST_DIR, "posts"), exist_ok=True)
    os.makedirs(os.path.join(DIST_DIR, "assets"), exist_ok=True)


def copy_assets():
    if not os.path.isdir(ASSETS_DIR):
        return
    dst = os.path.join(DIST_DIR, "assets")
    for root, _, files in os.walk(ASSETS_DIR):
        for fn in files:
            sp = os.path.join(root, fn)
            rel = os.path.relpath(sp, ASSETS_DIR)
            dp = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            with open(sp, "rb") as rf, open(dp, "wb") as wf:
                wf.write(rf.read())


def build():
    cfg = load_config()
    ensure_dirs()

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )

    posts = fetch_posts(cfg)

    index_t = env.get_template("index.html")
    with open(os.path.join(DIST_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_t.render(
            site_title=cfg.get("site_title", "One-Shot Lite RSS Digest"),
            site_description=cfg.get("site_description", ""),
            generated_at=datetime.now(timezone.utc),
            posts=posts[:50],
            base_url=cfg.get("base_url", "").rstrip("/")
        ))

    post_t = env.get_template("post.html")
    for p in posts[:200]:
        out_path = os.path.join(DIST_DIR, "posts", f"{p.slug}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(post_t.render(
                site_title=cfg.get("site_title", "One-Shot Lite RSS Digest"),
                post=p,
                base_url=cfg.get("base_url", "").rstrip("/")
            ))

    with open(os.path.join(DIST_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\n")

    copy_assets()
    print(f"[OK] Built {len(posts)} posts -> {DIST_DIR}/")


if __name__ == "__main__":
    build()
