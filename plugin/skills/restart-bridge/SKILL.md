---
name: flipper-restart-bridge
description: Restart the flipper-claude-buddy host bridge daemon and reconnect to the Flipper Zero. Use when notifications/keystrokes aren't reaching the Flipper, the bridge log shows "Serial send dropped (not connected)", BLE gets stuck after a `start_notify`/`BleakDBusError: Not Connected` failure, or BLE connects and then instantly drops (`failed to discover services, device disconnected` — see the unpaired-device section below).
allowed-tools: Bash
---

# Restart Flipper Bridge

Kills the running host-bridge daemon, clears its stale socket/pid/refcount
state, then re-runs the plugin's own `SessionStart` hook to bring it back up
— this reuses the exact same venv-detection, transport (USB→BLE) fallback,
and current-session re-registration logic the hook already uses, instead of
duplicating it.

Symptom this fixes: the bridge process is alive but every send logs
`Serial send dropped (not connected)`, most commonly because BlueZ dropped
the BLE link right as the bridge tried to enable notifications
(`BleakDBusError: [org.bluez.Error.NotConnected] Not Connected` in
`/tmp/claude-flipper-bridge.log`). A clean restart re-does the BLE
scan/connect/CCCD-write sequence from scratch and usually clears it.

```bash
SOCKET="/tmp/claude-flipper-bridge.sock"
PIDFILE="/tmp/claude-flipper-bridge.pid"
REFCOUNT_FILE="/tmp/claude-flipper-bridge.refcount"
LOG="/tmp/claude-flipper-bridge.log"

# Locate the installed plugin's SessionStart hook script (works for
# marketplace installs and local dev checkouts alike).
HOOK_SCRIPT=""
for candidate in \
    "$HOME/.claude/plugins/cache/flipper-claude-buddy"/*/scripts/on-session-start.sh \
    "$HOME/.claude/plugins/marketplaces/flipper-claude-buddy"/*/scripts/on-session-start.sh \
    ./plugin/scripts/on-session-start.sh; do
    for f in $candidate; do
        [ -f "$f" ] && HOOK_SCRIPT="$f" && break 2
    done
done

if [ -z "$HOOK_SCRIPT" ]; then
    echo "Could not find on-session-start.sh — is flipper-claude-buddy installed?" >&2
    exit 1
fi

PLUGIN_ROOT="$(cd "$(dirname "$HOOK_SCRIPT")/.." && pwd)"

# Reuse the existing per-plugin data dir (holds the venv) if one exists,
# so we don't reinstall it unnecessarily.
PLUGIN_DATA=""
for d in "$HOME/.claude/plugins/data"/*flipper-claude-buddy*; do
    [ -d "$d" ] && PLUGIN_DATA="$d" && break
done
PLUGIN_DATA="${PLUGIN_DATA:-/tmp/flipper-claude-buddy}"

echo "Stopping old bridge process..."
if [ -f "$PIDFILE" ]; then
    OLD_PID="$(cat "$PIDFILE" 2>/dev/null || echo "")"
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null
        sleep 1
        kill -0 "$OLD_PID" 2>/dev/null && kill -9 "$OLD_PID" 2>/dev/null
    fi
fi
rm -f "$SOCKET" "$PIDFILE" "$REFCOUNT_FILE"

echo "Restarting via SessionStart hook ($HOOK_SCRIPT)..."
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"
export CLAUDE_PLUGIN_DATA="$PLUGIN_DATA"
export FLIPPER_PROJECT_DIR="$(pwd)"
echo '{"source":"resume"}' | "$HOOK_SCRIPT"

sleep 3
if [ -S "$SOCKET" ]; then
    echo "--- Bridge is up. Recent transport log: ---"
    tail -n 15 "$LOG" | grep -iE "connect|ble|usb|error" || tail -n 8 "$LOG"
else
    echo "Bridge did not come back up — check $LOG"
fi
```

## Notes

- This only fixes the *bridge daemon*. If the Flipper itself is powered off,
  out of BLE range, or not in Bridge mode (see on-device menu:
  long-press Right → MENU), the restart will keep failing — check
  `bluetoothctl info <mac>` for `Connected: no` to confirm it's a device
  reachability issue rather than a daemon issue.
- Safe to run even if the bridge isn't running at all (e.g. after a crash);
  it just skips the kill step and starts fresh.
- Re-registers the current terminal as the active input target, so
  keystroke forwarding keeps working for the session that triggered the
  restart.

## Unpaired device: connects then instantly disconnects (needs BLE pairing)

Symptom: `bluetoothctl connect <mac>` reports `Connected: yes` but flips back
to `Connected: no` within ~0.5s, every time, even after rebooting the
Flipper. Bridge log shows `failed to discover services, device disconnected`.
`bluetoothctl info <mac>` shows `Paired: no` / `Bonded: no`.

Root cause: the Flipper's built-in Bridge-mode BLE serial profile (used by
`transport_bt.c`, distinct from the custom NUS profile in `nus_profile.c`
which explicitly disables bonding) requires **passkey-entry pairing**. On
Linux this shows up in the kernel log as:

```
kernel: Bluetooth: hci0: unexpected SMP command 0x0b from <mac>
```

(SMP opcode `0x0b` = Security Request.) Without an existing bond, the host's
BlueZ stack can't complete the SMP handshake in time and drops the link
right after `ServicesResolved` — this is a security handshake failure, not
an advertising, discovery, or bridge-daemon problem, so restarting the
bridge daemon alone will loop forever without fixing it.

Fix — pair once with an agent that can prompt for a passkey (this step is
interactive and needs a human reading the 6-digit code off the Flipper's
screen; it cannot be scripted headlessly):

```bash
bluetoothctl
agent KeyboardOnly
default-agent
scan on
pair <mac>
# Flipper screen shows a 6-digit passkey — type it at the
# "Enter passkey (number in 0-999999):" prompt
trust <mac>
quit
```

Verify with `bluetoothctl info <mac>` — expect `Paired: yes`, `Bonded: yes`.
Once bonded, `trust` keeps BlueZ auto-reconnecting on future sessions, and
a normal bridge restart (see above) will connect cleanly and stay connected.
