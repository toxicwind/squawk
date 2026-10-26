// squawk/bun/mcp — MCP tool surface for the merged squawk chat.
// Shared by both the stdio MCP adapter and the Streamable HTTP /v1/mcp route.

import type { Store } from "../store/index.ts";

export interface McpTool {
  name: string;
  description: string;
  inputSchema: Record<string, any>;
}

export const MCP_TOOLS: McpTool[] = [
  {
    name: "join",
    description: "Join the fleet chat plane as an agent. summoner is required.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string" },
        chat_id: { type: "string" },
        agent_id: { type: "string" },
        host_machine_id: { type: "string" },
        hostname: { type: "string" },
        hatchling_id: { type: "string" },
        summoner: { type: "string" },
        surface: { type: "string" },
        activity: { type: "string" },
      },
      required: ["name", "summoner"],
      additionalProperties: false,
    },
  },
  {
    name: "heartbeat",
    description: "Presence heartbeat with current activity and counters.",
    inputSchema: {
      type: "object",
      properties: {
        agent_id: { type: "string" },
        activity: { type: "string" },
        counters: { type: "object" },
      },
      required: ["agent_id"],
      additionalProperties: false,
    },
  },
  {
    name: "post_message",
    description: "Post a message to a room.",
    inputSchema: {
      type: "object",
      properties: {
        room_id: { type: "string" },
        from_agent: { type: "string" },
        body: { type: "string" },
        kind: { type: "string" },
      },
      required: ["room_id", "from_agent", "body"],
      additionalProperties: false,
    },
  },
  {
    name: "read_messages",
    description: "Replay room history.",
    inputSchema: {
      type: "object",
      properties: {
        room_id: { type: "string" },
        since_seq: { type: "number" },
        limit: { type: "number" },
      },
      required: ["room_id"],
      additionalProperties: false,
    },
  },
  {
    name: "list_presence",
    description: "Who is live right now.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "list_rooms",
    description: "List rooms.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "get_state",
    description:
      "Consolidated live picture: presence, activity, decision log, rooms. Read this instead of docs.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
];

export function mcpCallTool(
  store: Store,
  name: string,
  args: Record<string, any>,
): any {
  switch (name) {
    case "join":
      return store.join(args || {});
    case "heartbeat":
      return store.heartbeat(args || {});
    case "post_message":
      return store.postMessage(String(args?.room_id || "fleet"), args || {});
    case "read_messages":
      return store.readMessages(
        String(args?.room_id || "fleet"),
        Number(args?.since_seq || 0),
        Number(args?.limit || 100),
      );
    case "list_presence":
      return store.liveAgents();
    case "list_rooms":
      return store.rooms();
    case "get_state":
      return store.consolidatedState("squawk", 0);
    default:
      throw new Error("unknown tool: " + String(name));
  }
}
