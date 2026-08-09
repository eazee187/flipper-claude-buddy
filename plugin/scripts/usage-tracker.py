#!/usr/bin/env python3
"""Stop hook: accumulates session token usage from the transcript and pushes
a cumulative total (+ a rough cost estimate) to the Flipper's Usage screen.

Reads only the transcript lines appended since the last run (tracked via a
byte offset in a per-session state file), so cost stays O(new lines) per
Stop event instead of re-scanning the whole (growing) transcript.
"""

import json
import os
import socket
import sys

SOCKET_PATH = "/tmp/claude-flipper-bridge.sock"

# Rough per-1M-token USD rates (input, output). Cache-write is priced at
# 1.25x the input rate, cache-read at 0.1x — mirrors Anthropic's published
# cache pricing multipliers. NOTE: this table is a point-in-time estimate
# and will go stale as pricing changes; unrecognized models fall back to
# Sonnet rates.
RATE_TABLE = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.8, 4.0),
}
DEFAULT_RATE = RATE_TABLE["sonnet"]

# Context-window-remaining %, computed the same way as the separately
# installed "ecc" plugin's transcript-context.js: based on the *latest*
# turn's prompt size (input + cache_read + cache_creation, NOT output —
# that's generation size, not context size), not a cumulative total.
STANDARD_CONTEXT_WINDOW_TOKENS = 200_000
LARGE_CONTEXT_WINDOW_TOKENS = 1_000_000


def rates_for_model(model: str) -> tuple[float, float]:
    model = (model or "").lower()
    for key, rate in RATE_TABLE.items():
        if key in model:
            return rate
    return DEFAULT_RATE


def resolve_context_window(tokens: int, model: str) -> int:
    try:
        env_value = int(os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW", ""))
        if env_value > 0:
            return env_value
    except ValueError:
        pass
    if "[1m]" in (model or "").lower():
        return LARGE_CONTEXT_WINDOW_TOKENS
    if tokens > STANDARD_CONTEXT_WINDOW_TOKENS:
        return LARGE_CONTEXT_WINDOW_TOKENS
    return STANDARD_CONTEXT_WINDOW_TOKENS


def context_remaining_pct(last_usage: dict | None) -> int | None:
    if not last_usage:
        return None
    tokens = last_usage["context_tokens"]
    window = resolve_context_window(tokens, last_usage["model"])
    return max(0, min(100, round((1 - tokens / window) * 100)))


def load_state(state_path: str) -> dict:
    try:
        with open(state_path) as f:
            return json.load(f)
    except Exception:
        return {"offset": 0, "totals": {}}


def save_state(state_path: str, state: dict) -> None:
    try:
        with open(state_path, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def accumulate(transcript_path: str, state: dict) -> tuple[dict, dict | None]:
    totals = state.get("totals", {})
    offset = state.get("offset", 0)
    last_usage = None

    try:
        size = os.path.getsize(transcript_path)
    except OSError:
        return state, None
    if offset > size:
        # Transcript was rewritten/truncated — start over.
        offset = 0
        totals = {}

    with open(transcript_path, "r") as f:
        f.seek(offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue
            message = entry.get("message") or {}
            usage = message.get("usage")
            if not usage:
                continue
            model = message.get("model", "unknown")
            t = totals.setdefault(
                model, {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
            )
            input_t = usage.get("input_tokens", 0) or 0
            output_t = usage.get("output_tokens", 0) or 0
            cache_write_t = usage.get("cache_creation_input_tokens", 0) or 0
            cache_read_t = usage.get("cache_read_input_tokens", 0) or 0
            t["input"] += input_t
            t["output"] += output_t
            t["cache_write"] += cache_write_t
            t["cache_read"] += cache_read_t
            # Overwritten on every matching line, so this ends up holding
            # the latest turn's snapshot once the loop finishes.
            last_usage = {"model": model, "context_tokens": input_t + cache_write_t + cache_read_t}
        offset = f.tell()

    return {"offset": offset, "totals": totals}, last_usage


def grand_totals(state: dict) -> tuple[int, int, int, int, int]:
    input_tokens = output_tokens = cache_write = cache_read = 0
    cost_usd = 0.0
    for model, t in state.get("totals", {}).items():
        input_tokens += t["input"]
        output_tokens += t["output"]
        cache_write += t["cache_write"]
        cache_read += t["cache_read"]
        rate_in, rate_out = rates_for_model(model)
        cost_usd += (
            t["input"] * rate_in
            + t["output"] * rate_out
            + t["cache_write"] * rate_in * 1.25
            + t["cache_read"] * rate_in * 0.1
        ) / 1_000_000
    return input_tokens, output_tokens, cache_write, cache_read, round(cost_usd * 100)


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

    transcript_path = payload.get("transcript_path")
    session_id = payload.get("session_id")
    if not transcript_path or not session_id:
        return

    state_path = f"/tmp/claude-flipper-usage-{session_id}.json"
    state = load_state(state_path)
    state, last_usage = accumulate(transcript_path, state)
    save_state(state_path, state)

    input_tokens, output_tokens, cache_write, cache_read, cost_cents = grand_totals(state)
    ctx_pct = context_remaining_pct(last_usage)
    try:
        send_to_flipper(input_tokens, output_tokens, cache_write, cache_read, cost_cents, ctx_pct)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
