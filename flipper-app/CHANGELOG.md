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
