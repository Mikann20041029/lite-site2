#!/usr/bin/env python3
"""
セットアップ確認スクリプト。
.env が正しく設定できているか全部チェックしてくれます。

使い方:
    python check_setup.py
"""
import importlib.util
import json
import os
import subprocess
import sys


def check(label: str, ok: bool, detail: str = "") -> bool:
    icon = "✅" if ok else "❌"
    print(f"  {icon} {label}", end="")
    if detail:
        print(f"  → {detail}", end="")
    print()
    return ok


def main():
    all_ok = True
    print("\n" + "=" * 55)
    print("  Upwork Scraper セットアップ確認")
    print("=" * 55 + "\n")

    # ── 1. Python version ──────────────────────────────
    print("[1] Python バージョン")
    pv = sys.version_info
    ok = pv >= (3, 10)
    all_ok &= check(f"Python {pv.major}.{pv.minor}.{pv.micro}", ok,
                    "" if ok else "3.10 以上が必要です。python3 --version で確認してください。")
    print()

    # ── 2. Required packages ─────────────────────────
    print("[2] 必要なパッケージ")
    packages = {
        "playwright": "playwright",
        "openai": "openai",
        "dotenv": "python-dotenv",
        "requests": "requests",
    }
    for mod, pkg in packages.items():
        found = importlib.util.find_spec(mod) is not None
        all_ok &= check(pkg, found,
                        "" if found else f"pip install {pkg} を実行してください")

    # Playwright browsers
    try:
        result2 = subprocess.run(
            [sys.executable, "-c",
             "from playwright.sync_api import sync_playwright; p = sync_playwright().__enter__(); "
             "b = p.chromium.launch(); b.close(); p.__exit__(None,None,None)"],
            capture_output=True, text=True, timeout=20
        )
        browser_ok = result2.returncode == 0
    except Exception:
        browser_ok = False
    all_ok &= check("Playwright Chromium", browser_ok,
                    "" if browser_ok else "playwright install chromium を実行してください")
    print()

    # ── 3. .env file ──────────────────────────────
    print("[3] .env ファイル")
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env_exists = os.path.exists(env_path)
    all_ok &= check(".env ファイル存在", env_exists,
                    "" if env_exists else ".env ファイルがないです")

    if env_exists:
        from dotenv import dotenv_values
        env = dotenv_values(env_path)

        keys = {
            "UPWORK_EMAIL": "Upworkのメールアドレス",
            "UPWORK_PASSWORD": "Upworkのパスワード",
            "DEEPSEEK_API_KEY": "DeepSeek APIキー",
            "DISCORD_WEBHOOK_URL": "Discord Webhook URL",
        }
        for key, hint in keys.items():
            val = env.get(key, "")
            ok = bool(val and val not in ("your_upwork_email@example.com",
                                          "your_upwork_password",
                                          "sk-xxxxxxxxxxxxxxxxxxxxxxxx",
                                          "https://discord.com/api/webhooks/xxxx/xxxx"))
            all_ok &= check(f"{key}", ok,
                            "" if ok else f"未設定 → {hint}")
    print()

    # ── 4. Discord webhook test ──────────────────────
    print("[4] Discord Webhook テスト送信")
    if env_exists:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        if webhook_url and "discord.com/api/webhooks" in webhook_url:
            try:
                import requests
                resp = requests.post(
                    webhook_url,
                    json={"content": "✅ Upwork Scraper のセットアップ確認テストです！\nこのメッセージが届いていれば Discord の設定は完了です。"},
                    timeout=10,
                )
                ok = resp.status_code in (200, 204)
                all_ok &= check("Discord テスト送信", ok,
                                "" if ok else f"失敗 (HTTP {resp.status_code}): {resp.text[:100]}")
            except Exception as e:
                all_ok &= check("Discord テスト送信", False, str(e))
        else:
            all_ok &= check("Discord テスト送信", False, "DISCORD_WEBHOOK_URL が未設定")
    else:
        print("  ⏭  .env がないのでスキップ")
    print()

    # ── Summary ──────────────────────────────────────
    print("=" * 55)
    if all_ok:
        print("  🎉 全部OK！python run_scraper.py を実行できます！")
    else:
        print("  ⚠️  上の ❌ を全部直してから再実行してください。")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
