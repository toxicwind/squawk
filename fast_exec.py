#!/usr/bin/env python3
"""fast_exec: 2s-deadline async shell execution with racing.

Standing directive (2026-10-13): every command runs background-async with a
strict <2s timeout per execution. A command that exceeds its deadline is
"considered failed" — the caller races FASTER alternatives and takes the
first success.

API:
    result = await run("some command", deadline=2.0)
    result = await race(["cmd_a", "cmd_b", "cmd_c"], deadline=2.0)
    task   = spawn("some command", deadline=2.0, on_done=cb)  # fire-and-forget
    result = run_sync("some command", deadline=2.0)           # sync wrapper

    result.returncode  # int, or None when killed/timed out
    result.stdout      # str (capped at OUT_CAP chars)
    result.stderr      # str (capped at OUT_CAP chars)
    result.timed_out   # bool — True when the deadline fired
    result.elapsed     # float seconds wall-clock
    result.cmd         # the command string that produced this result
    result.ok          # True when returncode == 0 and not timed_out

race() launches every alternative concurrently and returns the first
result with ok == True. If none succeed, it returns the fastest failure.
Losers are killed immediately — no stragglers.

Design notes:
- asyncio-first; the event loop is never blocked by a slow child.
- On deadline: SIGKILL the whole process group, reap, mark timed_out.
- Output is capped so a chatty child cannot blow up memory.
"""

import asyncio
import inspect
import os
import signal
import sys
import time
from dataclasses import dataclass, field

DEFAULT_DEADLINE = 2.0
OUT_CAP = 100_000


@dataclass
class ExecResult:
    cmd: str
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    elapsed: float

    @property
    def ok(self) -> bool:
        return (not self.timed_out) and self.returncode == 0

    def short(self) -> str:
        state = "TIMEOUT" if self.timed_out else f"exit={self.returncode}"
        return f"[{state} {self.elapsed:.2f}s] {self.cmd[:80]}"


def _cap(b: bytes | None) -> str:
    if not b:
        return ""
    s = b.decode("utf-8", errors="replace")
    if len(s) > OUT_CAP:
        return s[:OUT_CAP] + f"\n...[truncated {len(s) - OUT_CAP} chars]"
    return s


async def run(cmd: str, deadline: float = DEFAULT_DEADLINE,
              workdir: str | None = None,
              env: dict | None = None) -> ExecResult:
    """Run one shell command background-async with a hard deadline."""
    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir or None,
            env=env,
            start_new_session=True,  # own process group -> killpg works
        )
    except Exception as e:
        return ExecResult(cmd=cmd, returncode=None, stdout="",
                          stderr=f"spawn failed: {e}"[:500],
                          timed_out=False,
                          elapsed=time.monotonic() - t0)
    was_timeout = False
    was_cancelled = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=deadline)
    except asyncio.TimeoutError:
        was_timeout = True
    except asyncio.CancelledError:
        # race() cancels losing tasks: kill the child the same way as a
        # deadline breach so no orphan process leaks, then re-raise to keep
        # task-cancellation semantics intact.
        was_cancelled = True
    else:
        return ExecResult(cmd=cmd, returncode=proc.returncode,
                          stdout=_cap(out), stderr=_cap(err),
                          timed_out=False,
                          elapsed=time.monotonic() - t0)
    # Deadline fired or task cancelled: SIGKILL the whole process group.
    # The kill itself is synchronous (no await) so it lands even while the
    # task is mid-cancellation; reap/drain below are best-effort and must
    # never raise.
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=1.0)
    except BaseException:
        pass
    # drain whatever is left without blocking
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=0.5)
    except BaseException:
        out, err = b"", b""
    if was_cancelled:
        raise asyncio.CancelledError()
    return ExecResult(cmd=cmd, returncode=None,
                      stdout=_cap(out), stderr=_cap(err),
                      timed_out=was_timeout,
                      elapsed=time.monotonic() - t0)


