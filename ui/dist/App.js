import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';
import { mdBlock, esc } from "../markdown.js";
import MessageCard from "./MessageCard.js";
import AddChannelDialog from "./AddChannelDialog.js";

var root = $.from_html(`<span class="x" role="button" tabindex="0">×</span>`);
var root_1 = $.from_html(`<div role="tab" tabindex="0"><span> </span> <!></div>`);
var root_2 = $.from_html(`<div class="sys"> </div>`);
var root_3 = $.from_html(`<header><h1>SQUAWK</h1> <span class="transport svelte-n50uah"> </span></header> <div id="tabs" role="tablist"><!> <button id="addTab" title="add channel" aria-label="add channel">+</button></div> <div id="log"><!> <!></div> <div id="composer"><input id="msg" autocomplete="off" aria-label="message"/> <button id="send">send</button></div> <div id="statusbar"><span><span></span> </span> <span> </span> <span> </span></div> <!>`, 1);

export default function App($$anchor, $$props) {
	$.push($$props, true);

	const VALID_NAME = /^[a-z0-9-_]{1,32}$/;

	// --- state (Svelte 5 runes) ---
	let tabs = $.state($.proxy({ fleet: { messages: [], cursor: 0, scrollTop: 0, wsSeq: 0 } }));

	let activeName = $.state("fleet");
	let conn = $.state("reconnecting");
	let latency = $.state(0);
	let sysLines = $.state($.proxy([]));
	let showDlg = $.state(false);
	let draft = $.state("");
	let sending = $.state(false);
	let active = $.derived(() => $.get(tabs)[$.get(activeName)] ?? { messages: [], cursor: 0, scrollTop: 0, wsSeq: 0 });

	let dotClass = $.derived(() => $.get(conn) === "live"
		? "live"
		: $.get(conn) === "degraded" ? "recon" : "recon");

	let connLabel = $.derived(() => $.get(conn) === "live"
		? "live"
		: $.get(conn) === "degraded" ? "degraded — auto-fallback" : "reconnecting…");

	let logEl = $.state(null);
	let ws = null;
	let pollTimer;
	let wsFailTimer;
	let reconTimer;
	let wsFlushTimer;
	let reconnectDelay = 1000;
	let running = true;
	let polling = false;
	let intentionalClose = false;
	let useWs = $.state(false // transport: ws primary, poll fallback (automatic, no user choice)
	);

	// identity key: unifies the poll seq space (file_seq) and the ws gseq space
	// (ws frames carry both seq=gseq and file_seq). Same logical message -> same key.
	// Note: file_seq is 0 (not undefined) for live-tail messages not yet on disk,
	// so use || not ?? — a 0 must fall through to the gseq.
	function keyOf(m) {
		return m.file_seq || m.seq;
	}

	function sysLine(s) {
		$.set(sysLines, [...$.get(sysLines).slice(-19), s], true);
	}

	function ingest(channel, msgs) {
		const t = $.get(tabs)[channel];

		if (!t || !msgs.length) return;

		const seen = new Set(t.messages.map(keyOf));
		const fresh = msgs.filter((m) => !seen.has(keyOf(m)));

		if (!fresh.length) return;

		$.get(tabs)[channel] = {
			...t,
			messages: [...t.messages, ...fresh].sort((a, b) => keyOf(a) - keyOf(b)),
			cursor: Math.max(t.cursor, ...fresh.map(keyOf))
		};
	}

	// normalize a squawk-ws broadcast frame into our Msg shape
	// (server sends {seq, file_seq, channel, sender, ts, sealed, text})
	function normalizeWs(d, fallbackChannel) {
		if (!d || typeof d.seq !== "number") return null;

		return {
			seq: d.seq,
			file_seq: typeof d.file_seq === "number" ? d.file_seq : undefined,
			from: d.sender ?? d.from ?? "?",
			to: d.to ?? "all",
			channel: typeof d.channel === "string" ? d.channel : fallbackChannel,
			ts: d.ts ?? "",
			status: d.status ?? "discussion",
			uuid: d.uuid ?? "",
			title: d.title ?? "msg",
			signature: d.signature,
			text: typeof d.text === "string" ? d.text : ""
		};
	}

	// --- transport: WebSocket primary (squawk-ws protocol), automatic fallback to polling ---
	function wsUrl() {
		const proto = location.protocol === "https:" ? "wss:" : "ws:";
		const base = location.pathname.replace(/\/[^/]*$/, "");

		return `${proto}//${location.host}${base}/squawk-ws`;
	}

	function closeWs() {
		intentionalClose = true;
		window.clearTimeout(wsFailTimer);
		flushWsBuf();

		if (ws) {
			try {
				ws.onclose = null;
				ws.onerror = null;
				ws.onmessage = null;
				ws.close();
			} catch {}

			ws = null;
		}
	}

	// incoming ws frames are buffered and flushed at most every 250ms:
	// a subscribe replay can deliver ~1000 frames at once, and ingesting +
	// re-rendering per frame is what crashed the renderer.
	let wsBuf = [];

	function flushWsBuf() {
		window.clearTimeout(wsFlushTimer);
		wsFlushTimer = undefined;

		if (!wsBuf.length || !running) {
			wsBuf = [];

			return;
		}

		const byCh = new Map();

		for (const { channel, msg } of wsBuf.splice(0)) {
			let a = byCh.get(channel);

			if (!a) {
				a = [];
				byCh.set(channel, a);
			}

			a.push(msg);
		}

		for (const [ch, msgs] of byCh) ingest(ch, msgs);
	}

	function onWsFrames(ev) {
		try {
			const d = JSON.parse(ev.data);
			const arr = Array.isArray(d) ? d : d.messages ? d.messages : [d];

			for (const raw of arr) {
				const ch = typeof raw?.channel === "string" && $.get(tabs)[raw.channel] ? raw.channel : $.get(activeName);
				const m = normalizeWs(raw, ch);

				if (!m) continue;

				const t = $.get(tabs)[ch];

				if (!t) continue;

				// gseq resume cursor (ws seq space; poll cursor stays in file_seq space)
				if (raw.seq > t.wsSeq) t.wsSeq = raw.seq;

				wsBuf.push({ channel: ch, msg: m });
			}

			window.clearTimeout(wsFailTimer);

			if (!$.get(useWs)) onPushLive();
			if (wsFlushTimer === undefined) wsFlushTimer = window.setTimeout(flushWsBuf, 250);
		} catch {}
	}

	function onPushLive() {
		window.clearTimeout(wsFailTimer);
		window.clearTimeout(reconTimer);
		reconnectDelay = 1000;

		if (!$.get(useWs)) sysLine("live push connected");

		$.set(useWs, true);
		$.set(conn, "live");
		polling = false;
		window.clearTimeout(pollTimer);
	}

	function onPushLost() {
		flushWsBuf();

		if ($.get(useWs)) sysLine("live push lost — reconnecting");

		$.set(useWs, false);
		$.set(conn, "reconnecting");
		startPoll("push disconnected");
		scheduleReconnect();
	}

	// server protocol: first text frame must be {subscribe: [...channels], since}
	// (since = per-channel gseq, or a single gseq). since=0 replays newest 1000.
	function connectPush(quiet = false) {
		if (!running) return;

		closeWs();

		const chans = Object.keys($.get(tabs));

		if (!chans.length) return;

		intentionalClose = false;

		let sock;

		try {
			sock = new WebSocket(wsUrl());
		} catch {
			$.set(useWs, false);
			startPoll("ws unavailable");

			return;
		}

		ws = sock;

		if (!quiet) $.set(conn, "reconnecting");

		wsFailTimer = window.setTimeout(
			() => {
				if (ws !== sock) return;

				intentionalClose = true;

				try {
					sock.close();
				} catch {}

				ws = null;

				if (!quiet) sysLine("live push unavailable — auto-fallback to polling");

				startPoll(quiet ? "ws retry failed" : "ws protocol timeout");
			},
			8000
		);

		sock.onopen = () => {
			const since = {};

			for (const c of chans) since[c] = $.get(tabs)[c]?.wsSeq ?? 0;

			try {
				sock.send(JSON.stringify({ subscribe: chans, since }));
			} catch {}
		};

		sock.onmessage = onWsFrames;

		sock.onerror = () => {
			/* onclose follows */
		};

		sock.onclose = () => {
			if (ws !== sock) return;

			ws = null;

			if (intentionalClose || !running) return;

			onPushLost();
		};
	}

	function scheduleReconnect() {
		if (!running) return;

		const d = reconnectDelay;

		reconnectDelay = Math.min(reconnectDelay * 2, 30000);
		window.clearTimeout(reconTimer);

		reconTimer = window.setTimeout(
			() => {
				if (!running || $.get(useWs)) return;

				connectPush();
			},
			d
		);
	}

	async function pollOnce(channel, cursor) {
		const t0 = performance.now();

		try {
			const r = await fetch(`wait?since=${cursor}&channel=${encodeURIComponent(channel)}&tail=200`);

			if (!r.ok) throw new Error("http " + r.status);

			const d = await r.json();

			if (!d.ok) throw new Error(d.error || "bad response");

			$.set(latency, Math.round(performance.now() - t0), true);
			ingest(channel, d.messages || []);

			return true;
		} catch {
			return false;
		}
	}

	function startPoll(reason) {
		if (!running || polling) return;

		polling = true;

		if (!$.get(useWs)) sysLine(reason + " — on polling fallback");

		let lastRetry = 0;

		const loop = async () => {
			if (!running || $.get(useWs)) {
				polling = false;

				return;
			}

			const ok = await pollOnce($.get(activeName), $.get(tabs)[$.get(activeName)]?.cursor ?? 0);

			if (!running || $.get(useWs)) {
				polling = false;

				return;
			}

			$.set(conn, ok ? "degraded" : "reconnecting", true);

			// quiet background retry of live push every 30s while polling healthy
			const now = Date.now();

			if (ok && now - lastRetry > 30000) {
				lastRetry = now;
				connectPush(true);
			}

			pollTimer = window.setTimeout(loop, ok ? 2500 : 5000);
		};

		loop();
	}

	// --- boot: snapshot then live transport ---
	$.user_effect(() => {
		running = true;
		sysLine("tuned in — pulling the latest traffic…");

		(async () => {
			const t = $.get(tabs)[$.get(activeName)];

			if (t) await pollOnce($.get(activeName), t.cursor);
			if (running) connectPush();
		})();

		const onOnline = () => {
			if (running && !$.get(useWs)) connectPush();
		};

		window.addEventListener("online", onOnline);

		return () => {
			running = false;
			window.removeEventListener("online", onOnline);
			window.clearTimeout(pollTimer);
			window.clearTimeout(wsFailTimer);
			window.clearTimeout(reconTimer);
			window.clearTimeout(wsFlushTimer);

			try {
				ws?.close();
			} catch {}

			ws = null;
		};
	});

	// --- scroll: stick to bottom when new messages arrive ---
	$.user_effect(() => {
		const el = $.get(logEl);
		const n = $.get(active).messages.length;
		const name = $.get(activeName);

		if (!el || !n) return;

		// run after DOM updates
		queueMicrotask(() => {
			const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;

			if (atBottom) el.scrollTop = el.scrollHeight;
		});
	});

	function showTab(name) {
		if ($.get(logEl) && $.get(tabs)[$.get(activeName)]) {
			$.get(tabs)[$.get(activeName)] = {
				...$.get(tabs)[$.get(activeName)],
				scrollTop: $.get(logEl).scrollTop
			};
		}

		$.set(activeName, name, true);

		queueMicrotask(() => {
			const t = $.get(tabs)[name];

			if ($.get(logEl) && t) $.get(logEl).scrollTop = t.scrollTop || $.get(logEl).scrollHeight;
		});
	}

	function addTab(name) {
		if ($.get(tabs)[name]) {
			showTab(name);
			$.set(showDlg, false);

			return;
		}

		$.get(tabs)[name] = { messages: [], cursor: 0, scrollTop: 0, wsSeq: 0 };
		$.set(showDlg, false);
		sysLine(`channel #${name} added — tuned in`);
		showTab(name);

		// re-subscribe push to include the new channel (delta-only replay via since)
		connectPush();

		if (!$.get(useWs)) pollOnce(name, 0);
	}

	function closeTab(name) {
		if (!$.get(tabs)[name] || Object.keys($.get(tabs)).length <= 1) return;

		const { [name]: _, ...rest } = $.get(tabs);

		$.set(tabs, rest, true);

		if (name === $.get(activeName)) showTab(Object.keys(rest)[0]);
	}

	async function sendMsg() {
		const text = $.get(draft).trim();

		if (!text || $.get(sending) || !$.get(activeName)) return;

		$.set(sending, true);

		try {
			const r = await fetch("send", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ channel: $.get(activeName), text })
			});

			const d = await r.json().catch(() => ({}));

			if (!r.ok || !d.ok) throw new Error(d.error || "http " + r.status);

			$.set(draft, "");

			// the live loop renders it; no optimistic duplicate needed
		} catch(e) {
			sysLine("send failed: " + (e.message || e) + " — retrying is safe");
		} finally {
			$.set(sending, false);
		}
	}

	var fragment = root_3();
	var header = $.first_child(fragment);
	var span = $.sibling($.child(header), 2);
	var text_1 = $.only_child(span, true);

	$.reset(header);

	var div = $.sibling(header, 2);
	var node = $.child(div);

	$.each(node, 16, () => Object.keys($.get(tabs)), (name) => name, ($$anchor, name) => {
		var div_1 = root_1();
		let classes;
		var span_1 = $.child(div_1);
		var text_2 = $.only_child(span_1);
		var node_1 = $.sibling(span_1, 2);

		{
			var consequent = ($$anchor) => {
				var span_2 = root();

				$.template_effect(() => $.set_attribute(span_2, 'title', `close #${name}`));

				$.delegated('click', span_2, (e) => {
					e.stopPropagation();
					closeTab(name);
				});

				$.delegated('keydown', span_2, (e) => {
					if (e.key === "Enter") {
						e.stopPropagation();
						closeTab(name);
					}
				});

				$.append($$anchor, span_2);
			};

			var d_1 = $.derived(() => Object.keys($.get(tabs)).length > 1);

			$.if(node_1, ($$render) => {
				if ($.get(d_1)) $$render(consequent);
			});
		}

		$.reset(div_1);

		$.template_effect(() => {
			$.set_attribute(div_1, 'aria-selected', name === $.get(activeName));
			classes = $.set_class(div_1, 1, 'tab', null, classes, { active: name === $.get(activeName) });
			$.set_text(text_2, `#${name ?? ''}`);
		});

		$.delegated('click', div_1, () => showTab(name));
		$.delegated('keydown', div_1, (e) => e.key === "Enter" && showTab(name));
		$.append($$anchor, div_1);
	});

	var button = $.sibling(node, 2);

	$.reset(div);

	var div_2 = $.sibling(div, 2);
	var node_2 = $.child(div_2);

	$.each(node_2, 17, () => $.get(sysLines), $.index, ($$anchor, s) => {
		var div_3 = root_2();
		var text_3 = $.only_child(div_3, true);

		$.template_effect(() => $.set_text(text_3, $.get(s)));
		$.append($$anchor, div_3);
	});

	var node_3 = $.sibling(node_2, 2);

	$.each(node_3, 17, () => $.get(active).messages, (m) => keyOf(m), ($$anchor, m) => {
		MessageCard($$anchor, {
			get m() {
				return $.get(m);
			}
		});
	});

	$.reset(div_2);
	$.bind_this(div_2, ($$value) => $.set(logEl, $$value), () => $.get(logEl));

	var div_4 = $.sibling(div_2, 2);
	var input = $.child(div_4);

	$.remove_input_defaults(input);

	var button_1 = $.sibling(input, 2);

	$.reset(div_4);

	var div_5 = $.sibling(div_4, 2);
	var span_3 = $.child(div_5);
	var span_4 = $.child(span_3);
	var text_4 = $.sibling(span_4, 1, true);

	$.reset(span_3);

	var span_5 = $.sibling(span_3, 2);
	var text_5 = $.only_child(span_5);
	var span_6 = $.sibling(span_5, 2);
	var text_6 = $.only_child(span_6, true);

	$.reset(div_5);

	var node_4 = $.sibling(div_5, 2);

	{
		var consequent_1 = ($$anchor) => {
			AddChannelDialog($$anchor, { onClose: () => $.set(showDlg, false), onAdd: addTab });
		};

		$.if(node_4, ($$render) => {
			if ($.get(showDlg)) $$render(consequent_1);
		});
	}

	$.template_effect(
		($0) => {
			$.set_attribute(span, 'title', $.get(useWs)
				? "live push via websocket"
				: "polling fallback — push unavailable");

			$.set_text(text_1, $.get(useWs) ? "push" : "poll");
			$.set_attribute(input, 'placeholder', `message #${$.get(activeName)}…  (enter to send)`);
			input.disabled = $.get(sending);
			button_1.disabled = $0;
			$.set_class(span_4, 1, `dot ${$.get(dotClass) ?? ''}`, 'svelte-n50uah');
			$.set_text(text_4, $.get(connLabel));
			$.set_text(text_5, `seq ${($.get(active).cursor || "—") ?? ''}`);
			$.set_text(text_6, $.get(latency) ? `${$.get(latency)}ms` : "");
		},
		[() => $.get(sending) || !$.get(draft).trim()]
	);

	$.delegated('click', button, () => $.set(showDlg, true));

	$.delegated('keydown', input, (e) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			sendMsg();
		}
	});

	$.bind_value(input, () => $.get(draft), ($$value) => $.set(draft, $$value));
	$.delegated('click', button_1, sendMsg);
	$.append($$anchor, fragment);
	$.pop();
}

$.delegate(['click', 'keydown']);