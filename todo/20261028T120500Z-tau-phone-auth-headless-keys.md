# TODO — Phone Auth SSOT: Bitwarden, Authy & Headless Fast Keys (Alt+Up/Shift+Up)

- status: IN PROGRESS
- author: tau (architect directive 2026-10-28)
- unique-id: tau-phone-auth-headless-keys
- created: 2026-10-28

# Phone Auth SSOT: Bitwarden, Authy & Headless Fast Keys

## User Directive (2026-10-28)
1. **MAX USE PHONE FOR AUTH**: Architect's Pixel 9 Pro XL (`10.0.0.77:43945`, via flotilla MCP `:25245`) has everything:
   - `com.x8bit.bitwarden` (Bitwarden vault)
   - `com.authy.authy` (Authy 2FA/OTP tokens)
   - Stored credentials, keys, authenticators
2. **FAST HEADLESS NAVIGATION DOCTRINE**:
   - `Alt+Up` / `Shift+Up` preferred for fast headless editing and navigation.
   - Use Flotilla MCP (`pixel_key`, `pixel_tap`, `pixel_ui`, `pixel_text`, `pixel_shell`) to interact without desktop UI requirements.
   - In ADB: `adb -s 10.0.0.77:<port> shell input keyevent ...` or flotilla MCP tool calls.

## Verified Packages on Device
- `package:com.x8bit.bitwarden`
- `package:com.authy.authy`
- `package:ch.protonvpn.android`
- `package:co.glasspass.app`
- `package:com.google.android.contactkeys`

## Fleet Invariant
When any service, deployment, git push, or external API requires credentials, 2FA, OTP, or vault retrieval:
DO NOT ask the user or halt.
Query the phone headlessly via flotilla-mcp (:25245) or wireless ADB (`10.0.0.77:43945`).