async def race(cmds: list[str], deadline: float = DEFAULT_DEADLINE,
               workdir: str | None = None,
               env: dict | None = None) -> ExecResult:
    """Race N alternative commands; first ok wins, losers are killed."""
    if not cmds:
        return ExecResult(cmd="", returncode=None, stdout="",
                          stderr="race: no commands given",
                          timed_out=False, elapsed=0.0)
    tasks = {asyncio.ensure_future(run(c, deadline, workdir, env)): c
             for c in cmds}
    fastest_failure: ExecResult | None = None
    try:
        while tasks:
            done, _ = await asyncio.wait(tasks.keys(),
                                         return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                tasks.pop(t)
                try:
                    r = t.result()
                except asyncio.CancelledError:
                    r = ExecResult(cmd="", returncode=None, stdout="",
                                   stderr="race task cancelled",
                                   timed_out=False, elapsed=0.0)
                except Exception as e:
                    r = ExecResult(cmd="", returncode=None, stdout="",
                                   stderr=f"race task crashed: {e}"[:300],
                                   timed_out=False, elapsed=0.0)
                if r.ok:
                    for loser in tasks:
                        loser.cancel()
                    return r
                if fastest_failure is None or r.elapsed < fastest_failure.elapsed:
                    fastest_failure = r
        return fastest_failure or ExecResult(
            cmd=cmds[0], returncode=None, stdout="",
            stderr="race: all alternatives failed silently",
            timed_out=False, elapsed=0.0)
    finally:
        for t in tasks:
            t.cancel()


def spawn(cmd: str, deadline: float = DEFAULT_DEADLINE,
          on_done=None, workdir: str | None = None) -> asyncio.Task:
    """Fire-and-forget: run in background, optional on_done(result) callback."""
    async def _wrapper():
        r = await run(cmd, deadline, workdir)
        if on_done:
            try:
                if inspect.iscoroutinefunction(on_done):
                    await on_done(r)
                else:
                    on_done(r)
            except Exception:
                pass
        return r
    return asyncio.ensure_future(_wrapper())


def run_sync(cmd: str, deadline: float = DEFAULT_DEADLINE,
             workdir: str | None = None) -> ExecResult:
    """Synchronous wrapper for non-async callers."""
    return asyncio.run(run(cmd, deadline, workdir))


async def _selftest() -> int:
    print("fast_exec selftest — deadline=%.1fs" % DEFAULT_DEADLINE)
    # 1. fast command succeeds
    r = await run("echo hello-fast")
    assert r.ok and "hello-fast" in r.stdout, r.short()
    print("  [ok] fast command:", r.short())

    # 2. slow command hits the deadline
    r = await run("sleep 10", deadline=1.0)
    assert r.timed_out and not r.ok, r.short()
    assert r.elapsed < 2.0, f"kill took too long: {r.elapsed}"
    print("  [ok] slow command timed out:", r.short())

    # 3. failing command reports non-zero
    r = await run("exit 3")
    assert not r.ok and r.returncode == 3 and not r.timed_out, r.short()
    print("  [ok] failing command:", r.short())

    # 4. race: slow primary loses, fast alternative wins
    r = await race(["sleep 10", "echo fast-alt"], deadline=1.5)
    assert r.ok and "fast-alt" in r.stdout, r.short()
    print("  [ok] race picks fast alternative:", r.short())

    # 5. race with all failures returns fastest failure
    r = await race(["exit 1", "exit 2"], deadline=1.5)
    assert not r.ok and not r.timed_out, r.short()
    print("  [ok] race all-fail:", r.short())

    # 6. spawn fire-and-forget
    seen = []
    t = spawn("echo bg-done", on_done=lambda res: seen.append(res.stdout.strip()))
    await t
    assert seen == ["bg-done"], seen
    print("  [ok] spawn fire-and-forget")

    print("SELFTEST 6/6 GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_selftest()))
