# TODO — Yote Telegram-as-a-Service (TaaS) + botfather autonomy

- status: NOT STARTED
- author: tau (design per architect 2026-10-28)
- unique-id: TAU-20261028-taas-design
- created: 2026-10-28

Yote telegram-as-a-service (TaaS): ANY rig/agent can create its own Telegram bot AUTONOMOUSLY.
Flow (proven live by inbound-probe): caller asks coyote/yote -> @puppertrix real-user MTProto session opens BotFather -> /newbot with rig's name -> collect token -> store in secretsmith keyring (label TG_BOT_TOKEN_<RIG>, service=taas) -> return token to caller.
Surfaces: (1) API on yote (openfang/coyote route) POST /telegram/newbot {name, description} -> {token, bot_username};
(2) MCP tool telegram_newbot via doorbell/thresher gateway so ANY rig (hephaistos, geode, tack...) calls it as a tool.
First customer: hephaistos (smoke-test the whole flow). Then rigs self-serve telegram presence forever.
