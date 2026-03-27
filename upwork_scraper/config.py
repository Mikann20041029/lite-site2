import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Upwork credentials ---
UPWORK_EMAIL = os.getenv("UPWORK_EMAIL", "")
UPWORK_PASSWORD = os.getenv("UPWORK_PASSWORD", "")

# --- DeepSeek API ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

# --- Discord ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- Search queries (Upwork) ---
SEARCH_QUERIES = [
    "japanese translation",
    "japanese localization proofreading",
    "AI evaluation japanese",
    "QA tester japanese",
    "data collection japan resident",
]

# --- Paths ---
BASE_DIR = Path(__file__).parent.parent
AUTH_STATE_FILE = BASE_DIR / ".upwork_auth_state.json"
DB_PATH = BASE_DIR / "jobs.db"

# --- Scraping settings ---
MAX_PAGES_PER_QUERY = 2   # pages per search query
TOP_JOBS_TO_NOTIFY = 5    # top N jobs to send in Discord notification
MIN_SCORE_TO_NOTIFY = 10  # skip jobs with score below this

# --- Scoring weights ---
SCORE_WEIGHTS = {
    "japanese_keywords": 30,
    "payment_verified": 20,
    "proposals_low": 25,      # < 5 proposals
    "entry_level": 20,
    "ai_qa_keywords": 20,
    "it_keywords": 15,
    "high_hourly_rate": 15,   # > $25/hr
    "proposals_many": -15,    # > 20 proposals
    "low_hourly_rate": -30,   # < $15/hr
    "ai_prohibited": -20,
    "high_experience_required": -15,  # 5+ years
    "specialized_field": -25,         # legal/medical/accounting
    "payment_unverified": -20,
}

# --- User profile (used for proposal generation) ---
USER_PROFILE = """
・日本語ネイティブスピーカー
・英語対応可能（ビジネスレベル、完璧ではないが実用的）
・ITエンジニア経験あり（Web開発・システム開発）
・AI/QA経験あり（AI評価・品質保証・データ収集・アノテーション）
・AIツールを活用した作業が得意、AIとの協業に慣れている
・翻訳・ローカライゼーション・校正・テスト業務対応可能
・日本市場・日本語品質に関する深い知識
・フリーランス初期段階（実績は少ないがスキルは高い）
""".strip()

# --- Job categories to target ---
TARGET_KEYWORDS = [
    "japanese", "日本語", "japan", "translation", "localization",
    "localisation", "proofreading", "proofread", "ai evaluation",
    "ai annotation", "data collection", "qa", "quality assurance",
    "usability test", "feedback", "annotation", "labeling",
    "developer", "engineer",
]

# --- Job categories to avoid ---
AVOID_KEYWORDS = [
    "voice over", "voiceover", "recording equipment", "on-site",
    "in-person", "legal translation", "medical translation",
    "certified translation", "notarized",
]
