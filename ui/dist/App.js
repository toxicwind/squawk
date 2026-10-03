import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';
import { mdBlock, esc } from "../markdown.js";
import MessageCard from "./MessageCard.js";
import AddChannelDialog from "./AddChannelDialog.js";
import { live, keyOf } from "./live.js";

var root = $.from_html(`<span class="x" role="button" tabindex="0">×</span>`);
var root_1 = $.from_html(`<div role="tab" tabindex="0"><span> </span> <!></div>`);
var root_2 = $.from_html(`<div class="sys"> </div>`);
var root_3 = $.from_html(`<header><h1>SQUAWK</h1> <span class="transport svelte-n50uah" title="single websocket push connection — no polling"> </span></header> <div id="tabs" role="tablist"><!> <button id="addTab" title="add channel" aria-label="add channel">+</button></div> <div id="log"><!> <!></div> <div id="composer"><input id="msg" autocomplete="off" aria-label="message"/> <button id="send">send</button></div> <div id="statusbar"><span><span></span> </span> <span> </span> <span> </span></div> <!>`, 1);

export default function App($$anchor, $$props) {
	$.push($$props, true);

	const VALID_NAME = /^[a-z0-9-_]{1,32}$/;

	// --- UI state (Svelte 5 runes); transport + message data live in the
	// --- `live` singleton (ui/live.svelte.js): one persistent websocket,
	// --- server push only, no HTTP polling anywhere.
	let activeName = $.state("fleet");

	let showDlg = $.state(false);
	let draft = $.state("");
	let sending = $.state(false);
	let logEl = $.state(null);

	// message list for the active tab, derived from the live connection state
	let active = $.derived(() => live.tabs[$.get(activeName)] ?? { messages: [], cursor: 0 });

	let dotClass = $.derived(() => live.status === "live"
		? "live"
		: live.status === "connecting" ? "recon" : "dead");

	let connLabel = $.derived(() => live.status === "live"
		? "live"
		: live.status === "connecting"
			? "connecting…"
			: `reconnecting… (attempt ${live.attempt})`);

	// --- boot: open the one websocket; the server replays since our cursor ---
	$.user_effect(() => {
		live.ensureChannel("fleet");
		live.connect();

		return () => {
			live.disconnect();
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
		if ($.get(logEl)) {
			const t = live.tabs[$.get(activeName)];

			if (t) t.scrollTop = $.get(logEl).scrollTop;
		}

		$.set(activeName, name, true);

		queueMicrotask(() => {
			if ($.get(logEl)) $.get(logEl).scrollTop = live.tabs[name]?.scrollTop || $.get(logEl).scrollHeight;
		});
	}

	function addTab(name) {
		$.set(showDlg, false);

		if (live.tabs[name]) {
			showTab(name);

			return;
		}

		// live re-subscribes over the socket (delta-only replay via since cursors)
		live.addChannel(name);

		showTab(name);
	}

	function closeTab(name) {
		if (!live.tabs[name] || Object.keys(live.tabs).length <= 1) return;

		live.removeChannel(name);

		if (name === $.get(activeName)) showTab(Object.keys(live.tabs)[0]);
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

			// the server push renders the echo; no optimistic duplicate needed
		} catch(e) {
			live.sysLine("send failed: " + (e.message || e) + " — retrying is safe");
		} finally {
			$.set(sending, false);
		}
	}

	var fragment = root_3();
	var header = $.first_child(fragment);
	var span = $.sibling($.child(header), 2);
	var text_1 = $.only_child(span);

	$.reset(header);

	var div = $.sibling(header, 2);
	var node = $.child(div);

	$.each(node, 16, () => Object.keys(live.tabs), (name) => name, ($$anchor, name) => {
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

			var d_1 = $.derived(() => Object.keys(live.tabs).length > 1);

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

	$.each(node_2, 17, () => live.sysLines, $.index, ($$anchor, s) => {
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
			$.set_text(text_1, `ws · ${live.status ?? ''}`);
			$.set_attribute(input, 'placeholder', `message #${$.get(activeName)}…  (enter to send)`);
			input.disabled = $.get(sending);
			button_1.disabled = $0;
			$.set_class(span_4, 1, `dot ${$.get(dotClass) ?? ''}`, 'svelte-n50uah');
			$.set_text(text_4, $.get(connLabel));
			$.set_text(text_5, `seq ${($.get(active).cursor || "—") ?? ''}`);
			$.set_text(text_6, live.latency ? `${live.latency}ms` : "");
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