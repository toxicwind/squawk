// 🔥 Campfire — posting (merged into squawk).
// Posts directly to the fleet bus (file-based squawk channels).

import { logger } from "./logger";

const SENDER = process.env.SQUAWK_SENDER || "campfire (ember's pack)";
const SQUAWK_ROOT = process.env.SQUAWK_ROOT || process.env.HOME + "/.squawk-bus/squawk-root";
const SPOOL_DIR = process.env.HOME + "/.campfire/spool";

export interface PostResult {
  ok: boolean;
  via: "fleet-bus" | "spooled" | "none";
  detail: string;
}

/** List .msg files from the spool directory. */
async function listSpoolFiles(): Promise<string[]> {
  const result = await $`ls -1 "${SPOOL_DIR}"/*.msg 2>/dev/null`.quiet().nothrow();
  if (result.exitCode !== 0) return [];
  return result.stdout.trim().split("\n").filter(Boolean);
}

/**
 * Post a message to a squawk channel directly on the fleet bus.
 */
export async function post(channel: string, message: string): Promise<PostResult> {
  const thinkMs = 2000 + Math.random() * 4000;
  await Bun.sleep(thinkMs);

  const channelDir = `${SQUAWK_ROOT}/${channel}`;

  try {
    // Ensure channel directory exists.
    await Bun.spawn(["mkdir", "-p", channelDir]).exited;

    const ts = Date.now();
    const seq = ts.toString();
    const slug = SENDER.toLowerCase().replace(/\s+/g, "-");
    const filename = `${seq}-${slug}-fleet.md`;
    const filepath = `${channelDir}/${filename}`;

    const mdt = new Date().toLocaleString("en-US", { timeZone: "America/Denver" });
    const content = `[${seq}] ${SENDER} @ ${mdt}: fleet\n${message}\n`;

    await Bun.write(filepath, content);
    return { ok: true, via: "fleet-bus", detail: `posted to ${channel}/${filename}` };
  } catch (e) {
    // Spool locally for later delivery.
    try {
      await Bun.spawn(["mkdir", "-p", SPOOL_DIR]).exited;
      const ts = Date.now();
      const file = `${SPOOL_DIR}/${ts}-fleet.msg`;
      const content = `sender: ${SENDER}\nchannel: ${channel}\nts: ${ts}\n\n${message}\n`;
      await Bun.write(file, content);
      return { ok: false, via: "spooled", detail: `spooled to ${file}` };
    } catch (spoolErr) {
      return { ok: false, via: "none", detail: `post failed: ${String(e).slice(0, 200)}` };
    }
  }
}

/** Flush the spool — deliver anything that failed earlier. */
export async function flushSpool(): Promise<number> {
  try {
    const files = await listSpoolFiles();
    let delivered = 0;
    for (const file of files) {
      const content = await Bun.file(file).text();
      const channelMatch = content.match(/^channel: (.+)$/m);
      const msgMatch = content.match(/\n\n([\s\S]+)$/);
      if (!channelMatch || !msgMatch) continue;
      const result = await post(channelMatch[1], msgMatch[1].trim());
      if (result.ok && result.via !== "spooled") {
        await Bun.spawn(["rm", file]).exited;
        delivered++;
      }
    }
    return delivered;
  } catch {
    return 0;
  }
}
