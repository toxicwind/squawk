# First green-blue rollout: mimetite catalog build lane

- **Posted by:** tau · 2026-10-28T19:30Z
- **Status:** NOT-STARTED
- **Priority:** medium (docketed via ask 2026-10-28, approved)

Target: `pens/geode/products/mimetite` — catalog SSOT, pure build+test lane,
no live traffic (safest first rollout). Primitive:
`bun pens/geode/products/pseudobrookite/scripts/deploy-green-blue.ts <dir> --build "bun run build" --health <url>`.
Contract: green stays runnable; blue healthchecked BEFORE symlink swap;
rollback = `ln -sfn releases/green-<ts> current`.
