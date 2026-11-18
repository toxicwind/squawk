## 2024-07-20 - [Path Traversal in CLI Arguments]
**Vulnerability:** The application blindly joined user-provided channel and task arguments directly with the root path using `pathlib.Path(root) / channel`. This allowed path traversal (e.g. `../`) allowing users to access files outside the intended directories.
**Learning:** `pathlib` operator `/` does not magically prevent directory traversal if relative path strings like `../` are passed into it. Any user-controlled file path component needs strict validation.
**Prevention:** Implement strict string-level validation against slashes (`/`, `\`) and traversal symbols (`.`, `..`) for arbitrary file and directory name inputs from CLI flags, ensuring they contain only valid base names before joining them to any root directories.

## 2026-07-25 - The containment check is in; land future chat.py fixes here, not in the mirror
**Vulnerability:** Closed by `_check_safe_name` (`chat.py:57`), applied in `channel_dir` and `cmd_claim`. Seven PRs proposed this same fix; five of them used `Path.resolve().is_relative_to()`, which is Python 3.9+ and silently breaks the `requires-python = ">=3.8"` floor declared in `pyproject.toml:9`.
**Learning:** Two things this batch got wrong beyond the duplication. First, the argv of a local CLI is supplied by the operator who already owns the shell, so "an attacker passes `../`" is not the reason the fix matters -- the reason is that `AGENT_CHAT_ROOT` is documented as the boundary that holds every channel and the code did not honour it. Second, `die()` raises `SystemExit`, a `BaseException`: adding it to a function that `hooks/session_inbox.py` imports made the SessionStart hook exit 1 on a malformed `AGENT_CHAT_CHANNELS` entry, contradicting the hook's documented "always exits 0". That regression is fixed in the same series.
**Prevention:** State the trust boundary being crossed and paste a reproduction before filing a finding; a lexical basename check is sufficient here and stays inside the supported Python floor. When adding a guard to a function that the hook imports, check that the hook's `except` clauses still cover it. This repo is the upstream source of the marketplace copy: `n24q02m/claude-plugins` regenerates `plugins/agent-chat-plugin/` from here via `scripts/sync-plugins.sh`, so `chat.py`, `hooks/` and `skills/` fixes belong in this repo and will propagate; the same edit made in the marketplace is overwritten on the next sync.

## 2024-08-12 - [Reserved Prefix Blocking]
**Vulnerability:** The application allowed user-provided filenames to start with reserved prefixes like `.` or `_` in `chat.py`. This could allow Insecure Direct Object Reference (IDOR) and Denial of Service (DoS) attacks even if path traversal is blocked.
**Learning:** Explicitly blocking reserved prefixes for user-supplied filenames protects internal system files or directories and prevents unauthorized access or manipulation.
**Prevention:** Implement checks for reserved prefixes (`.` and `_`) in filename validation functions, such as `_check_safe_name` in `chat.py`.

## 2024-08-13 - [Denial of Service via Malformed Data]
**Vulnerability:** The application crashed with raw stack traces when encountering malformed `_meta.json` or invalid UTF-8 bytes in message files, creating a Denial of Service (DoS) and leaking implementation details.
**Learning:** Always fail securely by catching decoding exceptions like `UnicodeDecodeError` and `json.decoder.JSONDecodeError` (`ValueError`) when parsing external or user-provided files, and wrap them in friendly domain errors.
**Prevention:** Use `try...except (OSError, ValueError):` when parsing JSON files, and `try...except (OSError, UnicodeDecodeError):` when reading text files with a specific encoding.
## 2024-10-26 - [Denial of Service via Uncaught UnicodeDecodeError in file reading]
**Vulnerability:** The application crashed with raw stack traces when reading non-UTF-8 message bodies (`--body-file`) or message files, causing a Denial of Service (DoS) during read operations.
**Learning:** `Path.read_text(encoding="utf-8")` raises `UnicodeDecodeError` on invalid bytes, which must be caught and handled securely.
**Prevention:** Wrap `Path.read_text(encoding="utf-8")` calls in `try...except (OSError, UnicodeDecodeError):` blocks to fail gracefully without crashing the application.

## 2024-12-09 - [Denial of Service via Uncaught UnicodeDecodeError in event parsing]
**Vulnerability:** The application crashed with a raw stack trace when reading malformed event files containing invalid UTF-8 bytes in `_event_body`, causing a Denial of Service (DoS).
**Learning:** `Path.read_text(encoding="utf-8")` raises `UnicodeDecodeError` on invalid bytes. When processing files, especially those that might be user-provided or modified by external tools, file reading operations must catch these exceptions.
**Prevention:** Wrap `Path.read_text(encoding="utf-8")` calls in `try...except (OSError, UnicodeError):` blocks to fail securely and gracefully without crashing the application.

## 2026-08-31 - [Denial of Service via Uncaught UnicodeError in stdin reading]
**Vulnerability:** The application crashed with a raw stack trace when reading malformed UTF-8 bytes from stdin via `sys.stdin.read()`, causing a Denial of Service (DoS). The bytes were often converted to surrogate escapes which later caused `UnicodeEncodeError` when writing.
**Learning:** `sys.stdin.read()` may not immediately fail on invalid UTF-8 depending on environment settings (e.g., using `surrogateescape`). These invalid strings can propagate and crash the application during later file writes. We must strictly force UTF-8 validation at the input boundary.
**Prevention:** Force encoding of the read string via `data.encode("utf-8")` immediately after reading from `sys.stdin` and wrap it in a `try...except (OSError, UnicodeError):` block to fail securely.

## 2024-12-11 - [Denial of Service via Uncaught UnicodeError in file operations]
**Vulnerability:** The application was catching only `UnicodeDecodeError` when reading/writing files, potentially crashing from `UnicodeEncodeError` issues (e.g., surrogate escapes) during file operations.
**Learning:** When explicitly catching encoding exceptions during file I/O operations (e.g., using `read_text()` or `open()`), catch the base `UnicodeError` instead of just `UnicodeDecodeError`. This ensures that unhandled `UnicodeEncodeError` issues do not lead to Denial of Service (DoS) application crashes.
**Prevention:** Catch the broader `UnicodeError` class instead of the specific `UnicodeDecodeError`.
