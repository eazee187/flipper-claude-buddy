# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

### Flipper App (C)
```bash
# Build (requires ufbt: pip3 install ufbt)
cd flipper-app && ufbt build

# Build and flash to connected Flipper
cd flipper-app && ufbt launch

# Or use the script
./scripts/build-flipper.sh           # build only
./scripts/build-flipper.sh --flash   # build + flash
```

### Host Bridge (Python) — only used in Bridge mode (see Architecture)
```bash
# Install (editable)
cd plugin/host-bridge && pip3 install -e .

# Run bridge daemon
python3 -m bridge

# Run with explicit transport
python3 -m bridge --transport ble   # BLE only
python3 -m bridge --transport usb   # USB only

# Key environment overrides
FLIPPER_BT_NAME="Flipper"          # BLE device name prefix
FLIPPER_TRANSPORT=ble              # force BLE
FLIPPER_LOG_LEVEL=debug            # verbose logs
```

### Testing IPC
```bash
echo '{"action":"notify","sound":"success","vibro":true,"text":"Test","subtext":""}' \
  | nc -U /tmp/claude-flipper-bridge.sock
```

### Debug scripts (`scripts/`)
- `scan-nus.py` — BLE scanner that shows every advertiser and whether it would match a Claude Desktop-style picker (name prefix "Claude" + NUS service UUID). Use to debug Desktop-mode pairing.
- `refresh-name.py` — connects and reads the GATT Device Name characteristic (0x2A00) to force macOS to refresh its cached peripheral name after an on-device rename.
- `flipper-log.py` — tails the Flipper's serial debug log.

## Architecture

The Flipper app has **two independent modes**, switchable at runtime from the on-device menu (long-press **Right → MENU**, top row) and persisted in `app_settings` (`BleMode`: `Bridge` = 0, `Desktop` = 1). Only one is active at a time; switching rebuilds the BLE transport live.

### Mode 1 — Bridge (Claude Code), default
```
Flipper Zero (C app)
  ↕ USB CDC serial  OR  BLE serial (custom Flipper-UUID profile)
Host Bridge (Python daemon)
  ↕ Unix socket  /tmp/claude-flipper-bridge.sock
Claude Code hook scripts (plugin/)
```
Talks to Claude Code in a terminal via the Python host-bridge daemon. Full keystroke forwarding (Enter, Esc, arrows, Ctrl+C, voice dictation, slash-command menu). USB is preferred when a cable is plugged in; falls back to BLE automatically (`transport_usb.c` / `transport_bt.c` on the Flipper side, `transport_usb.py` / `transport_bt.py` on the bridge side).

1. **`flipper-app/`** — Flipper Zero FAP (C). Handles button input and audio/haptic feedback.
2. **`plugin/host-bridge/`** — Python asyncio daemon. Bridges serial ↔ Unix socket. Manages BLE/USB connection with auto-reconnect. Serves a Unix socket that hook scripts connect to.
3. **`plugin/`** — Claude Code plugin (self-contained, shareable). Hook scripts that translate Claude Code lifecycle events into socket messages.

### Mode 2 — Desktop (Claude Desktop / Cowork BLE)
```
Flipper Zero (C app)
  ↕ BLE, standard Nordic UART Service (nus_profile.c)
Claude Desktop app (Developer Mode → Hardware Buddy)
```
Talks **directly** to the Claude Desktop app over BLE using Anthropic's [Hardware Buddy](https://github.com/anthropics/claude-desktop-buddy) protocol — no host bridge, no plugin, no Unix socket. The Flipper advertises a standard NUS service so Claude Desktop's own BLE picker can find and pair with it. Shows live session status (running/waiting counts, token counters), a scrollable transcript, and lets the user Allow/Deny permission prompts on-device. Keystroke-forwarding buttons are inactive in this mode since Claude Desktop doesn't take keystrokes over this protocol.

Relevant files: `nus_profile.c` (the BLE GATT profile itself), `transport_nus.c` (`Transport` adapter over that profile), `nus_protocol.c` (JSON wire format — heartbeats, turn events, cmds, permission decisions, acks), `nus_state.c` (state machine driving LED/audio/pose from heartbeat deltas), `nus_stats.c` (persisted approve/deny counters), `nus_transcript.c` (ring buffer for the on-device transcript view), `nus_charpack.c` (receiver for a folder-push sub-protocol: `char_begin` → `[file → chunk* → file_end]*` → `char_end`).

