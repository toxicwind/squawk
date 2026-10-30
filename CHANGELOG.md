# CHANGELOG

<!-- version list -->

## v0.17.2 (2026-10-30)

### Bug Fixes

- **squawk**: Resolve TOKEN_FILE to ~/.config/estate-chat-token default
  ([`5ea99f7`](https://github.com/toxicwind/squawk/commit/5ea99f7e37e96d291fd7e22a4f9e4d3db963f945))


## v0.17.1 (2026-10-29)

### Bug Fixes

- Squawk-ui ghost-path SQUAWK_DIR -> pens (lease), full LSP/typecheck green (22 diagnostics),
  fleet-feed dead-stub removal, tsconfig bun-types
  ([`f974b36`](https://github.com/toxicwind/squawk/commit/f974b36989197045c33e62e27903c47b3318094f))


## v0.17.0 (2026-10-28)

### Chores

- Fold tree WIP into main (rule 1b)
  ([`2b567be`](https://github.com/toxicwind/squawk/commit/2b567becff0b92ae69a1591dc8f145e37377ce68))

### Features

- **join**: Fleet-join -> rig SSOT (~/.rig/agents, RIG_API, rig-lane); openfang home retired
  ([`43b2f12`](https://github.com/toxicwind/squawk/commit/43b2f1225e36e0e559edba06dc2c9844a9597e4b))


## v0.16.0 (2026-10-28)

### Features

- **squawk**: A2a roster surface in consolidatedState, Bun.write codemod, and Anomaly 35 test fix
  ([`f5060fd`](https://github.com/toxicwind/squawk/commit/f5060fd5d39f9935907c2984a7d1a66c5827ee08))


## v0.15.0 (2026-10-28)

### Chores

- **todo**: Board index churn + block-status mirrors from live roundtrip
  ([`7f42370`](https://github.com/toxicwind/squawk/commit/7f423701609238fe9b22c9a6a1c006c3a45887d8))

### Features

- **todo**: Always-resolve resolver (loud candidates, best-of open-first) + rich done
  (by/when/evidence) + first-class block endpoint + blocked rank bucket
  ([`6074084`](https://github.com/toxicwind/squawk/commit/607408435ac3227a09c2336d945d43fdb0999262))


## v0.14.0 (2026-10-27)

### Features

- **squawk**: Add todo update endpoint + mark freeinference auto fallback IN PROGRESS
  ([`ac3d0a0`](https://github.com/toxicwind/squawk/commit/ac3d0a080f0876b5eee122eb8ef3756629b7092e))


## v0.13.0 (2026-10-27)

### Documentation

- **todo**: Append kappa model-switching gaps to pens-ui todo
  ([`0ed0d33`](https://github.com/toxicwind/squawk/commit/0ed0d336044a8d6d982b2b0eb60d591b92a70cae))

### Features

- **todo**: Wire /v1/todo routes + todo board module; append kappa model-switching gaps
  ([`aec8334`](https://github.com/toxicwind/squawk/commit/aec833437b447b9eab8b3a0bb8245e7dd7039b90))


## v0.12.0 (2026-10-27)

### Chores

- **todo**: Tau session worklog — a2a DM tools shipped, handoff list for kappa
  ([`3a30d38`](https://github.com/toxicwind/squawk/commit/3a30d384c8d288b5f53d97aa6c198ffdd6278697))

### Features

- **todo**: First-class fleet todo board — /v1/todo API, TODO.md auto-index, pens-ui urgent todo
  handoff
  ([`03933ab`](https://github.com/toxicwind/squawk/commit/03933ab4c8bd6cb0040a7a1027cb94fbd3d98250))


## v0.11.0 (2026-10-27)

### Features

- **mcp**: Expose send_targeted/read_targeted DM tools
  ([`b7870dd`](https://github.com/toxicwind/squawk/commit/b7870ddcff7a931199aa6cbd941b4fcecd6d3b5c))


## v0.10.3 (2026-10-27)


## v0.10.2 (2026-10-27)

### Bug Fixes

- **squawk**: Resolve merge conflict markers in plugin.json (v0.10.1) + CHANGELOG (both version
  histories preserved)
  ([`e65029c`](https://github.com/toxicwind/squawk/commit/e65029c60cd4f2814c84d578d28de4587ed26b45))

- **squawk**: Resolve pyproject.toml conflict marker (v0.10.1)
  ([`6cf0801`](https://github.com/toxicwind/squawk/commit/6cf08019949cfb71eae7f46107e0f3113aee2438))

### Chores

- **squawk**: Restore local WIP after upstream v0.10.1 merge
  ([`57acfb4`](https://github.com/toxicwind/squawk/commit/57acfb4228c116504a63194dec32b3417b2325e3))


## v0.10.1 (2026-10-26)

### Bug Fixes

- Ruff clean lint-and-smoke (30 errors)
  ([`1281a15`](https://github.com/toxicwind/squawk/commit/1281a155e5bf9c41414447fb2ec46a403bd6e397))


## v0.10.0 (2026-10-26)


## v0.9.2 (2026-10-23)

### Bug Fixes

- Update feed test for deliberate no-truncation behavior
  ([`c08d265`](https://github.com/toxicwind/squawk/commit/c08d2651ac3dfa4799eaedc79d537b05c345fe3f))


## v0.9.1 (2026-10-23)

### Bug Fixes

- **ci**: Resolve ruff F841 unused vars in oracle/bin/bidder.py
  ([`49f9a02`](https://github.com/toxicwind/squawk/commit/49f9a02270df5bf4300885b35c488aa88f793b01))


## v0.9.0 (2026-10-23)

### Features

- **oracle**: Bidder.py empty-response fix + SCCA consolidation, bid-finch routes, pitchfork.d
  cleanup
  ([`d59d426`](https://github.com/toxicwind/squawk/commit/d59d426b75525f5aadf16d0d09b4eb46c013e3e5))


## v0.8.1 (2026-10-03)

### Bug Fixes

- Squash sequence allocation and test suite green across squawk
  ([`ce16e84`](https://github.com/toxicwind/squawk/commit/ce16e84426ee05191b473a95b4a9b53cd94dc6a2))

### Documentation

- **readme**: Maximal README pass per readme-maximal skill
  ([`054aea2`](https://github.com/toxicwind/squawk/commit/054aea2107bbc3939fc473f76a4ab7badd11f3af))


## v0.8.0 (2026-09-15)

### Chores

- Token-scrub gitignore protection (2026-09-14)
  ([`9ac084f`](https://github.com/toxicwind/squawk/commit/9ac084f77034cc53b251293ef91ad3dfebfd05ea))

### Documentation

- **readme**: Aesthetic, accuracy-checked rewrite of main + relay READMEs
  ([`cfb4de2`](https://github.com/toxicwind/squawk/commit/cfb4de2433134578c8797116de30f836468dbee5))

- **relay**: Commit divergent ws draft, marked SUPERSEDED in TRANSPORT_STATUS.md
  ([`48d8d85`](https://github.com/toxicwind/squawk/commit/48d8d85f7bd6db9b9396729d6860e64dade2f1ed))

- **relay**: TRANSPORT_STATUS.md — mark live/retired/divergent Squawk transports
  ([`2ddb32e`](https://github.com/toxicwind/squawk/commit/2ddb32e7c2881f186e79a7fc00aa431009d2e173))

### Features

- **chat**: First-class papers command (arXiv/alphaXiv legs) + ruff 0.15.7 facade fix
  ([`54b297c`](https://github.com/toxicwind/squawk/commit/54b297c17dc93a9776ce119dffb42d9d14cefad7))


## v0.7.4 (2026-09-14)

### Bug Fixes

- **ci**: Mint fleet identity keys at import in test_squawk_feed (FLEET_KEYS_DIR override poisoned
  whole suite -> 74 errors)
  ([`7598162`](https://github.com/toxicwind/squawk/commit/75981622893c029d0e0062201f7cb0cb4cb4a7c5))


## v0.7.3 (2026-09-14)

### Bug Fixes

- **ci**: Ruff E741/E402 in smoke_relay.py + tests/test_squawk_feed.py (fat-feed merge fallout)
  ([`3d5c295`](https://github.com/toxicwind/squawk/commit/3d5c2957727ea7bd7f34284324c598eb01dfa1dc))


## v0.7.2 (2026-09-14)

### Bug Fixes

- **deps**: Update n24q02m/better-semantic-release action to v1.6.2
  ([#199](https://github.com/n24q02m/agent-chat-plugin/pull/199),
  [`0b68ca4`](https://github.com/n24q02m/agent-chat-plugin/commit/0b68ca49e4b70716a28e9cfe03d99ad6e9e94a33))

### Chores

- **release**: Fix stale two-branch comment (single-main lane)
  ([`4622c41`](https://github.com/n24q02m/agent-chat-plugin/commit/4622c41b209f86e119c4eec97427cebfc17becc6))

- **release**: Single-main release lane (staging branch retired)
  ([`92b5304`](https://github.com/n24q02m/agent-chat-plugin/commit/92b5304687396375725f91e71ee18ac35a047198))


## v0.7.1 (2026-09-12)

### Bug Fixes

- **deps**: Update astral-sh/setup-uv action to v10.1.0
  ([#192](https://github.com/n24q02m/agent-chat-plugin/pull/192),
  [`af685f4`](https://github.com/n24q02m/agent-chat-plugin/commit/af685f4d235f900aa2decda2237210e3fdc26774))

- **deps**: Update ruff to v0.16.7 ([#193](https://github.com/n24q02m/agent-chat-plugin/pull/193),
  [`19bc27b`](https://github.com/n24q02m/agent-chat-plugin/commit/19bc27bff1476c29d169222ff8b4276b877216bf))

### Chores

- Pin BSR action to v1.6.1 stable (6e688489)
  ([#194](https://github.com/n24q02m/agent-chat-plugin/pull/194),
  [`a035ea7`](https://github.com/n24q02m/agent-chat-plugin/commit/a035ea795e7014de57c160958f64ad42376c868f))

- **rulesets**: Align IaC with repo-bootstrap template
  ([`6de2ba3`](https://github.com/n24q02m/agent-chat-plugin/commit/6de2ba3c7f3dae0636c85a9bb6ae75a863f8011f))


## v0.7.0 (2026-09-11)

### Bug Fixes

- Remove duplicate metavar kwarg from event subparser (breaks py_compile)
  ([`70eb853`](https://github.com/n24q02m/agent-chat-plugin/commit/70eb85325b5e250a72c681c870d7fffe4fdb2a45))

- **deps**: Update github/codeql-action action to v4.38.0
  ([#188](https://github.com/n24q02m/agent-chat-plugin/pull/188),
  [`235ea2e`](https://github.com/n24q02m/agent-chat-plugin/commit/235ea2e5f1ad1a7e87529c64f8b81e5a8909a1b4))

### Continuous Integration

- Fix job-level if: env context invalid in jobs.<id>.if (startup failure)
  ([`e0fbd15`](https://github.com/n24q02m/agent-chat-plugin/commit/e0fbd154efab9185279cd3baf6af6e2e1c3815d5))

- Wire unified merge=release ladder (push staging=beta, main=stable)
  ([`7cf97e5`](https://github.com/n24q02m/agent-chat-plugin/commit/7cf97e5465ea9174e890e0066d795c94111f3d03))


## v0.6.1-beta.4 (2026-09-08)

### Bug Fixes

- Keep skill references portable
  ([`b9e0136`](https://github.com/n24q02m/agent-chat-plugin/commit/b9e0136d83081b80322be67a947545effee6b0b1))


## v0.6.1-beta.3 (2026-09-08)

### Bug Fixes

- Bound Agent Chat context surfaces
  ([`d9dc92a`](https://github.com/n24q02m/agent-chat-plugin/commit/d9dc92aa54c1a97b30ad505783902498ef93dc87))


## v0.6.1-beta.2 (2026-09-05)

### Bug Fixes

- Restore semantic release changelog updates
  ([#175](https://github.com/n24q02m/agent-chat-plugin/pull/175),
  [`ba98d95`](https://github.com/n24q02m/agent-chat-plugin/commit/ba98d9519f7dca21ff72b2a7c9ed7a748cc656f3))
