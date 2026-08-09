#!/usr/bin/env python3
"""Stop hook: forwards this session's token usage / cost / context-remaining %
to the Flipper's Usage screen and header, sourced from the separately
installed "ecc" plugin's own already-computed data.

No calculation happens here — if ecc isn't installed (or hasn't produced
data for this session yet), this hook sends nothing and the Flipper simply
shows no data, same as before its first "usage" message ever arrives.

Data sources (both written by ecc, not by this project):
  ~/.claude/metrics/costs.jsonl        cumulative cost/token totals, one row
                                        per Stop event, appended by ecc's own
                                        cost-tracker.js. We take the last row
                                        matching this session_id.
  /tmp/ecc-metrics-<session_id>.json   context_remaining_pct specifically —
                                        only populated once ecc's statusLine
                                        command has run at least once.
"""

import json
import os
import socket
import sys
import tempfile

SOCKET_PATH = "/tmp/claude-flipper-bridge.sock"
COSTS_PATH = os.path.expanduser("~/.claude/metrics/costs.jsonl")


def read_latest_costs_row(session_id: str) -> dict | None:
    try:
        with open(COSTS_PATH) as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("session_id") == session_id:
            return row
    return None


def read_context_pct(session_id: str) -> int | None:
    # ecc writes this via Node's os.tmpdir(), which (like Python's
    # tempfile.gettempdir()) honors $TMPDIR when set — not always plain
    # /tmp (e.g. systemd-managed per-user tmp dirs like /tmp/user/1000).
    bridge_path = os.path.join(tempfile.gettempdir(), f"ecc-metrics-{session_id}.json")
    try:
        with open(bridge_path) as f:
            bridge = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    pct = bridge.get("context_remaining_pct")
    return int(pct) if isinstance(pct, (int, float)) else None


def send_to_flipper(
    input_tokens: int, output_tokens: int, cache_write: int, cache_read: int,
    cost_cents: int, context_pct: int | None,
) -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCKET_PATH)
    payload = {
        "action": "usage",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_write_tokens": cache_write,
        "cache_read_tokens": cache_read,
        "cost_cents": cost_cents,
    }
    if context_pct is not None:
        payload["context_pct"] = context_pct
    msg = json.dumps(payload)
    s.sendall(msg.encode())
    s.shutdown(socket.SHUT_WR)
    s.recv(4096)
    s.close()


def main():
    if not os.path.exists(SOCKET_PATH):
        return

    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return

    session_id = payload.get("session_id")
    if not session_id:
        return

    row = read_latest_costs_row(session_id)
    if row is None:
        # ecc not installed, or no Stop event recorded for this session yet.
        return

    cost_cents = round(row.get("estimated_cost_usd", 0.0) * 100)
    ctx_pct = read_context_pct(session_id)
    try:
        send_to_flipper(
            row.get("input_tokens", 0),
            row.get("output_tokens", 0),
            row.get("cache_write_tokens", 0),
            row.get("cache_read_tokens", 0),
            cost_cents,
            ctx_pct,
        )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
