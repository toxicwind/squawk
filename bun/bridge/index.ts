// squawk/bun/bridge — mirror the kappa board table as a squawk chat channel.
// Bun port of kappa_board_bridge.py. Two-way, additive, idempotent bridge:
//
//   board -> chat   reads new rows from `kappa_board_message` in the kappa
//                   SQLite DB and writes one squawk message file per row into
//                   <root>/<channel>/<seq>-<sender>-board.md.
//
//   chat  -> board  reads squawk message files in <root>/<channel>/ and inserts
//                   each new one into `kappa_board_message` on the
//                   most-recently-updated `kappa_board` root, bumping the
//                   board's next_seq / message_count counters.
//
// It never deletes anything (reversible) and records a durable high-water mark
// per direction in <channel>/.kappa-bridge-state.json so both loops are safe to
// restart. Board-sourced files carry `source: kappa_board` frontmatter so a
// later board->chat pass never re-imports its own writes.

import { Database } from "bun:sqlite";
import {
  mkdirSync,
  existsSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";

export const STATE_FILENAME = ".kappa-bridge-state.json";
export const BOARD_SOURCE = "kappa_board";

export interface BridgeOptions {
  root: string;
  db: string;
  channel?: string;
  rootSession?: string | null;
}

export interface BridgeStats {
  boardToChat: number;
  chatToBoard: number;
  root: string | null;
  ts: string;
}

function nowISO(): string {
  return new Date().toISOString();
}

/** Parse (seq, frontmatter, body) for a squawk .md message file. */
export function parseFrontmatter(
  path: string,
  name: string,
): { seq: number; fm: Record<string, string>; body: string } {
  let raw = "";
  try {
    raw = readFileSync(path, "utf-8");
  } catch {
    return { seq: 0, fm: {}, body: "" };
  }
  const fm: Record<string, string> = {};
  let body = raw;
  if (raw.startsWith("---\n")) {
    const lines = raw.split("\n");
    let close: number | null = null;
    for (let i = 1; i < lines.length; i++) {
      if (lines[i].trim() === "---") {
        close = i;
        break;
      }
    }
    if (close !== null) {
      body = lines.slice(close + 1).join("\n");
      for (const line of lines.slice(1, close)) {
        const idx = line.indexOf(":");
        if (idx < 0) continue;
        fm[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
      }
    }
  }
  let seq = 0;
  const seqRaw = fm.seq ?? name.split("-")[0];
  const seqNum = Number(seqRaw);
  if (Number.isFinite(seqNum)) seq = seqNum;
  return { seq, fm, body: body.trim() };
}

export function loadState(chanDir: string): Record<string, unknown> {
  const p = `${chanDir}/${STATE_FILENAME}`;
  if (!existsSync(p)) return {};
  try {
    return JSON.parse(readFileSync(p, "utf-8")) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export function saveState(
  chanDir: string,
  state: Record<string, unknown>,
): void {
  mkdirSync(chanDir, { recursive: true });
  writeFileSync(
    `${chanDir}/${STATE_FILENAME}`,
    JSON.stringify(state, null, 2),
    "utf-8",
  );
}

/** Return the root_session_id of the most-recently-updated board (or null). */
export function activeBoard(dbPath: string): string | null {
  const db = new Database(dbPath, { readonly: true });
  try {
    const row = db
      .query(
        "SELECT root_session_id FROM kappa_board ORDER BY time_updated DESC LIMIT 1",
      )
      .get() as any;
    return row ? row.root_session_id : null;
  } finally {
    db.close();
  }
}

interface BoardRow {
  seq: number;
  time_created: number;
  sender_session_id: string;
  recipient: string;
  type: string;
  body: string;
  id: string;
}

/** Return board messages with seq > since. */
export function boardRows(
  dbPath: string,
  since: number,
  root: string | null,
): BoardRow[] {
  const db = new Database(dbPath, { readonly: true });
  try {
    let q =
      "SELECT seq, time_created, sender_session_id, recipient, type, body, id FROM kappa_board_message WHERE seq > ?";
    const args: Array<string | number> = [since];
    if (root !== null) {
      q += " AND board_root_session_id = ?";
      args.push(root);
    }
    q += " ORDER BY seq ASC";
    const rows = db.query(q).all(...args) as any[];
    return rows.map((r) => ({
      seq: Number(r.seq),
      time_created: Number(r.time_created),
      sender_session_id: String(r.sender_session_id),
      recipient: String(r.recipient),
      type: String(r.type),
      body: String(r.body ?? ""),
      id: String(r.id),
    }));
  } finally {
    db.close();
  }
}

function slugify(s: string): string {
  const slug = s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .slice(0, 20);
  return slug || "board";
}

function frontmatterValue(value: unknown): string {
  return String(value ?? "")
    .trim()
    .replace(/\s+/g, " ");
}

export function rowToFile(chanDir: string, row: BoardRow): string {
  const slug = slugify(row.sender_session_id);
  const fpath = `${chanDir}/${row.seq}-${slug}-board.md`;
  const tsIso = new Date(row.time_created).toISOString().slice(0, 19);
  const fm =
    `---\n` +
    `seq: ${row.seq}\n` +
    `from: ${row.sender_session_id}\n` +
    "to: all\n" +
    "channel: kappa_board\n" +
    `ts: ${tsIso}\n` +
    "status: discussion\n" +
    `source: ${BOARD_SOURCE}\n` +
    `board_type: ${frontmatterValue(row.type)}\n` +
    "title: board\n" +
    "---\n" +
    `${row.body.replace(/\s+$/, "")}\n`;
  mkdirSync(chanDir, { recursive: true });
  writeFileSync(fpath, fm, "utf-8");
  return fpath;
}

export function syncBoardToChat(
  chanDir: string,
  dbPath: string,
  root: string | null,
): number {
  const state = loadState(chanDir);
  let cursor = Number(state.board_chat_cursor ?? 0) || 0;
  let written = 0;
  for (const row of boardRows(dbPath, cursor, root)) {
    const seq = row.seq;
    if (seq <= cursor) continue;
    rowToFile(chanDir, row);
    written++;
    cursor = Math.max(cursor, seq);
  }
  state.board_chat_cursor = cursor;
  saveState(chanDir, state);
  return written;
}

/** List chat channel .md files that are NOT board-sourced, sorted by seq. */
export function chatFiles(
  chanDir: string,
): Array<{ seq: number; path: string }> {
  if (!existsSync(chanDir)) return [];
  const out: Array<{ seq: number; path: string }> = [];
  const dir = readdirSync(chanDir) as string[];
  for (const name of dir) {
    if (!name.endsWith(".md")) continue;
    const p = `${chanDir}/${name}`;
    const { seq, fm } = parseFrontmatter(p, name);
    if (seq <= 0 || fm.source === BOARD_SOURCE) continue;
    out.push({ seq, path: p });
  }
  return out.sort((a, b) => a.seq - b.seq);
}

export function insertIntoBoard(
  dbPath: string,
  root: string,
  seq: number,
  chName: string,
  text: string,
): void {
  const rowId = `msg_${seq}_bridge_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const ts = Date.now();
  const db = new Database(dbPath);
  try {
    db.query(
      `INSERT INTO kappa_board_message (
        id, board_root_session_id, seq, time_created, sender_session_id,
        recipient, type, body, reply_to, source_message_id, source_call_id
      ) VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
    ).run(
      rowId,
      root,
      seq,
      ts,
      root,
      "all",
      "message",
      text,
      null,
      `squawk:${chName}`,
      "kappa_board_bridge",
    );
    db.query(
      `UPDATE kappa_board SET next_seq = MAX(next_seq, ? + 1),
        message_count = message_count + 1,
        message_bytes = message_bytes + ?,
        time_updated = ? WHERE root_session_id = ?`,
    ).run(seq, Buffer.byteLength(text, "utf-8"), ts, root);
  } finally {
    db.close();
  }
}

export function syncChatToBoard(
  chanDir: string,
  dbPath: string,
  root: string | null,
): number {
  const state = loadState(chanDir);
  let cursor = Number(state.chat_board_cursor ?? 0) || 0;
  if (root === null) return 0;
  let inserted = 0;
  for (const { seq, path } of chatFiles(chanDir)) {
    if (seq <= cursor) continue;
    const { body } = parseFrontmatter(path, path.split("/").pop() ?? "");
    if (!body.trim()) continue;
    insertIntoBoard(
      dbPath,
      root,
      seq,
      chanDir.split("/").pop() ?? "kappa_board",
      body.trim(),
    );
    cursor = Math.max(cursor, seq);
    inserted++;
  }
  state.chat_board_cursor = cursor;
  saveState(chanDir, state);
  return inserted;
}

export function runSync(opts: BridgeOptions): BridgeStats {
  const channel = opts.channel ?? "kappa_board";
  const chanDir = `${opts.root}/${channel}`;
  const root = opts.rootSession ?? activeBoard(opts.db);
  const boardToChat = syncBoardToChat(chanDir, opts.db, root);
  const chatToBoard = syncChatToBoard(chanDir, opts.db, root);
  return { boardToChat, chatToBoard, root, ts: nowISO() };
}

/** CLI entry. Matches the Python bridge's flags. */
export function main(argv: string[] = process.argv.slice(2)): number {
  const flag = (name: string): string | null => {
    const i = argv.indexOf(name);
    return i >= 0 && i + 1 < argv.length ? argv[i + 1] : null;
  };
  const root =
    flag("--root") ??
    process.env.SQUAWK_ROOT ??
    `${process.env.HOME ?? ""}/.squawk-bus/squawk-root`;
  const db =
    flag("--db") ??
    `${process.env.HOME ?? ""}/.local/share/kappa/kappa-main.db`;
  const channel = flag("--channel") ?? "kappa_board";
  const rootSession = flag("--root-session");
  const watch = argv.includes("--watch");

  const chanDir = `${root}/${channel}`;
  if (!existsSync(chanDir)) {
    console.error(
      `error: channel '${chanDir}' not found (run: chat.py init ${channel})`,
    );
    return 2;
  }
  if (!existsSync(db)) {
    console.error(`error: kappa DB '${db}' not found`);
    return 2;
  }

  const onePass = () => {
    const stats = runSync({ root, db, channel, rootSession });
    if (stats.boardToChat || stats.chatToBoard) {
      console.log(
        `board->chat: ${stats.boardToChat}  chat->board: ${stats.chatToBoard}`,
      );
    }
  };

  if (watch) {
    onePass();
    setInterval(onePass, 3000);
  } else {
    onePass();
  }
  return 0;
}

const isEntry =
  (import.meta as any).main === true ||
  process.argv[1]?.endsWith("bridge/index.ts");
if (isEntry) {
  const code = main();
  // In --watch mode the process must stay alive for setInterval; only exit
  // the process explicitly in one-shot mode (code 2 = early validation error).
  if (process.argv.includes("--watch") && code === 0) {
    // keep the event loop alive (setInterval in main() does this)
  } else {
    process.exit(code);
  }
}
