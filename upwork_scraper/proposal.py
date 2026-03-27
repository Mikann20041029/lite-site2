"""Generate cover letter drafts using DeepSeek."""
from .ai_client import chat
from .config import USER_PROFILE

SYSTEM_PROMPT = f"""あなたはUpworkのフリーランス提案文の専門家です。
以下の応募者プロフィールを元に、Upworkの案件に対する短い提案文を英語で書いてください。

応募者プロフィール:
{USER_PROFILE}

ルール:
- 2〜4文の短い提案文（長すぎない）
- 案件の内容に具体的に言及する
- 実績の誇張・嘘は書かない
- 必要に応じて日本語ネイティブ・英語対応・AI/QA経験を自然に盛り込む
- 丁寧でプロフェッショナルなトーン
- 最後にConnects消費前に自分で確認するための文は不要（提案文本文だけ）
- Markdown記法不要、プレーンテキストで
"""


def generate_proposal(job: dict) -> str:
    """
    Generate a proposal draft for the given job.
    Returns the draft text (English), or empty string on failure.
    """
    user_prompt = f"""以下の案件に対して提案文を書いてください。

案件タイトル: {job.get('title', '')}
案件説明: {job.get('description', '')[:600]}
スキル: {', '.join(job.get('skills') or [])}
予算: {job.get('budget_text', '不明')}
"""
    return chat(SYSTEM_PROMPT, user_prompt, max_tokens=300)
