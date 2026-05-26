#!/usr/bin/env python3
# <bitbar.title>Prime Intellect GPU Availability</bitbar.title>
# <bitbar.version>1.0.0</bitbar.version>
# <bitbar.author>Denis</bitbar.author>
# <bitbar.desc>Watch Prime Intellect GPU availability against a list of {gpu_type, min, max} configs. Combines with wallet balance.</bitbar.desc>
# <bitbar.dependencies>python3</bitbar.dependencies>
# <bitbar.refreshOnOpen>true</bitbar.refreshOnOpen>

import base64
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API_BASE = "https://api.primeintellect.ai/api/v1"
GPU_ENDPOINT = f"{API_BASE}/availability/gpus"
WALLET_ENDPOINT = f"{API_BASE}/billing/wallet"
DASHBOARD = "https://app.primeintellect.ai"
TIMEOUT = 6
AUTH_STATUSES = {401, 403}

MATCH_HEX = "#d4423a"
NONE_HEX = "#888888"
ERROR_HEX = "#aa4444"
HEADER_HEX = "#999999"
MATCH_GLYPH = "●"
NONE_GLYPH = "·"

SCRIPT_DIR = Path(os.path.realpath(__file__)).parent
DEPLOY_BIN = SCRIPT_DIR / "bin" / "prime-deploy.py"
AUTH_CHECK_BIN = SCRIPT_DIR / "bin" / "prime-auth-check.py"

CONFIG_DIR = Path(os.environ.get("PRIME_CONFIG_DIR") or Path.home() / ".config" / "prime-gpu")
KEY_FILE = CONFIG_DIR / "key"
WATCH_FILE = CONFIG_DIR / "watch.conf"
STATE_FILE = CONFIG_DIR / "state.json"
LOGO_FILE = CONFIG_DIR / "assets" / "prime-logo-template.png"

# Fallback so users of prime-billing-statusbar don't have to duplicate their key.
FALLBACK_KEY_FILES = [Path.home() / ".config" / "prime-balance" / "key"]


def exit_with(title, *body_lines):
    print(title)
    print("---")
    for line in body_lines:
        print(line)
    print(f"Edit watch list | shell=/usr/bin/open param1={WATCH_FILE} terminal=false")
    print("Refresh now | refresh=true")
    sys.exit(0)


def get_keys():
    """Return all candidate API keys, in priority order. Tokens may be scoped
    differently (some have billing:read, some availability:read), so per-call
    code should try each in turn until one returns 200."""
    keys = []
    def add(k):
        if not k:
            return
        k = k.strip()
        if k.lower().startswith("bearer "):
            k = k[7:].strip()
        if k and not k.startswith("PASTE_") and k not in keys:
            keys.append(k)
    add(os.environ.get("PRIME_API_KEY"))
    for path in [KEY_FILE, *FALLBACK_KEY_FILES]:
        try:
            add(path.read_text())
        except (FileNotFoundError, PermissionError):
            continue
    return keys


def http_get_with_key(url, key):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None
    except Exception:
        return None, None


def http_get(url):
    """Reload keys for this request and retry once after auth failures."""
    last = (None, None)
    for _attempt in range(2):
        saw_auth_failure = False
        for k in get_keys():
            status, data = http_get_with_key(url, k)
            last = (status, data)
            if status == 200:
                return status, data
            if status in AUTH_STATUSES:
                saw_auth_failure = True
        if not saw_auth_failure:
            break
    return last


def parse_watch():
    rows = []
    try:
        text = WATCH_FILE.read_text()
    except FileNotFoundError:
        return rows
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            lo, hi = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if lo > hi:
            lo, hi = hi, lo
        rows.append({
            "gpu_type": parts[0],
            "min": lo,
            "max": hi,
            "socket": parts[3] if len(parts) >= 4 else None,
        })
    return rows


def short_name(gpu_type):
    head, _, tail = gpu_type.rpartition("_")
    return head if head and tail.endswith("GB") else gpu_type


def is_spot_offer(item):
    for field in ("cloudId", "stockStatus", "marketType", "pricingType", "priceType"):
        value = item.get(field)
        if isinstance(value, str) and "SPOT" in value.upper():
            return True
    return False


def fetch_availability(row):
    params = {"gpu_type": row["gpu_type"], "page_size": 100}
    if row["socket"]:
        params["socket"] = row["socket"]
    url = f"{GPU_ENDPOINT}?{urllib.parse.urlencode(params)}"
    status, data = http_get(url)
    if status != 200 or not isinstance(data, dict) or "items" not in data:
        detail = (data or {}).get("detail") if isinstance(data, dict) else None
        return {"row": row, "error": detail or (f"HTTP {status}" if status else "network error")}
    items = [it for it in data.get("items") or [] if not is_spot_offer(it)]
    matches = [it for it in items if row["min"] <= (it.get("gpuCount") or 0) <= row["max"]]
    matches.sort(key=lambda it: (it.get("prices") or {}).get("onDemand") or float("inf"))
    return {"row": row, "matches": matches, "total_offered": len(items)}


def icon_param():
    if not LOGO_FILE.is_file():
        return ""
    return "templateImage=" + base64.b64encode(LOGO_FILE.read_bytes()).decode()


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def _offers_fingerprint(matches):
    keys = []
    for it in matches:
        od = (it.get("prices") or {}).get("onDemand")
        keys.append((it.get("cloudId", ""), it.get("gpuCount", 0), od))
    keys.sort()
    return hashlib.sha256(json.dumps(keys).encode()).hexdigest()[:16]


