import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';
import { mdBlock, esc } from "../markdown.js";
import MessageCard from "./MessageCard.js";
import AddChannelDialog from "./AddChannelDialog.js";
import { live, keyOf } from "./live.js";

var root = $.from_html(`<span class="conn-lat"> </span>`);
var root_1 = $.from_html(`<button class="x">×</button>`);
var root_2 = $.from_html(`<div role="tab" tabindex="0"><span class="tab-name"> </span> <!></div>`);
var root_3 = $.from_html(`<div class="sys"> </div>`);
var root_4 = $.from_html(`<div class="empty"><div class="empty-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"></path></svg></div> <p class="empty-title"> </p> <p class="empty-sub">messages land here live — say something below</p></div>`);
var root_5 = $.from_html(`<div class="app"><header class="topbar"><div class="brand"><span class="brand-mark" aria-hidden="true">◈</span> <h1>SQUAWK</h1></div> <div class="conn" title="single websocket push connection — no polling" role="status"><span></span> <span class="conn-label"> </span> <!></div></header> <nav id="tabs" aria-label="channels"><div class="tabs-scroll" role="tablist"><!> <button id="addTab" title="add channel" aria-label="add channel"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10"></path></svg></button></div></nav> <div id="log"><!> <!> <!></div> <div id="composer"><div class="composer-bar"><input id="msg" autocomplete="off" autocapitalize="sentences" aria-label="message" enterkeyhint="send"/> <button id="send" aria-label="send message" title="send (enter)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"></path></svg></button></div> <div class="composer-meta" aria-hidden="true"><span><kbd>enter</kbd> to send</span></div></div> <footer id="statusbar"><span class="sb-item"> </span> <span class="sb-item sb-right"> </span></footer></div> <!>`, 1);

