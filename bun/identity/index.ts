// squawk/bun/identity — the four-namespace identity model (2026-09-18 verdict).
// The four namespaces are stored as SEPARATE fields and never collapsed into
// a single UUID:
//   host_machine_id  — host identity (machine-id; hostname for readability)
//   chat_id          — conversation/lane identity
//   agent_id         — agent/runtime incarnation (JARVIS_SESSION_ID or agent UUID)
//   hatchling_id     — shared parent/fleet identity (NOT unique per child)

export interface Identity {
  agent_id: string;
  name: string;
  chat_id: string | null;
  host_machine_id: string | null;
  hostname: string | null;
  hatchling_id: string | null;
  summoner: string;
  surface: string | null;
  frame_id: string | null;
}

export type IdentityInput = Partial<Identity> & {
  name: string;
  summoner: string;
};

export function nowISO(): string {
  return new Date().toISOString();
}

export function randomHex(n: number): string {
  return [...crypto.getRandomValues(new Uint8Array(n))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, n);
}

/** Validate a legal identity record. Returns a normalized Identity or throws. */
export function normalizeIdentity(p: IdentityInput): Identity {
  const name = String(p.name || "").trim();
  const summoner = String(p.summoner || "").trim();
  if (!name)
    throw Object.assign(new Error("name is required"), { status: 400 });
  if (!summoner)
    throw Object.assign(
      new Error("summoner is required (no anonymous joins)"),
      {
        status: 400,
      },
    );
  const agent_id = p.agent_id
    ? String(p.agent_id)
    : `sc-${Date.now().toString(36)}-${randomHex(6)}`;
  return {
    agent_id,
    name,
    chat_id: p.chat_id ? String(p.chat_id).slice(0, 80) : null,
    host_machine_id: p.host_machine_id ? String(p.host_machine_id) : null,
    hostname: p.hostname ? String(p.hostname) : null,
    hatchling_id: p.hatchling_id ? String(p.hatchling_id) : null,
    summoner,
    surface: p.surface ? String(p.surface).slice(0, 64) : null,
    frame_id: p.frame_id ? String(p.frame_id) : null,
  };
}
