"""Behavior tests for the non-blocking agent-chat Claude Code hooks."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROMPT_INBOX_HOOK = REPOSITORY_ROOT / "hooks" / "prompt_inbox.py"
STOP_INBOX_HOOK = REPOSITORY_ROOT / "hooks" / "stop_inbox.py"
SESSION_INBOX_HOOK = REPOSITORY_ROOT / "hooks" / "session_inbox.py"


def _run_hook_copy(hook_path, **environment):
    """Run a hook copy whose directory chain holds no chat.py."""
    with tempfile.TemporaryDirectory() as bare_dir:
        bare_hooks = Path(bare_dir) / "hooks"
        bare_hooks.mkdir()
        for name in (hook_path.name, "session_inbox.py"):
            (bare_hooks / name).write_text(
                (REPOSITORY_ROOT / "hooks" / name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        env = os.environ.copy()
        for env_name in (
            "AGENT_CHAT_NAME",
            "AGENT_CHAT_ROOT",
            "AGENT_CHAT_CHANNELS",
            "CLAUDE_PLUGIN_ROOT",
        ):
            env.pop(env_name, None)
        env.update(environment)
        return subprocess.run(
            [sys.executable, str(bare_hooks / hook_path.name)],
            capture_output=True,
            check=False,
            encoding="utf-8",
            env=env,
        )


class PromptInboxHookTests(unittest.TestCase):
    HOOK = PROMPT_INBOX_HOOK

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _channel(self, name="general"):
        channel = self.root / name
        channel.mkdir()
        (channel / "_meta.json").write_text(
            json.dumps({"channel": name, "members": [], "topic": ""}),
            encoding="utf-8",
        )
        return channel

    def _message(self, channel, sequence, sender, recipient="all"):
        (channel / f"{sequence:04d}-{sender}-message.md").write_text(
            "---\n"
            f"seq: {sequence}\n"
            f"from: {sender}\n"
            f"to: {recipient}\n"
            f"channel: {channel.name}\n"
            "title: Message\n"
            "---\n"
            "body\n",
            encoding="utf-8",
        )

    def _run_hook(self, **environment):
        env = os.environ.copy()
        for name in (
            "AGENT_CHAT_NAME",
            "AGENT_CHAT_ROOT",
            "AGENT_CHAT_CHANNELS",
            "CLAUDE_PLUGIN_ROOT",
        ):
            env.pop(name, None)
        env.update(environment)
        return subprocess.run(
            [sys.executable, str(self.HOOK)],
            capture_output=True,
            check=False,
            encoding="utf-8",
            env=env,
        )

    def test_stays_quiet_when_there_are_no_messages(self):
        """Adding no peer message must not produce a prompt notice."""
        self._channel()

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_reports_relevant_messages_above_the_cursor_by_channel_and_count(self):
        """Removing relevance filtering or sequence checks must change this notice."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")
        self._message(channel, 2, "carol", "alice")
        (channel / ".cursors").mkdir()
        (channel / ".cursors" / "alice.txt").write_text("0", encoding="utf-8")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertIn("review", result.stdout)
        self.assertIn("2", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_ignores_messages_for_another_agent_and_its_own_messages(self):
        """A recipient or sender filtering regression must not wake this agent."""
        channel = self._channel()
        self._message(channel, 1, "bob", "carol")
        self._message(channel, 2, "alice", "all")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_returns_quietly_without_an_identity_or_when_root_is_missing(self):
        """Unconfigured prompt hooks must never obstruct Claude Code."""
        no_identity = self._run_hook(AGENT_CHAT_ROOT=str(self.root))
        missing_root = self._run_hook(
            AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root / "missing")
        )

        for result in (no_identity, missing_root):
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_leaves_the_read_cursor_unchanged(self):
        """Writing a cursor here would hide a message from chat.py read."""
        channel = self._channel()
        self._message(channel, 3, "bob", "alice")
        cursor = channel / ".cursors" / "alice.txt"
        cursor.parent.mkdir()
        cursor.write_text("2", encoding="utf-8")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(cursor.read_text(encoding="utf-8"), "2")

    def test_invalid_configured_channel_does_not_hide_a_valid_inbox(self):
        """Invalid channels must not suppress unread messages in a later one."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")

        for invalid_channel in ("../invalid", "a" * 256):
            with self.subTest(invalid_channel=invalid_channel):
                result = self._run_hook(
                    AGENT_CHAT_NAME="alice",
                    AGENT_CHAT_ROOT=str(self.root),
                    AGENT_CHAT_CHANNELS=f"{invalid_channel},review",
                )

                self.assertEqual(result.returncode, 0)
                self.assertIn("review", result.stdout)
                self.assertIn("1", result.stdout)
                self.assertEqual(result.stderr, "")

        self.assertFalse((channel / ".cursors").exists())

    def test_claude_plugin_root_env_overrides_the_directory_chain(self):
        """CLAUDE_PLUGIN_ROOT must win over an unresolvable script location."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")
        result = _run_hook_copy(
            self.HOOK,
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
            CLAUDE_PLUGIN_ROOT=str(REPOSITORY_ROOT),
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("review", result.stdout)
        self.assertIn("1", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_skips_with_one_line_stderr_note_when_no_root_resolves(self):
        """Without chat.py reachable, the hook exits 0 with one stderr line."""
        result = _run_hook_copy(
            self.HOOK,
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        note_lines = result.stderr.strip().splitlines()
        self.assertEqual(len(note_lines), 1)
        self.assertIn("[agent-chat]", note_lines[0])

    def test_unresolvable_plugin_root_env_exits_zero_with_a_note(self):
        """A broken CLAUDE_PLUGIN_ROOT must skip, never crash the session."""
        result = self._run_hook(
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
            CLAUDE_PLUGIN_ROOT=str(self.root / "nowhere"),
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        note_lines = result.stderr.strip().splitlines()
        self.assertEqual(len(note_lines), 1)
        self.assertIn("[agent-chat]", note_lines[0])

    def test_unread_notice_is_bounded_across_many_relevant_channels(self):
        """Hook stdout stays within the context budget with many channels."""
        channel_names = [f"channel-{index:02d}" for index in range(20)]
        for channel_name in channel_names:
            channel = self._channel(channel_name)
            self._message(channel, 1, "bob", "alice")

        result = self._run_hook(
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
            AGENT_CHAT_CHANNELS=",".join(channel_names),
        )

        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout), 300)
        self.assertIn("channel-00", result.stdout)
        self.assertTrue("…" in result.stdout or "\\u2026" in result.stdout)
        self.assertEqual(result.stderr, "")


class StopInboxHookTests(PromptInboxHookTests):
    HOOK = STOP_INBOX_HOOK

    def test_warning_uses_claude_system_message_with_channel_and_count(self):
        """Stop-hook warnings must use Claude's visible systemMessage field."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertIn("review", payload["systemMessage"])
        self.assertIn("1", payload["systemMessage"])
        self.assertEqual(result.stderr, "")


class SessionInboxHookTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _channel(self, name="general"):
        channel = self.root / name
        channel.mkdir()
        (channel / "_meta.json").write_text(
            json.dumps({"channel": name, "members": [], "topic": ""}),
            encoding="utf-8",
        )
        return channel

    def _message(self, channel, sequence, sender, recipient="all"):
        (channel / f"{sequence:04d}-{sender}-message.md").write_text(
            "---\n"
            f"seq: {sequence}\n"
            f"from: {sender}\n"
            f"to: {recipient}\n"
            f"channel: {channel.name}\n"
            "title: Message\n"
            "---\n"
            "body\n",
            encoding="utf-8",
        )

    def _run_hook(self, **environment):
        env = os.environ.copy()
        for name in (
            "AGENT_CHAT_NAME",
            "AGENT_CHAT_ROOT",
            "AGENT_CHAT_CHANNELS",
            "CLAUDE_PLUGIN_ROOT",
        ):
            env.pop(name, None)
        env.update(environment)
        return subprocess.run(
            [sys.executable, str(SESSION_INBOX_HOOK)],
            capture_output=True,
            check=False,
            encoding="utf-8",
            env=env,
        )

    def test_stays_quiet_without_an_identity_when_the_chat_root_is_missing(self):
        """An unconfigured chat installation must not produce an identity warning."""
        result = self._run_hook(AGENT_CHAT_ROOT=str(self.root / "missing"))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_claude_plugin_root_env_overrides_the_directory_chain(self):
        """CLAUDE_PLUGIN_ROOT must win over an unresolvable script location."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")
        result = _run_hook_copy(
            SESSION_INBOX_HOOK,
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
            CLAUDE_PLUGIN_ROOT=str(REPOSITORY_ROOT),
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("review", result.stdout)
        self.assertIn("1", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_skips_with_one_line_stderr_note_when_no_root_resolves(self):
        """Without chat.py reachable, the hook exits 0 with one stderr line."""
        result = _run_hook_copy(
            SESSION_INBOX_HOOK,
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        note_lines = result.stderr.strip().splitlines()
        self.assertEqual(len(note_lines), 1)
        self.assertIn("[agent-chat]", note_lines[0])

    def test_unresolvable_plugin_root_env_exits_zero_with_a_note(self):
        """A broken CLAUDE_PLUGIN_ROOT must skip, never crash the session."""
        result = self._run_hook(
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
            CLAUDE_PLUGIN_ROOT=str(self.root / "nowhere"),
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        note_lines = result.stderr.strip().splitlines()
        self.assertEqual(len(note_lines), 1)
        self.assertIn("[agent-chat]", note_lines[0])

    def test_unread_notice_is_bounded_across_many_relevant_channels(self):
        """SessionStart stdout stays within the context budget."""
        channel_names = [f"channel-{index:02d}" for index in range(20)]
        for channel_name in channel_names:
            channel = self._channel(channel_name)
            self._message(channel, 1, "bob", "alice")

        result = self._run_hook(
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
            AGENT_CHAT_CHANNELS=",".join(channel_names),
        )

        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout), 300)
        self.assertIn("channel-00", result.stdout)
        self.assertIn("…", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_invalid_configured_channel_does_not_hide_a_valid_inbox(self):
        """Session start must still notify about valid configured channels."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")

        for invalid_channel in ("../invalid", "a" * 256):
            with self.subTest(invalid_channel=invalid_channel):
                result = self._run_hook(
                    AGENT_CHAT_NAME="alice",
                    AGENT_CHAT_ROOT=str(self.root),
                    AGENT_CHAT_CHANNELS=f"{invalid_channel},review",
                )

                self.assertEqual(result.returncode, 0)
                self.assertIn("review", result.stdout)
                self.assertIn("1", result.stdout)
                self.assertEqual(result.stderr, "")

        self.assertFalse((channel / ".cursors").exists())


if __name__ == "__main__":
    unittest.main()