Both modes share `protocol.c`/`ProtocolMessage` as the internal message shape consumed by `claude_buddy.c`'s GUI-thread dispatcher — `translate_nus_to_protocol()` in `claude_buddy.c` converts parsed `NusMessage`s into `ProtocolMessage`s so `process_message()` stays protocol-agnostic. `Transport` (`transport.h`) is the common vtable-style interface implemented by `transport_usb.c`, `transport_bt.c`, and `transport_nus.c`.

## Threading Model — Critical

### Flipper App
- **BLE/serial RX callback** runs on a worker thread. It must NOT call any UI functions or `transport_send`.
- The callback queues parsed `ProtocolMessage` into a `FuriMessageQueue` and signals the GUI thread via `view_dispatcher_send_custom_event`.
- **GUI thread** (the Furi event loop) drains the queue and calls `transport_send` safely.
- Calling `ble_profile_serial_tx` (or `nus_profile_tx`) from inside the BLE event callback deadlocks on Momentum firmware — always defer TX to the GUI thread.
- `transport_bt_set_connect_callback` fires on the BT stack thread for Bridge-mode link state changes — it must only dispatch a custom event (`CustomEventBtLinkDown`), never touch UI directly.
- `nus_state_tick` (Desktop-mode's 1 Hz timer, for sleep-timeout detection) is likewise dispatched to the GUI thread via a custom event (`CustomEventNusTick`) rather than run inline in the timer callback.
- `app_settings.c` (persisted `BleMode`, owner name, device name) is accessed from the GUI thread only.

### Host Bridge
- Single asyncio event loop. All transport I/O, IPC, and ping tasks are async coroutines.
- `serial_conn.py` runs a reconnect loop that re-establishes the transport on disconnect.
- `transport_bt.py`: `readline()` must handle disconnect without blocking — checks `_closed` flag before and after `_rx_event.clear()`.
- Only relevant to **Bridge mode** — Desktop mode never touches the host bridge.

## Protocol

### Bridge protocol (Mode 1)
JSON lines (`\n`-terminated) over serial (USB or BLE):
```json
{"v": 1, "t": "<type>", "d": {...}}
```

**Host → Flipper:** `ping`, `notify`, `state`, `status`, `menu`, `perm`
**Flipper → Host:** `hello`, `pong`, `cmd`, `yes`, `enter`, `esc`, `down`, `backspace`, `voice`, `space_down`, `space_up`, `interrupt`, `pgup`, `pgdown`, `ctrl_o`, `ctrl_e`, `shift_tab`, `perm_resp`

The Flipper sends `hello` on the first received `ping` (from the GUI thread), not at BLE connect time. This is because the host's CCCD write (enabling notifications) hasn't happened yet when the connection status callback fires.

### Anthropic Hardware Buddy protocol (Mode 2)
JSON lines over the standard NUS service. Spec: https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md

**Desktop → device:** heartbeat snapshot (on every change + 10s keepalive; may embed a permission prompt), `{"evt":"turn",...}` (one-shot per assistant turn, drives the transcript), `{"time":[epoch,tz]}` (sets the Flipper's RTC on connect), `{"cmd":"status"|"owner"|"name"|"unpair"}`, folder-push cmds (`char_begin`/`file`/`chunk`/`file_end`/`char_end`).
**Device → desktop:** `{"cmd":"permission","id":"<id>","decision":"once"|"deny"}`, `{"ack":"<cmd>","ok":true,"n":0,"data":{...}?}`.

Unlike the Bridge protocol, every desktop-originated cmd requires an ack (built in `nus_build_ack`/`nus_build_status_ack`), and permission decisions only have `once`/`deny` (no "always") — the on-device permission view hides the Always toggle in Desktop mode.

## BLE Transport Details

### Bridge mode — custom Flipper-UUID serial profile (`transport_bt.c` / `transport_bt.py`)
- Adv UUID (scan filter): `00003082-0000-1000-8000-00805f9b34fb`
- Flipper→host (notify): `19ed82ae-ed21-4c9d-4145-228e61fe0000`
- Host→Flipper (write): `19ed82ae-ed21-4c9d-4145-228e62fe0000`
- Host writes with `response=False` (write-without-response), chunk size capped to `negotiated_mtu - 3`
- `BT_WRITE_CHUNK = 128` in `config.py` (runtime cap applies)

### Desktop mode — standard Nordic UART Service (`nus_profile.c`)
- Service: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- RX (desktop → device, write w/o response): `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
- TX (device → desktop, notify): `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
- Advertised name defaults to "Claude Flipper" (Claude Desktop's picker filters by `Claude*`); renamed via `cmd:name`, which triggers a live BLE profile restart to pick up the new GAP name.
- Max single write: `NUS_PROFILE_RX_MAX_LEN` (240 bytes), also capped below ATT MTU-3.

## Key Files

| File | Purpose |
|------|---------|
| `flipper-app/claude_buddy.c` | App entry point, GUI event loop, mode switching, message dispatch |
| `flipper-app/transport.h` | Abstract `Transport` interface shared by USB/BT/NUS |
| `flipper-app/transport_bt.c` | Bridge-mode BLE transport (custom UUID) — RX callback, connection state |
| `flipper-app/transport_nus.c` | Desktop-mode BLE transport adapter over `nus_profile.c` |
| `flipper-app/nus_profile.c` | Standard Nordic UART Service BLE GATT profile |
| `flipper-app/nus_protocol.c` | Anthropic Hardware Buddy JSON wire format (parse + build) |
| `flipper-app/nus_state.c` | Desktop-mode state machine (LED/audio/pose from heartbeat deltas) |
| `flipper-app/nus_stats.c` | Persisted approve/deny counters for Desktop mode |
| `flipper-app/nus_transcript.c` | Ring buffer backing the on-device transcript view |
| `flipper-app/nus_charpack.c` | Folder-push receiver (character pack files sent from Desktop) |
| `flipper-app/app_settings.c` | Persisted per-app settings: `BleMode`, owner name, device name |
| `flipper-app/protocol.c` | JSON parse/build for Bridge-protocol message types |
| `flipper-app/ui.c` | Display rendering, button input handlers |
| `plugin/host-bridge/bridge/daemon.py` | Main event loop, message routing, slash-command discovery |
| `plugin/host-bridge/bridge/transport_auto.py` | Tries USB first, falls back to BLE |
| `plugin/host-bridge/bridge/transport_bt.py` | Bridge-mode BLE transport (bleak), readline, write |
| `plugin/host-bridge/bridge/serial_conn.py` | Reconnect loop, disconnect detection |
| `plugin/host-bridge/bridge/config.py` | All tunables (timeouts, UUIDs, chunk sizes) |
| `plugin/scripts/` | Hook scripts for each Claude Code lifecycle event |
| `scripts/scan-nus.py` | Debug: shows what a Desktop-mode BLE picker would see |

## Runtime Files (macOS)
- Socket: `/tmp/claude-flipper-bridge.sock`
- PID: `/tmp/claude-flipper-bridge.pid`
- Log: `/tmp/claude-flipper-bridge.log`
- Session refcount: `/tmp/claude-flipper-bridge.refcount`
- Turn stats: `/tmp/claude-flipper-turn-stats.json` — tool usage counts written by `on-post-tool-use.py`, read by `on-stop.sh`
- Skip-stop flag: `/tmp/claude-flipper-skip-stop.flag` — set by hook Bash commands that write directly to the socket, prevents `on-stop.sh` from double-notifying
- BT name cache: `$PLUGIN_DATA/bt_name` — auto-detected Bluetooth device name saved after first `hello`; used across sessions to skip re-scanning
- Flipper-side: `/ext/apps_data/claude_buddy/settings.bin` — persisted `BleMode` + owner/device name (1 byte header + strings)

All of the above (except the Flipper-side settings file) apply only to **Bridge mode**; Desktop mode has no host-side process.

To inspect bridge activity: `tail -f /tmp/claude-flipper-bridge.log`

## Platform Notes

| Feature | macOS | Linux |
|---------|-------|-------|
| USB transport | `/dev/cu.usbmodem*` | `/dev/ttyACM*` (auto-detected) |
| BLE transport | ✓ | ✓ (via BlueZ — `apt install bluetooth bluez`, add user to `bluetooth` group) |
| Keystroke forwarding | AppleScript (`osascript`) | `xdotool` (X11) or `ydotool` (Wayland) — auto-detected, see below |
| Dictation | macOS native (`FLIPPER_DICTATION_BACKEND=macos`) | disabled by default; use `FLIPPER_DICTATION_BACKEND=custom` |

On Linux X11, `WINDOWID` (set by VTE-based terminals like gnome-terminal and kitty) is used by `xdotool` to focus the correct window. If `WINDOWID` is not set, keystrokes go to the active window.

On Linux Wayland, keystroke forwarding uses `ydotool` (uinput-based) instead — `plugin/host-bridge/bridge/input.py::create_backend()` picks it automatically when `WAYLAND_DISPLAY` is set or `XDG_SESSION_TYPE=wayland`, falling back to `xdotool` (XWayland only) if `ydotool` isn't installed. `ydotool` requires the `ydotoold` service running and the user in the `input` group (`/dev/uinput` access), and has no window-targeting concept — keystrokes always go to whatever the compositor has focused. Override auto-detection with `FLIPPER_INPUT_BACKEND=xdotool|ydotool|none` (`config.INPUT_BACKEND`). `ydotool` also sends raw US-QWERTY keycodes regardless of the compositor's actual layout, so some characters land wrong on non-US systems (e.g. `/` arrives as `-` on German QWERTZ). The bridge auto-remaps the common German-layout differences (`input.py`'s `_DE_YDOTOOL_CHAR_REMAP`); other layouts aren't covered. Override detection with `FLIPPER_KEYBOARD_LAYOUT=de|us` (`config.KEYBOARD_LAYOUT`).

Keystroke forwarding and dictation only apply to Bridge mode. The bridge daemon, IPC socket, and all hook scripts are otherwise platform-agnostic; Desktop mode is BLE-only and has no host-side platform dependency.

## Command Menu System (Bridge mode only)

The Flipper's button menu (`daemon.py: _load_commands`) is the union of:
1. Built-in Claude Code slash commands (hardcoded list, `Daemon.BUILTIN_COMMANDS`).
2. `commands/*.md` in both `~/.claude/` and `$PROJECT_DIR/.claude/` — filename becomes `/<name>`.
3. `skills/<name>/SKILL.md` in both roots — the `name:` frontmatter field becomes the command.
4. Every plugin enabled in either root's `settings.json` (`enabledPlugins`), resolved under `~/.claude/plugins/marketplaces/` (or `cache/` for externally-sourced plugins) — its `commands/*.md` become `/<plugin>:<name>` and its `skills/*/SKILL.md` contribute their own frontmatter name.
5. Legacy override files: `~/.claude/flipper-commands.txt` and `$PROJECT_DIR/.claude/flipper-commands.txt` (project overrides user).

Menu items are pipe-delimited and sent to the Flipper as a `menu` message; entries are truncated to 26 chars for on-device display, and the Flipper stores the truncated→full mapping in `_cmd_map`, expanding it back to the full command string when a selection is sent to the host.

## Releasing a New Version

1. **Commit any uncommitted changes first** — the version bump should be its own clean commit.
2. **`flipper-app/CHANGELOG.md`** — add a new `## vX.Y` section at the top, summarizing commits since the previous version.
3. **`flipper-app/application.fam`** — update `fap_version`
4. **`flipper-app/ui.c`** — update version string on the About page
5. **`plugin/.claude-plugin/plugin.json`** — update `version`
6. **`plugin/host-bridge/pyproject.toml`** — update `version`
7. Commit, push, then tag:
   ```bash
   git tag X.Y
   git push origin X.Y
   ```
   The CI workflow (`.github/workflows/build-fap.yml`) builds the FAP with `ufbt` on every push to `flipper-app/**` or tag push, and on a tag push additionally creates the GitHub release and attaches the built `.fap`.
