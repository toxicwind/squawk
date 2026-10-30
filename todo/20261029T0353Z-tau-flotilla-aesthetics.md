# Fleet todo: Flotilla — correct to production-grade aesthetics, analyze screenshots via image kit

## Origin
tau followup phase: "Flotilla: correct to production-grade aesthetics, analyze screenshots via image kit".

## Scope
`ranch/android-fleet/flotilla/mcp/server.ts` (telegram-as-a-service / pixel MCP bridge via thresher, port 25245 per ports.env). Aesthetic pass = production-grade UI/surface + screenshot analysis via the image kit (browser-keeper CDP :25233 or fltk fltk.org tooling).

## Status
PENDING — not started in this session. Open questions to route to the architect:
- Which "image kit" screenshots? (browser-keeper profiles at /home/toxic/.browserless/profiles/skopos, or fltk?)
- Is flotilla-aesthetics a UI task or a docs/surface task? Board gives no acceptance criteria.
