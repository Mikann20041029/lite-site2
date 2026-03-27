"""Rule-based scoring for Upwork job listings."""
import re

from .config import AVOID_KEYWORDS, SCORE_WEIGHTS, TARGET_KEYWORDS


def _parse_proposals(text: str) -> int | None:
    """
    Parse proposals count from text like:
    'Less than 5', '5 to 10', '10 to 15', '20 to 50', 'Over 50'
    Returns the lower bound as int, or None if unparseable.
    """
    text = text.lower()
    if "less than 5" in text or "less than5" in text:
        return 2
    m = re.search(r"(\d+)\s*to\s*(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"over\s*(\d+)", text)
    if m:
        return int(m.group(1)) + 1
    m = re.search(r"(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def _parse_hourly_rate(budget_text: str) -> float | None:
    """
    Parse hourly rate in USD from text like '$15.00-$25.00/hr', '$20/hr', 'Fixed-price'.
    Returns the lower bound, or None.
    """
    text = budget_text.lower()
    if "fixed" in text or "fixed-price" in text:
        return None  # fixed price jobs — can't compare hourly rate
    # Match e.g. $10.00-$30.00 or $15/hr
    m = re.search(r"\$(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    return None


def score_job(job: dict) -> tuple[int, list[str]]:
    """
    Score a job dict and return (total_score, reasons_list).
    Higher score = better match for the user.
    """
    score = 0
    reasons: list[str] = []

    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    skills_str = " ".join(job.get("skills") or []).lower()
    full_text = f"{title} {desc} {skills_str}"

    # ── Positive signals ────────────────────────────────────────────────────

    # Japanese / localization keywords
    jp_kws = ["japanese", "日本語", "japan", "localization", "localisation",
              "translation", "translate", "proofreading", "proofread",
              "日本", "翻訳", "校正", "ローカライズ"]
    if any(kw in full_text for kw in jp_kws):
        w = SCORE_WEIGHTS["japanese_keywords"]
        score += w
        reasons.append(f"日本語案件 +{w}")

    # Payment verified
    if job.get("payment_verified"):
        w = SCORE_WEIGHTS["payment_verified"]
        score += w
        reasons.append(f"支払い認証済み +{w}")

    # Proposals count
    proposals = _parse_proposals(job.get("proposals_text") or "")
    if proposals is not None:
        if proposals < 5:
            w = SCORE_WEIGHTS["proposals_low"]
            score += w
            reasons.append(f"競合少ない({proposals}件未満) +{w}")
        elif proposals > 20:
            w = SCORE_WEIGHTS["proposals_many"]
            score += w
            reasons.append(f"競合多い({proposals}件以上) {w}")

    # Entry level / beginner friendly
    entry_kws = ["entry level", "entry-level", "beginner", "no experience", "0-1 year", "starter"]
    if any(kw in full_text for kw in entry_kws):
        w = SCORE_WEIGHTS["entry_level"]
        score += w
        reasons.append(f"初心者歓迎 +{w}")

    # AI / QA / evaluation keywords
    ai_qa_kws = ["ai evaluation", "ai annotation", "data collection", "quality assurance",
                 "usability test", "annotation", "labeling", "data labeling",
                 "ai trainer", "rlhf", "feedback", "model evaluation", "llm"]
    if any(kw in full_text for kw in ai_qa_kws):
        w = SCORE_WEIGHTS["ai_qa_keywords"]
        score += w
        reasons.append(f"AI/QA案件 +{w}")

    # IT / engineering
    it_kws = ["developer", "engineer", "programming", "software", "web development", "coding"]
    if any(kw in full_text for kw in it_kws):
        w = SCORE_WEIGHTS["it_keywords"]
        score += w
        reasons.append(f"IT案件 +{w}")

    # Hourly rate
    hourly = _parse_hourly_rate(job.get("budget_text") or "")
    if hourly is not None:
        if hourly < 15:  # < ~2250 JPY/hr
            w = SCORE_WEIGHTS["low_hourly_rate"]
            score += w
            reasons.append(f"時給低い(${hourly:.0f}) {w}")
        elif hourly > 25:  # > ~3750 JPY/hr
            w = SCORE_WEIGHTS["high_hourly_rate"]
            score += w
            reasons.append(f"時給高い(${hourly:.0f}) +{w}")

    # ── Negative signals ────────────────────────────────────────────────────

    # AI prohibited
    ai_prohibited_kws = ["no ai", "without ai", "no chatgpt", "no gpt", "ai prohibited",
                         "human written", "human only", "no artificial"]
    if any(kw in full_text for kw in ai_prohibited_kws):
        w = SCORE_WEIGHTS["ai_prohibited"]
        score += w
        reasons.append(f"AI禁止 {w}")

    # High experience required (5+ years)
    year_matches = re.findall(r"(\d+)\+?\s*years?\s*(?:of\s*)?(?:experience|exp)", full_text)
    if year_matches and max(int(y) for y in year_matches) >= 5:
        w = SCORE_WEIGHTS["high_experience_required"]
        score += w
        reasons.append(f"5年以上経験要求 {w}")

    # Specialized fields (legal, medical, etc.)
    specialized_kws = ["legal translation", "legal document", "medical translation",
                       "medical document", "certified translation", "notarized",
                       "pharmaceutical", "voice over", "voiceover", "recording equipment",
                       "on-site", "in-person", "in person"]
    if any(kw in full_text for kw in specialized_kws):
        w = SCORE_WEIGHTS["specialized_field"]
        score += w
        reasons.append(f"専門分野・現場案件 {w}")

    # Payment unverified
    if not job.get("payment_verified"):
        w = SCORE_WEIGHTS["payment_unverified"]
        score += w
        reasons.append(f"支払い未認証 {w}")

    return score, reasons
