#!/usr/bin/env python3
"""
Dev / headless Grid Service Bot client.

Polls /api/bot/queue and prints messages (or POST ack). Use for testing without
an in-world avatar. Production delivery uses packaging/inworld/GridServiceBot.lsl.

Usage:
  export GRID_BOT_API_TOKEN=your-token
  python scripts/grid_bot_client.py --url https://portal.example.com --once
  python scripts/grid_bot_client.py --url https://portal.example.com --loop --interval 30
"""

import argparse
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)


def poll_queue(base_url, token, text_format=True):
    fmt = "text" if text_format else "json"
    url = f"{base_url.rstrip('/')}/api/bot/queue?format={fmt}&token={urllib.parse.quote(token)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("X-Grid-Bot-Token", token)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def ack_message(base_url, token, message_id, success=True, error=None):
    params = {"token": token, "format": "text", "success": "1" if success else "0"}
    if error:
        params["error"] = error[:200]
    url = f"{base_url.rstrip('/')}/api/bot/ack/{message_id}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("X-Grid-Bot-Token", token)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def deliver_line(line):
    """Simulate in-world delivery — override for real IM/region chat integration."""
    parts = line.split("|")
    if len(parts) < 5:
        print(f"  [skip malformed] {line[:80]}")
        return False
    msg_id = parts[0]
    msg_type = parts[1]
    if len(parts) >= 8:
        target_uuid, region_name, group_uuid, delivery, subject, body = (
            parts[2],
            parts[3],
            parts[4],
            parts[5],
            parts[6],
            parts[7],
        )
        if delivery in ("group_chat", "group_notice"):
            print(
                f"  [GROUP {delivery} -> {group_uuid}] ({msg_type}) {subject}: {body}"
            )
        elif target_uuid:
            print(f"  [IM -> {target_uuid}] ({msg_type}) {body}")
        elif region_name:
            print(f"  [REGION {region_name}] ({msg_type}) {body}")
        else:
            print(f"  [BROADCAST] ({msg_type}) {body}")
    else:
        msg_id, msg_type, target_uuid, region_name, body = parts[:5]
        if target_uuid:
            print(f"  [IM -> {target_uuid}] ({msg_type}) {body}")
        elif region_name:
            print(f"  [REGION {region_name}] ({msg_type}) {body}")
        else:
            print(f"  [BROADCAST] ({msg_type}) {body}")
    return True


def run_once(base_url, token, do_ack=True):
    try:
        raw = poll_queue(base_url, token, text_format=True)
    except urllib.error.HTTPError as e:
        print(f"Poll failed: HTTP {e.code}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Poll failed: {e.reason}", file=sys.stderr)
        return 1

    if not raw.strip():
        print("No pending messages.")
        return 0

    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        ok = deliver_line(line)
        if do_ack:
            msg_id = line.split("|", 1)[0]
            try:
                ack_message(base_url, token, int(msg_id), success=ok)
            except Exception as exc:
                print(f"  Ack failed for {msg_id}: {exc}", file=sys.stderr)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Grid Service Bot poll client")
    parser.add_argument(
        "--url", default=os.environ.get("PORTAL_URL", "https://portal.example.com")
    )
    parser.add_argument("--token", default=os.environ.get("GRID_BOT_API_TOKEN", ""))
    parser.add_argument("--once", action="store_true", help="Poll once and exit")
    parser.add_argument("--loop", action="store_true", help="Poll continuously")
    parser.add_argument(
        "--interval", type=int, default=30, help="Seconds between polls (loop mode)"
    )
    parser.add_argument(
        "--no-ack", action="store_true", help="Do not send delivery acks"
    )
    args = parser.parse_args()

    if not args.token:
        print("Set GRID_BOT_API_TOKEN or pass --token", file=sys.stderr)
        return 1

    if args.loop:
        print(f"Polling {args.url} every {args.interval}s (Ctrl+C to stop)")
        while True:
            run_once(args.url, args.token, do_ack=not args.no_ack)
            time.sleep(args.interval)
    else:
        return run_once(args.url, args.token, do_ack=not args.no_ack)


if __name__ == "__main__":
    raise SystemExit(main())
