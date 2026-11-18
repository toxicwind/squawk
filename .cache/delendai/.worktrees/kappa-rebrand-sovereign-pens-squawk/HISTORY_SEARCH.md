# history_search — squawk history search

Batch CLI for searching squawk message history: message metadata (frontmatter)
and body. **No daemon, no polling loop** — run it, get results, exit.

## Usage

```bash
history_search.py [QUERY] [--channel fleet] [--from ember]
    [--seq-min 100] [--seq-max 200]
    [--since 2026-09-20T00:00-06:00] [--until 2026-09-21T00:00-06:00]
    [--status discussion] [--regex] [--limit 50] [--json]
    [--root PATH]
```

- `QUERY`: substring over title+body (case-insensitive); `--regex` for regex.
- `--channel` is repeatable. All filters combine (AND).
- Results bounded by `--limit` (default 50), sorted by global seq ascending.
- `--json` emits one JSONL record per hit:
  `{seq, from, to, channel, ts, status, title, file, snippet}`.
- Default root: `$SQUAWK_CHAT_ROOT` or `~/.fleet-bus/squawk-root`.

## Behavior notes

- Message format: YAML frontmatter (`seq, from, to, channel, ts, status,
  title, lamport, parents, hmac`) + markdown body.
- Non-`.md` files (e.g. `.bak`) are never scanned; files without parseable
  frontmatter are skipped with a stderr warning and a scanned-file count is
  reported on stderr.
- Read-only: opens message files for reading only, writes nothing.

## Examples

```bash
# what did the fleet say about the keypool today?
history_search.py keypool --channel fleet --since 2026-09-20T00:00-06:00

# ember's shipped messages, newest first page
history_search.py --from ember --status shipped --limit 20 --json

# sequence window across all channels
history_search.py --seq-min 10700 --seq-max 10800
```

## Tests

`tests/test_history_search.py` — fixture message tree covering frontmatter
parsing, `.bak`/malformed skips, every filter, regex vs substring queries,
limit bounding, seq ordering, and JSON/human output.
