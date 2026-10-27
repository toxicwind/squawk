// squawk/todo — first-class fleet todo board.
//
// Folder-backed (todo/*.md is the system of record) + JSON index (TODO.md)
// so any agent or human can read the queue without the daemon. The daemon
// exposes /v1/todo endpoints and MCP tools (todo_list, todo_add, todo_done)
// for first-class access. Single-writer semantics: last write wins per file,
// status parsed from the `status:` header line.

import { readdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

export interface TodoDeps {
  todoDir: string;
}

export interface TodoItem {
  file: string;
  title: string;
  author: string;
  status: string;
  created: string;
  urgency: "normal" | "urgent";
}

const STATUS_RE = /^[-*]?\s*status:\s*(.+)$/im;
const AUTHOR_RE = /^[-*]?\s*author:\s*(.+)$/im;
const CREATED_RE = /^[-*]?\s*created:\s*(.+)$/im;
const URGENT_RE = /most urgent|urgent/i;

export function parseTodo(file: string, raw: string): TodoItem {
  const title = (raw.match(/^#\s*TODO\s*—?\s*(.+)$/im)?.[1] ?? file.replace(/\.md$/, "")).trim();
  const status = (raw.match(STATUS_RE)?.[1] ?? "unknown").trim();
  const author = (raw.match(AUTHOR_RE)?.[1] ?? "unknown").trim();
  const created = (raw.match(CREATED_RE)?.[1] ?? "").trim();
  return {
    file,
    title: title.slice(0, 120),
    author: author.slice(0, 60),
    status: status.slice(0, 80),
    created,
    urgency: URGENT_RE.test(status) || URGENT_RE.test(title) ? "urgent" : "normal",
  };
}

export function listTodos(deps: TodoDeps): TodoItem[] {
  if (!existsSync(deps.todoDir)) return [];
  const items: TodoItem[] = [];
  for (const f of readdirSync(deps.todoDir)) {
    if (!f.endsWith(".md") || f === "TODO.md") continue;
    try {
      items.push(parseTodo(f, readFileSync(join(deps.todoDir, f), "utf8")));
    } catch {
      /* unreadable file skipped */
    }
  }
  // Urgent first, then NOT STARTED before partial before done, then newest.
  const rank = (s: string) =>
    /not started/i.test(s) ? 0 : /in progress|partial/i.test(s) ? 1 : /done|complete/i.test(s) ? 2 : 1;
  return items.sort(
    (a, b) =>
      Number(b.urgency === "urgent") - Number(a.urgency === "urgent") ||
      rank(a.status) - rank(b.status) ||
      b.created.localeCompare(a.created),
  );
}

export function regenerateIndex(deps: TodoDeps): string {
  const items = listTodos(deps);
  const lines = [
    "# FLEET TODO — INDEX (auto-generated; edit the linked files, not this)",
    "",
    `Updated: ${new Date().toISOString()}`,
    "",
    "| Urgency | Status | Author | Todo | File |",
    "|---|---|---|---|---|",
    ...items.map(
      (t) =>
        `| ${t.urgency === "urgent" ? "🔥 URGENT" : ""} | ${t.status} | ${t.author} | ${t.title} | [${t.file}](${t.file}) |`,
    ),
    "",
    "Protocol: one md per arc — `todo/<YYYYMMDDTHHMMZ>-<agent>-<slug>.md`.",
    "Read via daemon: `GET /v1/todo` · MCP tools: todo_list / todo_add / todo_done.",
    "",
  ];
  const out = lines.join("\n");
  writeFileSync(join(deps.todoDir, "TODO.md"), out);
  return out;
}

// --- wire-up helpers (called from routes) ---

export function handleList(deps: TodoDeps) {
  return { ok: true, todos: listTodos(deps) };
}

export function handleAdd(deps: TodoDeps, body: { slug: string; author: string; content: string }) {
  const ts = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "Z");
  const authorSlug = (body.author || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const file = `${ts}-${authorSlug}-${(body.slug || "untitled").toLowerCase().replace(/[^a-z0-9-]+/g, "-").slice(0, 60)}.md`;
  writeFileSync(join(deps.todoDir, file), body.content);
  regenerateIndex(deps);
  return { ok: true, file };
}

export function handleDone(deps: TodoDeps, file: string) {
  const p = join(deps.todoDir, file);
  if (!existsSync(p)) return { ok: false, error: "no such todo" };
  const raw = readFileSync(p, "utf8");
  if (STATUS_RE.test(raw)) {
    writeFileSync(p, raw.replace(STATUS_RE, (m) => m.replace(/:\s*.*$/, ": DONE (marked by daemon)")));
  } else {
    writeFileSync(p, `${raw}\n- status: DONE (marked by daemon)\n`);
  }
  regenerateIndex(deps);
  return { ok: true, file };
}
