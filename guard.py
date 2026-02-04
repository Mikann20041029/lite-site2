import argparse
import json
import os
import sys
from datetime import datetime, timezone

LOCK_PATH = os.path.join(".lite", "lock.json")

def die(msg: str, code: int = 2):
    print(msg)
    sys.exit(code)

def check():
    if os.path.exists(LOCK_PATH):
        try:
            with open(LOCK_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("locked_at", "unknown")
            die(f"[LOCKED] This trial has already been executed once (locked_at={ts}).\n"
                f"To run again, you must delete {LOCK_PATH} and recreate the workflow file.",
                3)
        except Exception:
            die(f"[LOCKED] This trial has already been executed once.\n"
                f"To run again, you must delete {LOCK_PATH} and recreate the workflow file.",
                3)
    print("[OK] Not locked yet.")

def lock():
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    payload = {
        "locked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "one-shot lite lock"
    }
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] Locked -> {LOCK_PATH}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--lock", action="store_true")
    args = ap.parse_args()

    if args.check:
        check()
        return
    if args.lock:
        lock()
        return
    die("Usage: python guard.py --check | --lock", 1)

if __name__ == "__main__":
    main()
