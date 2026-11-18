## 2024-05-24 - CLI Output Alignment Bug
**Learning:** Fixed a visual alignment issue in the CLI `channels` command output where columns were misaligned if all channel names were shorter than the column header "CHANNEL".
**Action:** Always ensure dynamic column width calculation accounts for the length of the column headers, not just the data, to guarantee visual alignment.

## 2026-07-25 - Empty states already exist; keep CLI output ASCII
**Learning:** `chat.py` already prints an empty state on every path that can produce no output -- `cmd_channels` at both of its exits (`chat.py:212`, `chat.py:229`), `cmd_read` when nothing is unread (`chat.py:311`), `cmd_peek` on an empty channel (`chat.py:345`) -- and `require_channel` (`chat.py:64`) already names the recovery command. Four separate PRs proposed appending a call-to-action to those same lines; only the column-width fix addressed something that was actually broken. One of them used an em dash, which does not survive this CLI's own portability claim: the module docstring states it runs identically on Windows, WSL and Linux, and on a Windows console `sys.stdout.encoding` is `cp1252`, where non-ASCII is emitted as a byte that is invalid UTF-8 or raises `UnicodeEncodeError`.
**Action:** Run the command and paste the real before/after terminal output into the PR body as the evidence that a UX defect exists. Keep all CLI output ASCII -- use `-`, never an em dash. Write this journal to `.jules/` in lowercase; `.Jules/` is a separate, unread directory on a case-sensitive filesystem.

## 2024-08-11 - CLI Stdin EOF Prompt
**Learning:** When prompting for input via stdin in a CLI application, instructing the user to "send EOF" is too technical and can lead to confusion. Platform-specific instructions are needed.
**Action:** When reading from stdin and using `sys.stdin.isatty()` to provide a prompt, include platform-specific instructions on how to send EOF (e.g., "press Ctrl-D (or Ctrl-Z and Enter on Windows) to finish").

## 2024-08-12 - CLI Error Handling and Formatting
**Learning:** Raw stack traces from common errors like missing files (OSError) or user cancellation (KeyboardInterrupt) break the illusion of a polished tool. Additionally, printing raw Python data structures (like `['agent-1', 'agent-2']`) instead of formatted strings looks unfinished.
**Action:** Catch `KeyboardInterrupt` globally to exit cleanly (code 130). Catch common I/O errors and map them to application-specific error types with clear messages. Always format lists (e.g., `, `.join()) before presenting them to the user.

## 2024-08-13 - Truncate long strings in CLI tables
**Learning:** Extremely long member lists can push CLI table columns out of alignment and clutter the output, making it unreadable. Additionally, raw lists formatted without spaces (e.g., `alice,bob,charlie`) are visually dense.
**Action:** When displaying lists in CLI tables (e.g., in `cmd_channels`), use an ellipsis (`...`) to truncate the string to a reasonable length instead of a hard slice, preventing abrupt cut-offs. Also format lists with `, ` (comma + space) for better readability.
## 2024-03-24 - Dynamic CLI Column Alignment for Tasks
**Learning:** Hardcoded column spacing in text-based CLIs breaks visually when field content like "OWNER" or "DEPENDS_ON" has varying lengths, making it difficult for users to read table output cleanly.
**Action:** When printing tables to the CLI, calculate the maximum width needed for each column across all rows (including headers), and use `.ljust(width)` to format the text uniformly.

## 2024-05-25 - Self-documenting CLI Interfaces
**Learning:** For Python CLI applications, providing descriptive `help` text for all `argparse` arguments (both positional and optional) significantly improves usability by making the interface self-documenting via the `--help` flag.
**Action:** Always add descriptive `help` parameters to all `add_argument` calls in CLI applications, not just the top-level commands.
## 2026-08-31 - Adding help text for argparse arguments
**Learning:** For Python CLI applications, providing descriptive `help` text for all `argparse` arguments (both positional and optional) significantly improves usability by making the interface self-documenting via the `--help` flag.
**Action:** Always ensure that when defining CLI arguments using `argparse`, both positional and optional parameters are provided with a concise, descriptive `help` string to aid users in understanding the command's requirements and usage.

## Rejected

- **2026-09-05 — Additional subparser title/help PRs (#163, #170):**
  The top-level, event and task command groups now have explicit titles and
  descriptions. Check the current `chat.py --help`, `chat.py event --help` and
  `chat.py task --help` output before proposing another help-only rewrite.
## 2024-06-25 - Cleaner CLI help output for subcommands
**Learning:** For Python CLI applications, providing descriptive `help` text for `argparse` arguments improves usability. For `add_subparsers` groups specifically, explicitly set the `metavar` argument (e.g., `metavar="COMMAND"`) to prevent the default, verbose listing of all subcommands in curly braces, making the usage string much cleaner.
**Action:** When defining `add_subparsers` in Python `argparse`, explicitly set `metavar` to improve readability.
## 2024-09-08 - Add metavar to argparse subparsers
**Learning:** For Python CLI applications using `argparse`, adding a `metavar` argument to `add_subparsers` groups significantly improves the readability of the `--help` output by replacing the default verbose positional argument list with a clean placeholder.
**Action:** When adding sub-commands to Python CLIs, always explicitly set the `metavar` on the subparser group to a clear, singular noun (e.g., `COMMAND`) to keep the help text clean.
## 2024-05-27 - List formatting in Task CLI output
**Learning:** Raw lists formatted without spaces (e.g., `task-1,task-2`) in CLI tables and task detail views are visually dense and harder to read.
**Action:** Use ", " (comma + space) to format list items in CLI output to improve readability and visual spacing.
## 2026-09-11 - Graceful OSError handling
**Learning:** For Python CLI applications, it is a poor UX to leak raw internal stack traces to the user when unhandled permissions or system IO errors occur.
**Action:** Wrap all `OSError` exceptions globally at the CLI entry point using a clean standard error output to improve generic human legibility and accessibility.
