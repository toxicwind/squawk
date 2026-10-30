---
agent: tau
status: pending
---

# LG fleet maximal — 8 subgoals (architect order 2026-10-29)

Priority: HIGH. Context: architect watches Drew Carey live on a working
nuvio fork; the failed LG chat was root-caused (stale squawk MCP path,
fixed + pushed barn 9888180).

## Subgoals
1. **LG-1 fork lineage audit** — which fork serves live TV (Drew Carey
   proof): probe NuvioTVSmart (space.nuvio.webos 1.2.10) vs nuvio-webos
   AETHER (com.toxicwind.streamers 1.0.0) vs NuvioTVWebOS (strem lineage);
   identify working source config + addon sources.
2. **LG-2 IPK canonical rebuild** — com.toxicwind.streamers ipk (retire
   stale io.strem.tv name in dist), bump version, package via ares-webos.
3. **LG-3 bridge** — re-establish flotilla/adb to 10.0.0.77:35913 +
   ares-shell LAN reach to the TV; screenshot proof.
4. **LG-4 chat root** — locate the original failed LG chat event
   (estate-chat/squawk logs + nuvio addon chat lane), fix forward, announce.
5. **LG-5 playback contract tests** — hlsjs-p2p + docchi on the working
   fork; Tizen 4 P2P runtime gate; stream decode proof.
6. **LG-6 TV vision+typo lanes** — vk_describe the live TV screenshot via
   vision-kit; typo-kit decode-max on remote command text.
7. **LG-7 orphan sweep** — estate-orphans lg-webos → products/ or archive
   per pairs map; ghost refs killed; manifest clean.
8. **LG-8 ship + announce** — install AETHER on the LG, launch, screenshot
   proof to fleet, close the squawk todo.

## Equity
Additive-only. Never remove/disable a daemon without explicit order.
Archive artifacts to ~/sovereign/scratch-archive/. Push every repo touched.
