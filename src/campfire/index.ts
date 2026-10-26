// 🔥 Campfire — merged into squawk. Entry point.
// Wires watcher → brain → poster.
// Event-driven: wakes on fleet events, sweeps on a heartbeat.
// Runs as a squawk sub-daemon: `bun src/campfire/index.ts [--dry-run]`

import { Brain } from "./brain";
import { watchLive, backfill } from "./watcher";
import { flushSpool } from "./poster";
import { logger } from "./logger";

const dryRun = process.argv.includes("--dry-run");
const brain = new Brain({ dryRun });

logger.info("starting", { dry_run: dryRun });

async function main(): Promise<void> {
  // Flush any spooled messages from a previous outage.
  if (!dryRun) {
    const delivered = await flushSpool();
    if (delivered > 0) logger.info("spool flushed", { delivered });
  }

  // Backfill recent history so the brain knows the room.
  logger.info("backfilling", { n: 50 });
  await backfill(50, (msg) => brain.onMessage(msg));
  logger.info("backfill done, watching live");

  // Heartbeat sweep: nudges, check-ins, connections, parked questions.
  // This is the ONE timer — it doesn't poll for new data, it only
  // evaluates time-based conditions (silence thresholds, nudge ages)
  // on state the event-driven watcher already maintains.
  const sweepInterval = setInterval(() => {
    brain.sweep().catch((e) => logger.error("sweep error", { error: String(e).slice(0, 200) }));
  }, 60 * 1000);

  // Watch live. This never returns (restarts internally on failure).
  await watchLive(
    (msg) => brain.onMessage(msg),
    (err) => logger.error("watcher", { error: err })
  );

  clearInterval(sweepInterval); // unreachable, but honest
}

main().catch((e) => {
  logger.error("fatal", { error: String(e).slice(0, 200) });
  process.exit(1);
});