export default function App($$anchor, $$props) {
	$.push($$props, true);

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

	let tabCount = $.derived(() => Object.keys(live.tabs).length);

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

	var fragment = root_5();
	var div = $.first_child(fragment);
	var header = $.child(div);
	var div_1 = $.sibling($.child(header), 2);
	var span = $.child(div_1);
	var span_1 = $.sibling(span, 2);
	var text_1 = $.only_child(span_1, true);
	var node = $.sibling(span_1, 2);

	{
		var consequent = ($$anchor) => {
			var span_2 = root();
			var text_2 = $.only_child(span_2);

			$.template_effect(() => $.set_text(text_2, `${live.latency ?? ''}ms`));
			$.append($$anchor, span_2);
		};

		$.if(node, ($$render) => {
			if (live.latency) $$render(consequent);
		});
	}

	$.reset(div_1);
	$.reset(header);

	var nav = $.sibling(header, 2);
	var div_2 = $.child(nav);
	var node_1 = $.child(div_2);

	$.each(node_1, 16, () => Object.keys(live.tabs), (name) => name, ($$anchor, name) => {
		var div_3 = root_2();
		let classes;
		var span_3 = $.child(div_3);
		var text_3 = $.only_child(span_3);
		var node_2 = $.sibling(span_3, 2);

		{
			var consequent_1 = ($$anchor) => {
				var button = root_1();

				$.template_effect(() => {
					$.set_attribute(button, 'title', `close #${name}`);
					$.set_attribute(button, 'aria-label', `close #${name}`);
				});

				$.delegated('click', button, (e) => {
					e.stopPropagation();
					closeTab(name);
				});

				$.append($$anchor, button);
			};

			$.if(node_2, ($$render) => {
				if ($.get(tabCount) > 1) $$render(consequent_1);
			});
		}

		$.reset(div_3);

		$.template_effect(() => {
			$.set_attribute(div_3, 'aria-selected', name === $.get(activeName));
			classes = $.set_class(div_3, 1, 'tab', null, classes, { active: name === $.get(activeName) });
			$.set_text(text_3, `#${name ?? ''}`);
		});

		$.delegated('click', div_3, () => showTab(name));
		$.delegated('keydown', div_3, (e) => e.key === "Enter" && showTab(name));
		$.append($$anchor, div_3);
	});

	var button_1 = $.sibling(node_1, 2);

	$.reset(div_2);
	$.reset(nav);

	var div_4 = $.sibling(nav, 2);
	var node_3 = $.child(div_4);

	$.each(node_3, 17, () => live.sysLines, $.index, ($$anchor, s) => {
		var div_5 = root_3();
		var text_4 = $.only_child(div_5, true);

		$.template_effect(() => $.set_text(text_4, $.get(s)));
		$.append($$anchor, div_5);
	});

	var node_4 = $.sibling(node_3, 2);

	{
		var consequent_2 = ($$anchor) => {
			var div_6 = root_4();
			var p = $.sibling($.child(div_6), 2);
			var text_5 = $.only_child(p);

			$.next(2);
			$.reset(div_6);
			$.template_effect(() => $.set_text(text_5, `nothing on #${$.get(activeName) ?? ''} yet`));
			$.append($$anchor, div_6);
		};

		$.if(node_4, ($$render) => {
			if ($.get(active).messages.length === 0) $$render(consequent_2);
		});
	}

	var node_5 = $.sibling(node_4, 2);

	$.each(node_5, 19, () => $.get(active).messages, (m) => keyOf(m), ($$anchor, m, i) => {
		{
			let $0 = $.derived(() => $.get(i) > 0 && $.get(active).messages[$.get(i) - 1].from === $.get(m).from);

			MessageCard($$anchor, {
				get m() {
					return $.get(m);
				},

				get compact() {
					return $.get($0);
				}
			});
		}
	});

	$.reset(div_4);
	$.bind_this(div_4, ($$value) => $.set(logEl, $$value), () => $.get(logEl));

	var div_7 = $.sibling(div_4, 2);
	var div_8 = $.child(div_7);
	var input = $.child(div_8);

	$.remove_input_defaults(input);

	var button_2 = $.sibling(input, 2);

	$.reset(div_8);
	$.next(2);
	$.reset(div_7);

	var footer = $.sibling(div_7, 2);
	var span_4 = $.child(footer);
	var text_6 = $.only_child(span_4);
	var span_5 = $.sibling(span_4, 2);
	var text_7 = $.only_child(span_5);

	$.reset(footer);
	$.reset(div);

	var node_6 = $.sibling(div, 2);

	{
		var consequent_3 = ($$anchor) => {
			AddChannelDialog($$anchor, { onClose: () => $.set(showDlg, false), onAdd: addTab });
		};

		$.if(node_6, ($$render) => {
			if ($.get(showDlg)) $$render(consequent_3);
		});
	}

	$.template_effect(
		($0) => {
			$.set_attribute(div_1, 'data-state', live.status);
			$.set_attribute(div_1, 'aria-label', `connection: ${$.get(connLabel)}`);
			$.set_class(span, 1, `dot ${$.get(dotClass) ?? ''}`);
			$.set_text(text_1, $.get(connLabel));
			$.set_attribute(input, 'placeholder', `message #${$.get(activeName)}`);
			input.disabled = $.get(sending);
			button_2.disabled = $0;
			$.set_text(text_6, `seq ${($.get(active).cursor || "—") ?? ''}`);
			$.set_text(text_7, `${$.get(tabCount) ?? ''} channel${$.get(tabCount) === 1 ? "" : "s"}`);
		},
		[() => $.get(sending) || !$.get(draft).trim()]
	);

	$.delegated('click', button_1, () => $.set(showDlg, true));

	$.delegated('keydown', input, (e) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			sendMsg();
		}
	});

	$.bind_value(input, () => $.get(draft), ($$value) => $.set(draft, $$value));
	$.delegated('click', button_2, sendMsg);
	$.append($$anchor, fragment);
	$.pop();
}

$.delegate(['click', 'keydown']);