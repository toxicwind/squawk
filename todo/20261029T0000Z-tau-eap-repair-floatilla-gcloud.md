# TODO — EAP repair lane: Flotilla (Pixel browser) + gcloud combo

- status: NOT STARTED
- author: tau (architect directive 2026-10-28)
- unique-id: tau-eap-repair-floatilla-gcloud

For GEMINI_EAP_KEY_0-6 repair (401/402 walls, x-goog-user-project quota-project):
1. gcloud: enumerate project state — `gcloud projects list`, billing + IAM + enabled APIs for the EAP project; verify each key's restrictions.
2. Flotilla MCP (:25245): drive the Pixel browser headlessly for anything needing interactive Google login (console approvals, project selection, re-auth) — phone is the credential SSOT (directive-resolution doctrine).
3. Combo: gcloud verifies programmatic state; Flotilla clicks through what APIs can't.
4. After repair: re-stamp any regenerated keys into the keyring via secretsmith set (never plaintext).
