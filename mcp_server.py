#!/usr/bin/env python3
"""squawk-mcp: stdio MCP server wrapping the squawk chat CLI.

Follows the mcp-dropin-guide (R-101..R-301): stdio JSON-RPC 2.0 with
Content-Length framing, dual framing on input, initialize handshake with
protocolVersion 2024-11-05, and tool schemas with descriptions.

Config settings (env vars, overridable by ~/.config/squawk/config.json):
  SQUAWK_ROOT     - chat root dir (default: $AGENT_CHAT_ROOT or ~/agent-chat)
  SQUAWK_CHANNEL  - default channel (default: "general")
  SQUAWK_AGENT    - agent name for posting/reading (default: $USER)

Read-only tools: channels, roster, peek, state, thread, dag, clocks, ops, get_config.
Mutating tools (post, claim, task, event) require confirm: true.
"""
import json
import subprocess
import sys
import os

SERVER_INFO = {"name": "squawk-mcp", "version": "1.1.0"}
CHAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat.py")

# --- Config settings ---
def load_config():
    cfg = {
        "root": os.environ.get("SQUAWK_ROOT", os.environ.get("AGENT_CHAT_ROOT", os.path.expanduser("~/agent-chat"))),
        "channel": os.environ.get("SQUAWK_CHANNEL", "general"),
        "agent": os.environ.get("SQUAWK_AGENT", os.environ.get("USER", "agent")),
    }
    # Optional config file override
    cfg_path = os.environ.get("SQUAWK_CONFIG", os.path.expanduser("~/.config/squawk/config.json"))
    try:
        with open(cfg_path) as f:
            file_cfg = json.load(f)
        cfg.update({k: v for k, v in file_cfg.items() if k in cfg})
    except Exception:
        pass
    return cfg

CONFIG = load_config()
ROOT = CONFIG["root"]
DEFAULT_CHANNEL = CONFIG["channel"]
AGENT = CONFIG["agent"]

TOOLS = [
    {"name": "get_config", "description": "Show the current squawk MCP config settings (root, channel, agent)", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "channels", "description": "List all squawk channels", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "roster", "description": "Show a channel's members", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}}, "required": []}},
    {"name": "peek", "description": "Show last N messages without touching the cursor", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}, "n": {"type": "integer", "description": "Number of messages"}}, "required": []}},
    {"name": "state", "description": "Render or show channel state summary", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}}, "required": []}},
    {"name": "thread", "description": "Show the reply thread from root to a message", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}, "message": {"type": "string", "description": "Message id"}}, "required": ["message"]}},
    {"name": "dag", "description": "Verify the hash-linked message DAG of a channel", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}}, "required": []}},
    {"name": "clocks", "description": "Show per-agent Lamport clocks", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}}, "required": []}},
    {"name": "ops", "description": "Show the commutative op log", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}}, "required": []}},
    {"name": "post", "description": "Post a message to a channel", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}, "body": {"type": "string", "description": "Message body"}, "confirm": {"type": "boolean", "description": "Must be true to post"}}, "required": ["body", "confirm"]}},
    {"name": "claim", "description": "Atomically claim a task marker", "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "description": "Channel name (default: config channel)"}, "task": {"type": "string", "description": "Task id"}, "confirm": {"type": "boolean", "description": "Must be true to claim"}}, "required": ["task", "confirm"]}},
]

TOOL_BY_NAME = {t["name"]: t for t in TOOLS}

def run_chat(args):
    try:
        r = subprocess.run([sys.executable, CHAT, "--root", ROOT] + args, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or r.stderr.strip()
    except Exception as e:
        return str(e)

def handle_call(name, args):
    ch = args.get("channel", DEFAULT_CHANNEL)
    if name == "get_config":
        return json.dumps(CONFIG, indent=2)
    if name == "channels":
        return run_chat(["channels"])
    if name == "roster":
        return run_chat(["roster", ch])
    if name == "peek":
        return run_chat(["peek", ch, "--n", str(args.get("n", 10))])
    if name == "state":
        return run_chat(["state", ch])
    if name == "thread":
        return run_chat(["thread", ch, args.get("message", "")])
    if name == "dag":
        return run_chat(["dag", ch])
    if name == "clocks":
        return run_chat(["clocks", ch])
    if name == "ops":
        return run_chat(["ops", ch])
    if name == "post":
        if not args.get("confirm"):
            return "confirm: true required"
        return run_chat(["post", ch, "--body", args.get("body", "")])
    if name == "claim":
        if not args.get("confirm"):
            return "confirm: true required"
        return run_chat(["claim", ch, args.get("task", "")])
    return "unknown tool"

def send(msg):
    # mcp-go client reads newline-delimited JSON from server stdout (ReadString('\n')).
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def read_msg():
    """Read one Content-Length-framed or newline-delimited JSON-RPC message."""
    line = sys.stdin.buffer.readline().decode("latin1")
    if not line:
        return None
    line = line.rstrip("\r\n")
    if line.startswith("{"):
        return json.loads(line)
    length = 0
    if line.lower().startswith("content-length:"):
        length = int(line.split(":", 1)[1].strip())
    while True:
        line = sys.stdin.buffer.readline().decode("latin1")
        if not line:
            return None
        line = line.rstrip("\r\n")
        if not line:
            break
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    if length:
        return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))
    line = sys.stdin.buffer.readline().decode("latin1")
    return json.loads(line) if line.strip() else None

while True:
    msg = read_msg()
    if msg is None:
        break
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        result = handle_call(name, args)
        send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": result}]}})
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}})
