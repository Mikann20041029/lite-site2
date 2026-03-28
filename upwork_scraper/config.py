import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Gmail (for reading Upwork alert emails) ---
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# --- DeepSeek API ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

# --- Discord ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- Paths ---
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "jobs.db"

# --- Settings ---
TOP_JOBS_TO_NOTIFY = 5
MIN_SCORE_TO_NOTIFY = 10

# --- Scoring weights ---
SCORE_WEIGHTS = {
    "japanese_keywords": 30,
    "payment_verified": 20,
    "proposals_low": 25,
    "entry_level": 20,
    "ai_qa_keywords": 20,
    "it_keywords": 15,
    "high_hourly_rate": 15,
    "proposals_many": -15,
    "low_hourly_rate": -30,
    "ai_prohibited": -20,
    "high_experience_required": -15,
    "specialized_field": -25,
    "payment_unverified": -20,
}

# --- User profile (for proposal generation) ---
USER_PROFILE = """
・日本語ネイティブスピーカー
・英語対応可能（ビジネスレベル、実用的）
・ITエンジニア経験あり（Web開発・システム開発）
・AI/QA経験あり（AI評価・品質保証・データ収集・アノテーション）
・AIツールを活用した作業が得意、AIとの協業に慣れている
・翻訳・ローカライゼーション・校正・テスト業務対応可能
・日本市場・日本語品質に関する深い知識
・フリーランス初期段階（実績は少ないがスキルは高い）
""".strip()
