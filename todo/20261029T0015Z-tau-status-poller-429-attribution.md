# TODO — status poller + 429 attribution (tau 2026-10-28)

- status: NOT STARTED
- author: tau (kryptos/kryptos-quota session)
- unique-id: tau-status-poller-429-attribution

1. **status.freeinference.org poller -> fleet health feed** — poll the status page, publish to squawk /v1/rooms/fleet.
2. **429-vs-quota attribution** — distinguish local Thresher shed (retry-after) from provider exhaustion (402/403 strike). Log lane in keypool audit.
3. **Quota email draft** (USER-GATED — never send without architect): admin@freeinference.org, cite role:pro $160/day, d55dab6, ask for agent-loop headroom. Draft at /home/toxic/pens/geode/products/mimetite/docs/freeinference/quota-email-DRAFT.md.
