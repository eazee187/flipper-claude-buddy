## v0.7.6

- `flipper-restart-bridge` skill now documents and diagnoses the BLE connect-then-instantly-disconnect failure mode caused by missing passkey pairing on the host (Bridge-mode's built-in serial profile requires it, unlike the custom NUS profile) — includes the `bluetoothctl` pairing steps to fix it.

## v0.7.5

- On-device Usage page now also shows Claude's 5h-window and weekly rate-limit usage percentages (from `claude /usage`), alongside the existing token/cost stats.
- New `flipper-restart-bridge` skill: cleanly restarts the host bridge daemon and reconnects (USB or BLE) without a manual `kill`/socket cleanup dance.
- Fixed a crash in the BLE transport: a transient GATT/DBus error while enabling notifications (e.g. right after connecting) was left unhandled and took down the whole bridge daemon instead of just failing that one connection attempt. The bridge now logs the error and retries on the next reconnect tick, like it already did for connection failures.

## v0.7.4

- The Up button, when dictation is disabled (the Linux default), sends a configurable quick-action command (e.g. `/compact`) — now configurable directly on the Flipper: hold Right → MENU → Quick Action, type a new command (blank = revert to host default), OK to save. Takes effect immediately, no reconnect needed. Still configurable via `FLIPPER_QUICK_ACTION`/the plugin's Quick Action Command option as before.
- The status header now shows the actual configured quick-action text (e.g. "/compact") instead of a generic "Mic" hint when dictation is disabled.
- Fixed `ydotool` (Linux Wayland) sending wrong key names for Enter/Escape/Page Up/Page Down (X11 keysym names instead of the Linux `KEY_*` names ydotool expects) — Enter presses were landing as a literal "r" keystroke, breaking the Up-button quick action and occasionally the OK-button confirm.

## v0.7.3

- Fixed `ydotool` (Linux Wayland) mis-typing characters on German (QWERTZ) keyboard layouts — e.g. `/` arriving as `-`. The bridge now auto-detects the system layout and remaps the common German-layout differences; override with `FLIPPER_KEYBOARD_LAYOUT=de|us`.
- Fixed the on-device permission prompt (OK/Select) sometimes not registering: a status/notify update arriving from the host while the prompt was showing could silently evict it back to the status screen, so the next button press sent a plain keystroke instead of the permission decision. Reproduced over both USB and BLE since it was a GUI-thread view-arbitration bug, not a transport issue.

## v0.7.2

- Usage page and header context-% now source their numbers from the [ecc plugin](https://github.com/affaan-m/ECC) instead of computing them independently — install ecc for reliable data; without it these stay empty. README documents how to install ecc.

## v0.7.1

- Updated author/repo attribution throughout (plugin metadata, marketplace listing, on-device About/Help pages) to the current maintainer.

## v0.7

- Linux Wayland keystroke forwarding via `ydotool`, auto-detected alongside the existing `xdotool` (X11) backend.
- Fixed a crash and garbled keystrokes on the new Wayland backend (missing import, wrong `ydotool` CLI syntax).
- New on-device **Usage** info page: cumulative session token counts and an estimated cost.
- New context-window-remaining % shown directly on the main screen header.

## v0.6

- Fixed connection/disconnection state handling in Bridge mode.
- Fixed a memory leak in the Flipper app.


## v0.5

- New **Claude Desktop (BLE)** mode: talks directly to the Claude Desktop app over Anthropic's Hardware Buddy protocol. No plugin needed.
- Linux support for the host bridge plugin — thanks to @DanilaE for the contribution!
- Info menu relabels: **Claude Code (USB/BLE)** / **Claude Desktop (BLE)**.
- Help and Transcript pages are now mode-aware.
- Changed Flipper app category from USB to Bluetooth.


## v0.4

- Info menu (Hold ►): Help, Transcript, Plan/Code Mode, About.
- Transcript scrolling with Page Up/Down and jump-to-top/bottom.
- Flipper notifications for tool failures and elicitation prompts.

## v0.3

- Auto-discover slash commands from user/project commands, skills, and enabled plugins.
- Selected menu commands are promoted to the top of the list for convenient re-use.

## v0.2

- Routed remote input to the active runner session, including the correct terminal tab.
- Added Up-button long-press support for Claude voice input.
- Fixed BLE signal bars in the header.
- Fixed slash-command menu refresh so the first selected command matches the item shown on screen.

## v0.1

- Initial release with physical remote control, haptic feedback, USB/BLE transport, and Claude Code plugin integration.
