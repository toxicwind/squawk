// 🔥 Campfire — logger: herd-level structured logging.
// Follows the minimum bar (docs/LOGGING.md):
//   [campfire] [LEVEL] event key=value ...
// Levels: DEBUG/INFO/WARN/ERROR, runtime-configurable via LOG_LEVEL.

type Level = "DEBUG" | "INFO" | "WARN" | "ERROR";

const ORDER: Record<Level, number> = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };

function currentLevel(): Level {
  const raw = (process.env.LOG_LEVEL || "INFO").toUpperCase();
  if (raw === "DEBUG" || raw === "INFO" || raw === "WARN" || raw === "ERROR") return raw;
  return "INFO";
}

function log(level: Level, msg: string, fields: Record<string, string | number | boolean> = {}): void {
  if (ORDER[level] < ORDER[currentLevel()]) return;
  const fieldStr = Object.entries(fields)
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
  const line = fieldStr
    ? `[campfire] [${level}] ${msg} ${fieldStr}`
    : `[campfire] [${level}] ${msg}`;
  if (level === "ERROR" || level === "WARN") {
    console.error(line);
  } else {
    console.log(line);
  }
}

export const logger = {
  debug: (msg: string, fields?: Record<string, string | number | boolean>) => log("DEBUG", msg, fields),
  info: (msg: string, fields?: Record<string, string | number | boolean>) => log("INFO", msg, fields),
  warn: (msg: string, fields?: Record<string, string | number | boolean>) => log("WARN", msg, fields),
  error: (msg: string, fields?: Record<string, string | number | boolean>) => log("ERROR", msg, fields),
};
