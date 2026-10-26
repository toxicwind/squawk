// squawk/bun/test/bridge.test.ts
import { beforeAll, afterAll, describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import {
  parseFrontmatter,
  loadState,
  saveState,
  activeBoard,
  boardRows,
  rowToFile,
  chatFiles,
  insertIntoBoard,
  runSync,
  BOARD_SOURCE,
} from "../bridge/index.ts";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let dir: string;
let chan: string;
let dbPath: string;
let db: Database;

function makeBoard(root = "root-session-x") {
  db.exec(
    "CREATE TABLE IF NOT EXISTS kappa_board (root_session_id TEXT PRIMARY KEY, next_seq INTEGER, message_count INTEGER, message_bytes INTEGER, time_updated INTEGER)",
  );
  db.query("INSERT OR IGNORE INTO kappa_board VALUES (?,0,0,0,?)").run(
    root,
    Date.now(),
  );
  return root;
}

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "squawk-bridge-"));
  chan = `${dir}/kappa_board`;
  dbPath = `${dir}/kappa.db`;
  db = new Database(dbPath, { create: true });
  makeBoard();
  // message table for boardRows / insertIntoBoard
  db.exec(
    "CREATE TABLE IF NOT EXISTS kappa_board_message (id TEXT PRIMARY KEY, board_root_session_id TEXT, seq INTEGER, time_created INTEGER, sender_session_id TEXT, recipient TEXT, type TEXT, body TEXT, reply_to TEXT, source_message_id TEXT, source_call_id TEXT)",
  );
});

afterAll(() => {
  db.close();
  rmSync(dir, { recursive: true, force: true });
});

describe("frontmatter parsing", () => {
  test("parses full frontmatter + body", () => {
    const p = `${chan}/5-wren-board.md`;
    Bun.write(
      p,
      "---\nseq: 5\nfrom: wren\nto: all\nchannel: kappa_board\nts: 2024-01-01\nstatus: discussion\nsource: kappa_board\n---\nhello body\n",
    );
    const { seq, fm, body } = parseFrontmatter(p, "5-wren-board.md");
    expect(seq).toBe(5);
    expect(fm.from).toBe("wren");
    expect(fm.source).toBe(BOARD_SOURCE);
    expect(body).toBe("hello body");
  });

  test("falls back to filename seq without frontmatter", () => {
    const p = `${chan}/9-nofm.md`;
    Bun.write(p, "no frontmatter here");
    const { seq, body } = parseFrontmatter(p, "9-nofm.md");
    expect(seq).toBe(9);
    expect(body).toContain("no frontmatter");
  });
});

describe("state persistence", () => {
  test("saveState + loadState round-trip", () => {
    saveState(chan, { board_chat_cursor: 42 });
    const s = loadState(chan);
    expect(s.board_chat_cursor).toBe(42);
  });

  test("loadState returns empty for missing", () => {
    const empty = loadState(`${dir}/nowhere`);
    expect(Object.keys(empty)).toHaveLength(0);
  });
});

describe("board queries", () => {
  test("activeBoard picks newest board", () => {
    makeBoard("root-session-y");
    db.query(
      "UPDATE kappa_board SET time_updated = ? WHERE root_session_id = 'root-session-y'",
    ).run(Date.now() + 60_000);
    const root = activeBoard(dbPath);
    expect(root).toBe("root-session-y");
  });

  test("insertIntoBoard writes row and bumps board", () => {
    const before = (
      db.query("SELECT COUNT(*) AS c FROM kappa_board_message").get() as any
    ).c;
    insertIntoBoard(dbPath, "root-session-x", 1, "kappa_board", "posted text");
    const after = (
      db.query("SELECT COUNT(*) AS c FROM kappa_board_message").get() as any
    ).c;
    expect(after).toBe(before + 1);
    const board = db
      .query("SELECT message_count FROM kappa_board WHERE root_session_id=?")
      .get("root-session-x") as any;
    expect(board.message_count).toBeGreaterThan(0);
  });

  test("boardRows returns rows above cursor", () => {
    const rows = boardRows(dbPath, 0, null);
    expect(rows.length).toBeGreaterThan(0);
    const noneNew = boardRows(dbPath, 10_000, null);
    expect(noneNew.length).toBe(0);
  });
});

describe("row -> file", () => {
  test("rowToFile writes a board-sourced md file", () => {
    const f = rowToFile(chan, {
      seq: 77,
      time_created: 1700000000000,
      sender_session_id: "Echo",
      recipient: "all",
      type: "message",
      body: "board body",
      id: "id-1",
    });
    expect(existsSync(f)).toBe(true);
    const { fm } = parseFrontmatter(f, f.split("/").pop()!);
    expect(fm.source).toBe(BOARD_SOURCE);
  });
});

describe("single sync pass", () => {
  test("runSync is idempotent and reversible", () => {
    const s1 = runSync({
      root: dir,
      db: dbPath,
      channel: "kappa_board",
      rootSession: "root-session-x",
    });
    expect(s1.boardToChat).toBeGreaterThanOrEqual(0);
    expect(s1.chatToBoard).toBeGreaterThanOrEqual(0);
    expect(s1.root).toBe("root-session-x");
    const state1 = loadState(chan) as any;
    const s3 = runSync({
      root: dir,
      db: dbPath,
      channel: "kappa_board",
      rootSession: "root-session-x",
    });
    const state3 = loadState(chan) as any;
    expect(Number(state3.board_chat_cursor ?? 0)).toBeGreaterThanOrEqual(
      Number(state1.board_chat_cursor ?? 0),
    );
    expect(Number(state3.chat_board_cursor ?? 0)).toBeGreaterThanOrEqual(
      Number(state1.chat_board_cursor ?? 0),
    );
  });

  test("chatFiles excludes board-sourced files", () => {
    const files = chatFiles(chan);
    for (const f of files) {
      const { fm } = parseFrontmatter(f.path, f.path.split("/").pop()!);
      expect(fm.source).not.toBe(BOARD_SOURCE);
    }
  });
});
