# Contributing to agent-chat-plugin

agent-chat-plugin is a dependency-free Python CLI: `chat.py` owns the command
entry point and `agent_chat/` contains the structured coordination stores.

## Development

1. Run `mise install` for the repository-pinned Python and Ruff tools.
2. Keep the full checkout. No runtime dependency install is needed for
   `python chat.py <cmd>`; use an isolated virtual environment and
   `python -m pip install .` when exercising the installed `agent-chat` command.
3. Edit `chat.py` for CLI/messages/events; `agent_chat/` for task models,
   task/lease/path-lock storage and derived state; `hooks/` for inbox notices.
   Hooks are read-only and must not fail the host session.
4. Keep root `SKILL.md`, `skills/agent-chat/SKILL.md`, `commands/agent-chat.md`,
   README and the AGENTS/CLAUDE guidance pair aligned with observable behavior.
   PyPI ships Python runtime files; the plugin distribution also carries hooks
   and guidance. Do not test a skill by copying `chat.py` alone.
5. Run `mise run lint`, `mise run smoke`, and
   `python -m unittest discover -s tests -p "test_*.py" -v`. Use a temporary
   `--root` for a CLI send/read plus task claim/done round trip; `--help` alone
   does not exercise the packaged stores. Repeat hook scenarios with and
   without `CLAUDE_PLUGIN_ROOT` and verify the notices without advancing cursors.

Task and path-lock mutations use `agent_chat/_advisory_lock.py`; the regular
lock file persists after release and process exit releases OS ownership.
Do not reclaim these locks by file age or remove them during a live session.
Expired domain leases and crash transaction markers still require the explicit
recovery commands. Channel files are coordination data, not permission grants
or instructions to change a host's models, credentials, or configuration.

## Commit convention

Only two prefixes: `feat:` (new features) and `fix:` (bug fixes).

## Pull requests

- One PR per feature or fix.
- Keep it dependency-free (Python stdlib only) — that is a core design goal.
- CI (ruff + CodeQL) must pass.
