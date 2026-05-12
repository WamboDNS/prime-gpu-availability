#!/usr/bin/env python3
"""Deploy a Prime Intellect pod from a base64url-encoded offer payload.

Usage: prime-deploy.py <b64url_offer_json>

The argument is JSON describing one /availability/gpus item, with the keys
the create-pod endpoint needs: cloudId, gpuType, socket, gpuCount, provider,
dataCenter, country, region, stockStatus, prices.

Workflow:
  1. Decode the offer.
  2. Show an osascript confirm dialog summarising the offer + price.
  3. Ask for a pod name (default: timestamped).
  4. POST to /api/v1/pods/.
  5. Notify locally + via ntfy on success or failure.

Set PRIME_DRY_RUN=1 to skip the POST (the dialog still runs).
"""

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

API_BASE = "https://api.primeintellect.ai/api/v1"
PODS_ENDPOINT = f"{API_BASE}/pods/"
PODS_DASHBOARD = "https://app.primeintellect.ai/dashboard/pods"

CONFIG_DIR = Path(os.environ.get("PRIME_CONFIG_DIR") or Path.home() / ".config" / "prime-gpu")
KEY_FILE = CONFIG_DIR / "key"
NTFY_FILE = CONFIG_DIR / "ntfy.url"
FALLBACK_KEY_FILES = [Path.home() / ".config" / "prime-balance" / "key"]


def get_keys():
    keys = []
    def add(k):
        if k and k.strip() and not k.strip().startswith("PASTE_") and k.strip() not in keys:
            keys.append(k.strip())
    add(os.environ.get("PRIME_API_KEY"))
    for path in [KEY_FILE, *FALLBACK_KEY_FILES]:
        try:
            add(path.read_text())
        except (FileNotFoundError, PermissionError):
            continue
    return keys


def _osa_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def osa_confirm(text, title="Prime Intellect Deploy"):
    """Show a confirm dialog. Returns the clicked button name or None on Cancel."""
    script = (
        f'tell application "System Events"\n'
        f'  activate\n'
        f'  display dialog "{_osa_escape(text)}" with title "{_osa_escape(title)}" '
        f'buttons {{"Cancel", "Deploy"}} default button "Deploy" with icon caution\n'
        f'end tell'
    )
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=180)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    for part in r.stdout.split(", "):
        if part.startswith("button returned:"):
            return part[len("button returned:"):].strip()
    return None


def osa_text(prompt, default="", title="Prime Intellect Deploy"):
    script = (
        f'tell application "System Events"\n'
        f'  activate\n'
        f'  display dialog "{_osa_escape(prompt)}" with title "{_osa_escape(title)}" '
        f'default answer "{_osa_escape(default)}" '
        f'buttons {{"Cancel", "OK"}} default button "OK"\n'
        f'end tell'
    )
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=180)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    for part in r.stdout.split(", "):
        if part.startswith("text returned:"):
            return part[len("text returned:"):].strip()
    return None


def notify_local(title, body):
    script = (
        f'display notification "{_osa_escape(body)}" with title "{_osa_escape(title)}"'
    )
    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def push_ntfy(title, body, click_url=None):
    try:
        for raw in NTFY_FILE.read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if line.startswith("http"):
                url = line
                break
        else:
            return
    except (FileNotFoundError, PermissionError):
        return
    headers = {"Title": title, "Priority": "high", "Tags": "rocket"}
    if click_url:
        headers["Click"] = click_url
    req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST", headers=headers)
    try:
        urllib.request.urlopen(req, timeout=4).read()
    except Exception:
        pass


def alert(title, body, click_url=None):
    notify_local(title, body)
    push_ntfy(title, body, click_url)


def http_post(url, key, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None
    except Exception as e:
        return None, {"error": str(e)}


def decode_offer(s):
    s = s.strip()
    s += "=" * (-len(s) % 4)
    return json.loads(base64.urlsafe_b64decode(s))


def fmt_price(prices):
    p = (prices or {}).get("onDemand")
    if not isinstance(p, (int, float)):
        return "?"
    cur = (prices or {}).get("currency") or "USD"
    sym = "$" if cur == "USD" else f"{cur} "
    return f"{sym}{p:.2f}/hr"


def main():
    if len(sys.argv) < 2:
        alert("Deploy", "Missing offer payload.")
        sys.exit(2)
    try:
        offer = decode_offer(sys.argv[1])
    except Exception as e:
        alert("Deploy: decode failed", str(e))
        sys.exit(2)

    keys = get_keys()
    if not keys:
        alert("Deploy: no API key", f"Set {KEY_FILE} first.")
        sys.exit(2)

    summary_lines = [
        f"{offer['gpuCount']}× {offer['gpuType']}"
        + (f"  {offer['socket']}" if offer.get('socket') else ""),
        "",
        f"Provider: {offer.get('provider', '?')}",
        f"Region:   {offer.get('region', '?')}",
        f"Center:   {offer.get('dataCenter', '?')}",
        f"Price:    {fmt_price(offer.get('prices'))}",
        f"Stock:    {offer.get('stockStatus', '?')}",
        "",
        "This will create a pod and start billing immediately.",
    ]

    if osa_confirm("\n".join(summary_lines)) != "Deploy":
        sys.exit(0)

    default_name = f"prime-gpu-{datetime.now():%Y%m%d-%H%M%S}"
    name = osa_text("Pod name:", default=default_name)
    if not name:
        sys.exit(0)

    pod_body = {
        "name": name,
        "cloudId": offer["cloudId"],
        "gpuType": offer["gpuType"],
        "gpuCount": offer["gpuCount"],
    }
    if offer.get("socket"):
        pod_body["socket"] = offer["socket"]
    if offer.get("dataCenter"):
        pod_body["dataCenterId"] = offer["dataCenter"]
    if offer.get("country"):
        pod_body["country"] = offer["country"]
    price = (offer.get("prices") or {}).get("onDemand")
    if isinstance(price, (int, float)):
        pod_body["maxPrice"] = price

    request_body = {
        "pod": pod_body,
        "provider": {"type": offer.get("provider")},
    }

    if os.environ.get("PRIME_DRY_RUN") == "1":
        alert("Deploy (dry-run)", f"Would POST: {json.dumps(request_body)[:120]}…")
        print(json.dumps(request_body, indent=2))
        sys.exit(0)

    last_status, last_data = None, None
    for k in keys:
        status, data = http_post(PODS_ENDPOINT, k, request_body)
        last_status, last_data = status, data
        if 200 <= (status or 0) < 300:
            pod_id = (data or {}).get("id") or ((data or {}).get("pod") or {}).get("id") or "?"
            alert(
                "Pod provisioning",
                f"{name} — {offer['gpuCount']}× {offer['gpuType']} @ {fmt_price(offer.get('prices'))} (id {pod_id})",
                click_url=PODS_DASHBOARD,
            )
            print(json.dumps(data, indent=2))
            sys.exit(0)

    detail = "?"
    if isinstance(last_data, dict):
        detail = last_data.get("detail") or json.dumps(last_data)[:300]
    elif last_status is not None:
        detail = f"HTTP {last_status}"
    alert("Deploy failed", str(detail)[:200], click_url=PODS_DASHBOARD)
    print(f"HTTP {last_status}\n{json.dumps(last_data, indent=2) if last_data else ''}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
