#!/usr/bin/env python3
"""Check Prime Intellect API-key reachability without creating resources."""

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.primeintellect.ai/api/v1"
CONFIG_DIR = Path(os.environ.get("PRIME_CONFIG_DIR") or Path.home() / ".config" / "prime-gpu")
KEY_FILE = CONFIG_DIR / "key"
FALLBACK_KEY_FILES = [Path.home() / ".config" / "prime-balance" / "key"]
TIMEOUT = 15

CHECKS = [
    ("availability:read", f"{API_BASE}/availability/gpus?page_size=1"),
    ("billing:read", f"{API_BASE}/billing/wallet"),
    ("instances:read", f"{API_BASE}/pods/?limit=1"),
]


def normalize_key(raw):
    if not raw:
        return None
    key = raw.strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    if not key or key.startswith("PASTE_"):
        return None
    return key


def fingerprint(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def get_keys():
    keys = []
    seen = set()

    def add(label, raw):
        key = normalize_key(raw)
        if key and key not in seen:
            seen.add(key)
            keys.append({"label": label, "key": key, "fingerprint": fingerprint(key)})

    add("PRIME_API_KEY", os.environ.get("PRIME_API_KEY"))
    for path in [KEY_FILE, *FALLBACK_KEY_FILES]:
        try:
            add(str(path), path.read_text())
        except (FileNotFoundError, PermissionError):
            continue
    return keys


def get_json(url, key):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None
    except Exception as e:
        return None, {"error": str(e)}


def detail_text(data):
    if isinstance(data, dict):
        detail = data.get("detail") or data.get("error") or data.get("message")
        if detail:
            return str(detail)
    return ""


def main():
    keys = get_keys()
    if not keys:
        print(f"No API key found. Save one to {KEY_FILE} or set PRIME_API_KEY.")
        return 2

    print("Prime Intellect API permission check")
    print(f"Config dir: {CONFIG_DIR}")
    print()

    for item in keys:
        print(f"{item['label']} ({item['fingerprint']})")
        for name, url in CHECKS:
            status, data = get_json(url, item["key"])
            marker = "ok" if status == 200 else "fail"
            detail = detail_text(data)
            suffix = f" - {detail}" if detail else ""
            print(f"  {marker:4} {name:17} HTTP {status}{suffix}")
        print()

    print("Note: pod creation cannot be tested safely here because it would")
    print("create a billable resource. For deploy clicks, the key also needs")
    print("Prime's Instances -> Read and write permission.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
