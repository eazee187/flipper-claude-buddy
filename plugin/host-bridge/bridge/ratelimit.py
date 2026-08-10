"""Parses `claude /usage` CLI output for the 5h-window and weekly rate-limit
percentages. Ported from the (independently fixed and field-tested) parser in
the flipper-ai-dashboard project's ClaudeCollector, since the CLI's output
format uses "NN% used" today, not the older "NN% left" phrasing.
"""

import re

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
PERCENT_USAGE_RE = re.compile(r"([0-9]{1,3})%\s+(used|left)", re.IGNORECASE)


def _extract_used_pct(text: str, tokens: tuple[str, ...]) -> int | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        lower = line.lower()
        if not any(token in lower for token in tokens):
            continue

        match = PERCENT_USAGE_RE.search(line)
        if match:
            value = int(match.group(1))
            return value if match.group(2).lower() == "used" else 100 - value

        # Older layouts spread percent across the next few lines instead of
        # the token line itself.
        for candidate in lines[index + 1 : index + 6]:
            candidate_match = PERCENT_USAGE_RE.search(candidate)
            if candidate_match:
                value = int(candidate_match.group(1))
                return value if candidate_match.group(2).lower() == "used" else 100 - value
    return None


def parse_claude_usage(text: str) -> tuple[int | None, int | None]:
    """Returns (session_used_pct, week_used_pct), each 0-100 or None if not found."""
    clean = ANSI_RE.sub("", text)
    session_pct = _extract_used_pct(clean, ("5h", "session"))
    week_pct = _extract_used_pct(clean, ("weekly", "week"))
    return session_pct, week_pct
