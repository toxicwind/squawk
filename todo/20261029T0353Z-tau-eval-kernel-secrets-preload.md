# Fleet todo: Eval kernel — auto-load all kryptos/secretsmith secrets into env at boot, zero per-command transport

## Origin
tau kryptos-kernel phase: "Eval kernel: auto-load all kryptos/secretsmith secrets into env at boot, zero per-command transport (race A subprocess bulk vs B in-process D-Bus, decide winner, wire it)".

## Race results (decided)
- Technique A: `secretsmith --json env` → one subprocess bulk dump (295ms, 172 secrets, full label→value pairs). Winner: **fast, reliable, all secrets in one shot**.
- Technique B: in-process D-Bus via `secretstorage`/`dbus-next` → **no session bus** in the eval kernel (`DBUS_SESSION_BUS_ADDRESS` unset); dead.
- Technique C: `secretsmith env --app <name>` → **broken** (0 vars returned — secretsmith env --app bug, anomaly #16/#58 class).

## Wiring (done for current kernel)
- `/home/toxic/.tau/kernel-preload-secrets.py` — `subprocess.run(["secretsmith", "--json", "env"])` → injects into `os.environ` (idempotent; loads secrets not already present). Verified: THRESHER_API_KEY (64 chars) present in python kernel.
- `/home/toxic/.tau/kernel-preload-secrets.js` — `Bun.$ \`secretsmith --json env\`` → injects into `process.env`. Verified: THRESHER_API_KEY present in js kernel (64 chars).
- Zero per-command transport: after boot, every `Bun.$` inherits from process.env — no secretsmith spawn per command.
- Both kernels verified without any per-command secretsmith call.

## Remaining
- Make preload automatic at kernel boot (hook into tau eval kernel startup; currently manual `%load`-equivalent per kernel life). Check `~/.tau/extensions/*` for a boot hook mechanism or a Bun preload entrypoint.
- Note: technique C (`env --app` broken) is a separate secretsmith bug to file if the architect wants it fixed.

## Status
PENDING (wired manually; auto-boot hook not yet found).