def notify(title, body):
    safe = lambda s: s.replace("\\", "").replace('"', "'")
    subprocess.Popen(
        ["osascript", "-e",
         f'display notification "{safe(body)}" with title "{safe(title)}"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def price_str(item):
    prices = item.get("prices") or {}
    p = prices.get("onDemand")
    if not isinstance(p, (int, float)):
        return "n/a"
    cur = prices.get("currency") or "USD"
    sym = "$" if cur == "USD" else f"{cur} "
    return f"{sym}{p:.2f}/hr"


def main():
    keys = get_keys()
    if not keys:
        exit_with(
            "prime: no key",
            f"API key missing. Save it to {KEY_FILE} (chmod 600).",
            f"Or set PRIME_API_KEY in SwiftBar's plugin environment.",
        )

    watch = parse_watch()
    if not watch:
        exit_with(
            "prime: no watch list",
            f"Add lines to {WATCH_FILE}:",
            "  H200_141GB 4 8",
            "  H100_80GB  8 8",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, 1 + len(watch))) as pool:
        wallet_future = pool.submit(http_get, WALLET_ENDPOINT)
        gpu_futures = [pool.submit(fetch_availability, row) for row in watch]
        wallet_status, wallet_data = wallet_future.result()
        results = [f.result() for f in gpu_futures]

    title_segs = []
    bal_str = None
    if wallet_data and "balance_usd" in wallet_data:
        bal = float(wallet_data["balance_usd"])
        cur = wallet_data.get("currency", "USD")
        sym = "$" if cur == "USD" else f"{cur} "
        bal_str = f"{sym}{bal:.2f}"
        title_segs.append(bal_str)

    total_matches = 0
    prev_state = load_state()
    new_state = {}
    notifications = []
    for res in results:
        row = res["row"]
        key_id = f"{row['gpu_type']}|{row['socket'] or ''}|{row['min']}-{row['max']}"
        s = short_name(row["gpu_type"])
        if "error" in res:
            title_segs.append(f"{s} ?")
            new_state[key_id] = {"fp": None}
            continue
        n = len(res["matches"])
        fp = _offers_fingerprint(res["matches"])
        new_state[key_id] = {"fp": fp}
        total_matches += n
        if n > 0:
            title_segs.append(f"{s} {MATCH_GLYPH}{n}")
        else:
            title_segs.append(f"{s} {NONE_GLYPH}")
        prev = prev_state.get(key_id) or {}
        if n > 0 and fp != prev.get("fp"):
            cheapest = res["matches"][0]
            notifications.append(
                f"{row['gpu_type']} [{row['min']}-{row['max']}] → {n} match"
                f"{'es' if n != 1 else ''} (cheapest {price_str(cheapest)})"
            )
    save_state(new_state)
    for line in notifications:
        notify("Prime GPU available", line)

    # NOTE: SwiftBar suppresses templateImage when color= or ansi=true is also
    # set on the title. We pick the icon, and rely on the `●N` glyph (vs `·`)
    # to signal which configs have matches. Dropdown rows keep their colors.
    title_parts = ["  ".join(title_segs)]
    icon = icon_param()
    if icon:
        title_parts.append(icon)
    print(" | ".join(title_parts))

    print("---")
    if bal_str is not None:
        print(f"Balance: {bal_str}")
    elif wallet_status in (401, 403):
        detail = (wallet_data or {}).get("detail") if isinstance(wallet_data, dict) else None
        print(f"Balance: {detail or f'auth error (HTTP {wallet_status})'}")
    elif wallet_status is None:
        print("Balance: network error")
    else:
        print(f"Balance: HTTP {wallet_status}")
    print(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
    print(f"Watching {len(watch)} config(s), {total_matches} match(es)")

    for res in results:
        row = res["row"]
        rng = f"[{row['min']}-{row['max']}]"
        sock = f" {row['socket']}" if row["socket"] else ""
        header = f"{row['gpu_type']}{sock} {rng}"
        print("---")
        if "error" in res:
            print(f"{header}: {res['error']} | color={ERROR_HEX}")
            continue
        n = len(res["matches"])
        total = res["total_offered"]
        if n == 0:
            note = "no offers" if total == 0 else f"none in range ({total} outside)"
            print(f"{header}: {note} | color={NONE_HEX}")
            continue
        print(f"{header}: {n} match{'es' if n != 1 else ''} | color={MATCH_HEX}")
        for it in res["matches"][:10]:
            count = it.get("gpuCount")
            gtype = it.get("gpuType", "")
            isock = it.get("socket") or ""
            prov = it.get("provider", "")
            region = it.get("region", "")
            stock = it.get("stockStatus", "")
            text = f"  {count}× {gtype} {isock} · {price_str(it)} · {prov} · {region} · {stock}"
            payload = base64.urlsafe_b64encode(json.dumps({
                "cloudId": it.get("cloudId"),
                "gpuType": gtype,
                "socket": isock or None,
                "gpuCount": count,
                "provider": prov,
                "dataCenter": it.get("dataCenter"),
                "country": it.get("country"),
                "region": region,
                "stockStatus": stock,
                "prices": it.get("prices") or {},
            }).encode()).decode().rstrip("=")
            print(f"{text} | shell={DEPLOY_BIN} param1={payload} terminal=false")

    print("---")
    print(f"Open dashboard | href={DASHBOARD}")
    print(f"Open billing dashboard | href={DASHBOARD}/dashboard/billing")
    print(f"Check API permissions | shell={AUTH_CHECK_BIN} terminal=true")
    print(f"Edit watch list | shell=/usr/bin/open param1={WATCH_FILE} terminal=false")
    print("Refresh now | refresh=true")


if __name__ == "__main__":
    main()
