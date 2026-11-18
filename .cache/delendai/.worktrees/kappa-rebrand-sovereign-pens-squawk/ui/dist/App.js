import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';
import MessageCard from "./MessageCard.js";
import AddChannelDialog from "./AddChannelDialog.js";
import { live, keyOf } from "./live.js";

var root = $.from_html(`<button class="x">×</button>`);
var root_1 = $.from_html(`<div role="tab" tabindex="0"><span class="tab-name"> </span> <!></div>`);
var root_2 = $.from_html(`<div class="sys"> </div>`);
var root_3 = $.from_html(`<div class="skel"><div class="skel-row"><span class="skel-avatar"></span><span class="skel-name"></span><span class="skel-ts"></span></div> <div class="skel-line"></div> <div class="skel-line short"></div></div>`);
var root_4 = $.from_html(`<div class="skels" aria-hidden="true"></div>`);
var root_5 = $.from_html(`<div class="empty"><div class="empty-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"></path></svg></div> <p class="empty-title"> </p> <p class="empty-sub">messages land here live — say something below</p></div>`);
var root_6 = $.from_html(`<button id="jump"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12l7 7 7-7"></path></svg> </button>`);
var root_7 = $.from_html(`<div class="app"><header class="topbar"><div class="brand"><span class="brand-mark" aria-hidden="true">◈</span> <h1>SQUAWK</h1></div> <div class="conn" title="single websocket push connection — no polling" role="status"><span></span> <span class="conn-label"> </span></div></header> <nav id="tabs" aria-label="channels"><div class="tabs-scroll" role="tablist"><!> <button id="addTab" title="add channel" aria-label="add channel"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10"></path></svg></button></div></nav> <div id="log"><!> <!> <!></div> <!> <div id="composer"><div class="composer-bar"><textarea id="msg" autocomplete="off" autocapitalize="sentences" aria-label="message" enterkeyhint="send"></textarea> <button id="send" aria-label="send message" title="send (enter)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"></path></svg></button></div> <div class="composer-meta" aria-hidden="true"><span><kbd>enter</kbd> to send · <kbd>shift</kbd>+<kbd>enter</kbd> for a new line</span></div></div> <footer id="statusbar"><span class="sb-item"> </span> <span class="sb-item sb-right"> </span></footer></div> <!>`, 1);

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

	// stuck = the user scrolled up; new arrivals surface a jump pill
	// instead of yanking the scroll position.
	let stuck = $.state(false);

	let newWhileStuck = $.state(0);
	let prevCount = 0;
	let msgEl = $.state(null);

	// auto-growing composer: the textarea expands with content up to a cap,
	// then scrolls internally. Enter sends, Shift+Enter inserts a newline.
	function autogrow() {
		const el = $.get(msgEl);

		if (!el) return;

		el.style.height = "auto";
		el.style.height = Math.min(el.scrollHeight, 168) + "px";
	}

	// shrink back to one row whenever the draft clears (e.g. after send)
	$.user_effect(() => {
		if ($.get(draft) === "") autogrow();
	});

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
	let loading = $.derived(() => $.get(active).messages.length === 0 && live.status !== "live");

	// --- boot: open the one websocket; the server replays since our cursor ---
	$.user_effect(() => {
		live.ensureChannel("fleet");
		live.connect();

		return () => {
			live.disconnect();
		};
	});

	// --- count arrivals while stuck (drives the jump pill) ---
	$.user_effect(() => {
		const n = $.get(active).messages.length;

		if ($.get(stuck) && n > prevCount) $.set(newWhileStuck, $.get(newWhileStuck) + (n - prevCount));

		prevCount = n;
	});

	// --- scroll: stick to bottom when new messages arrive (unless stuck) ---
	$.user_effect(() => {
		const el = $.get(logEl);
		const n = $.get(active).messages.length;

		void $.get(activeName);

		if (!el || !n) return;

		// run after DOM updates
		queueMicrotask(() => {
			const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;

			if (atBottom) el.scrollTop = el.scrollHeight;
		});
	});

	function onLogScroll() {
		if (!$.get(logEl)) return;

		$.set(stuck, $.get(logEl).scrollHeight - $.get(logEl).scrollTop - $.get(logEl).clientHeight > 120);

		if (!$.get(stuck)) $.set(newWhileStuck, 0);
	}

	function jumpToLatest() {
		if ($.get(logEl)) $.get(logEl).scrollTop = $.get(logEl).scrollHeight;

		$.set(stuck, false);
		$.set(newWhileStuck, 0);
	}

	function showTab(name) {
		if ($.get(logEl)) {
			const t = live.tabs[$.get(activeName)];

			if (t) t.scrollTop = $.get(logEl).scrollTop;
		}

		$.set(activeName, name, true);
		$.set(stuck, false);
		$.set(newWhileStuck, 0);

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

	var fragment = root_7();
	var div = $.first_child(fragment);
	var header = $.child(div);
	var div_1 = $.sibling($.child(header), 2);
	var span = $.child(div_1);
	var span_1 = $.sibling(span, 2);
	var text_1 = $.only_child(span_1, true);

	$.reset(div_1);
	$.reset(header);

	var nav = $.sibling(header, 2);
	var div_2 = $.child(nav);
	var node = $.child(div_2);

	$.each(node, 16, () => Object.keys(live.tabs), (name) => name, ($$anchor, name) => {
		var div_3 = root_1();
		let classes;
		var span_2 = $.child(div_3);
		var text_2 = $.only_child(span_2);
		var node_1 = $.sibling(span_2, 2);

		{
			var consequent = ($$anchor) => {
				var button = root();

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

			$.if(node_1, ($$render) => {
				if ($.get(tabCount) > 1) $$render(consequent);
			});
		}

		$.reset(div_3);

		$.template_effect(() => {
			$.set_attribute(div_3, 'aria-selected', name === $.get(activeName));
			classes = $.set_class(div_3, 1, 'tab', null, classes, { active: name === $.get(activeName) });
			$.set_text(text_2, `#${name ?? ''}`);
		});

		$.delegated('click', div_3, () => showTab(name));
		$.delegated('keydown', div_3, (e) => e.key === "Enter" && showTab(name));
		$.append($$anchor, div_3);
	});

	var button_1 = $.sibling(node, 2);

	$.reset(div_2);
	$.reset(nav);

	var div_4 = $.sibling(nav, 2);
	var node_2 = $.child(div_4);

	$.each(node_2, 17, () => live.sysLines, $.index, ($$anchor, s) => {
		var div_5 = root_2();
		var text_3 = $.only_child(div_5, true);

		$.template_effect(() => $.set_text(text_3, $.get(s)));
		$.append($$anchor, div_5);
	});

	var node_3 = $.sibling(node_2, 2);

	{
		var consequent_2 = ($$anchor) => {
			var fragment_1 = $.comment();
			var node_4 = $.first_child(fragment_1);

			{
				var consequent_1 = ($$anchor) => {
					var div_6 = root_4();

					$.each(div_6, 20, () => [0, 1, 2, 3], (i) => i, ($$anchor, i) => {
						var div_7 = root_3();

						$.append($$anchor, div_7);
					});

					$.reset(div_6);
					$.append($$anchor, div_6);
				};

				var alternate = ($$anchor) => {
					var div_8 = root_5();
					var p = $.sibling($.child(div_8), 2);
					var text_4 = $.only_child(p);

					$.next(2);
					$.reset(div_8);
					$.template_effect(() => $.set_text(text_4, `nothing on #${$.get(activeName) ?? ''} yet`));
					$.append($$anchor, div_8);
				};

				$.if(node_4, ($$render) => {
					if ($.get(loading)) $$render(consequent_1); else $$render(alternate, -1);
				});
			}

			$.append($$anchor, fragment_1);
		};

		$.if(node_3, ($$render) => {
			if ($.get(active).messages.length === 0) $$render(consequent_2);
		});
	}

	var node_5 = $.sibling(node_3, 2);

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

	var node_6 = $.sibling(div_4, 2);

	{
		var consequent_3 = ($$anchor) => {
			var button_2 = root_6();
			var text_5 = $.sibling($.child(button_2));

			$.reset(button_2);

			$.template_effect(() => {
				$.set_attribute(button_2, 'aria-label', `jump to latest, ${$.get(newWhileStuck)} new messages`);
				$.set_text(text_5, ` ${$.get(newWhileStuck) ?? ''} new`);
			});

			$.delegated('click', button_2, jumpToLatest);
			$.append($$anchor, button_2);
		};

		$.if(node_6, ($$render) => {
			if ($.get(stuck) && $.get(newWhileStuck) > 0) $$render(consequent_3);
		});
	}

	var div_9 = $.sibling(node_6, 2);
	var div_10 = $.child(div_9);
	var textarea = $.child(div_10);

	$.remove_textarea_child(textarea);
	$.set_attribute(textarea, 'rows', 1);
	$.bind_this(textarea, ($$value) => $.set(msgEl, $$value), () => $.get(msgEl));

	var button_3 = $.sibling(textarea, 2);

	$.reset(div_10);
	$.next(2);
	$.reset(div_9);

	var footer = $.sibling(div_9, 2);
	var span_3 = $.child(footer);
	var text_6 = $.only_child(span_3);
	var span_4 = $.sibling(span_3, 2);
	var text_7 = $.only_child(span_4);

	$.reset(footer);
	$.reset(div);

	var node_7 = $.sibling(div, 2);

	{
		var consequent_4 = ($$anchor) => {
			AddChannelDialog($$anchor, { onClose: () => $.set(showDlg, false), onAdd: addTab });
		};

		$.if(node_7, ($$render) => {
			if ($.get(showDlg)) $$render(consequent_4);
		});
	}

	$.template_effect(
		($0) => {
			$.set_attribute(div_1, 'data-state', live.status);
			$.set_attribute(div_1, 'aria-label', `connection: ${$.get(connLabel)}`);
			$.set_class(span, 1, `dot ${$.get(dotClass) ?? ''}`);
			$.set_text(text_1, $.get(connLabel));
			$.set_attribute(textarea, 'placeholder', `message #${$.get(activeName)}`);
			textarea.disabled = $.get(sending);
			button_3.disabled = $0;
			$.set_text(text_6, `seq ${($.get(active).cursor || "—") ?? ''}`);
			$.set_text(text_7, `${$.get(tabCount) ?? ''} channel${$.get(tabCount) === 1 ? "" : "s"}`);
		},
		[() => $.get(sending) || !$.get(draft).trim()]
	);

	$.delegated('click', button_1, () => $.set(showDlg, true));
	$.event('scroll', div_4, onLogScroll);
	$.delegated('input', textarea, autogrow);

	$.delegated('keydown', textarea, (e) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			sendMsg();
		}
	});

	$.bind_value(textarea, () => $.get(draft), ($$value) => $.set(draft, $$value));
	$.delegated('click', button_3, sendMsg);
	$.append($$anchor, fragment);
	$.pop();
}

$.delegate(['click', 'keydown', 'input']);