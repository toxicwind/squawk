import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';
import MessageCard from "./MessageCard.js";
import AddChannelDialog from "./AddChannelDialog.js";
import { untrack, tick } from "svelte";
import { live as feedLive, keyOf as feedKeyOf } from "./live.js";
import { natsLive, keyOf as natsKeyOf } from "./nats-live.js";

var root = $.from_html(`<button class="x">×</button>`);
var root_1 = $.from_html(`<div role="tab" tabindex="0"><span class="tab-name"> </span> <!></div>`);
var root_2 = $.from_html(`<div class="sys"> </div>`);
var root_3 = $.from_html(`<div class="skel"><div class="skel-row"><span class="skel-avatar"></span><span class="skel-name"></span><span class="skel-ts"></span></div> <div class="skel-line"></div> <div class="skel-line short"></div></div>`);
var root_4 = $.from_html(`<div class="skels" aria-hidden="true"></div>`);
var root_5 = $.from_html(`<div class="empty"><div class="empty-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"></path></svg></div> <p class="empty-title"> </p> <p class="empty-sub">messages land here live — say something below</p></div>`);
var root_6 = $.from_html(`<span style="opacity:.55;font-size:12px;">loading older…</span>`);
var root_7 = $.from_html(`<button style="background:none;border:1px solid rgba(255,255,255,.14);border-radius:999px;color:inherit;padding:3px 12px;font-size:12px;cursor:pointer;" aria-label="load older messages">↑ load older messages</button>`);
var root_8 = $.from_html(`<span style="opacity:.45;font-size:12px;"> </span>`);
var root_9 = $.from_html(`<div style="display:flex;justify-content:center;align-items:center;height:32px;"><!></div>`);
var root_10 = $.from_html(`<span style="opacity:.65;"> </span> <button style="background:none;border:none;color:inherit;opacity:.6;cursor:pointer;font-size:12px;" aria-label="close pack">✕</button>`, 1);
var root_11 = $.from_html(`<span style="opacity:.8;"> </span>`);
var root_12 = $.from_html(`<div style="opacity:.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"><span style="opacity:.7;"> </span> </div>`);
var root_13 = $.from_html(`<div style="opacity:.5;"> </div>`);
var root_14 = $.from_html(`<div style="margin-top:6px;display:flex;flex-direction:column;gap:2px;"><!> <!></div>`);
var root_15 = $.from_html(`<div style="margin:2px 8px 6px;border:1px solid rgba(255,255,255,.10);border-radius:10px;padding:6px 10px;font-size:12px;"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;"><button style="background:none;border:1px solid rgba(255,255,255,.14);border-radius:999px;color:inherit;padding:3px 12px;font-size:12px;cursor:pointer;" aria-label="summarize channel history as a pack"> </button> <input placeholder="focus terms (optional)" aria-label="pack focus terms" style="background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.10);border-radius:999px;color:inherit;padding:3px 10px;font-size:12px;min-width:150px;"/> <!> <!></div> <!></div>`);
var root_16 = $.from_html(`<button id="jump"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12l7 7 7-7"></path></svg> </button>`);
var root_17 = $.from_html(`<div class="app"><header class="topbar"><div class="brand"><span class="brand-mark" aria-hidden="true">◈</span> <h1>SQUAWK</h1></div> <div class="conn" title="single websocket push connection — no polling" role="status"><span></span> <span class="conn-label"> </span> <button class="src-toggle" aria-label="toggle live source"> </button></div></header> <nav id="tabs" aria-label="channels"><div class="tabs-scroll" role="tablist"><!> <button id="addTab" title="add channel" aria-label="add channel"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10"></path></svg></button></div></nav> <div id="log"><!> <!> <!> <!> <!></div> <!> <div id="composer"><div class="composer-bar"><textarea id="msg" autocomplete="off" autocapitalize="sentences" aria-label="message" enterkeyhint="send"></textarea> <button id="send" aria-label="send message" title="send (enter)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"></path></svg></button></div> <div class="composer-meta" aria-hidden="true"><span><kbd>enter</kbd> to send · <kbd>shift</kbd>+<kbd>enter</kbd> for a new line</span></div></div> <footer id="statusbar"><span class="sb-item"> </span> <span class="sb-item sb-right"> </span></footer></div> <!>`, 1);

export default function App($$anchor, $$props) {
	$.push($$props, true);

	// ?src=nats swaps the live source to NATS+JetStream (file-feed snapshot
	// for history, NATS for live). Default stays the feed websocket.
	const SRC_NATS = new URLSearchParams(location.search).get("src") === "nats";

	const live = SRC_NATS ? natsLive : feedLive;
	const keyOf = SRC_NATS ? natsKeyOf : feedKeyOf;

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

	// --- history paging: the boot snapshot is tail-capped (200); older
	// --- messages load on demand via /wait?before=<oldest loaded seq>.
	// --- Per-channel state; hasMore starts optimistic-true and the server's
	// --- has_more field corrects it on the first page fetch.
	let paging = $.state($.proxy({}));

	let page = $.derived(() => $.get(paging)[$.get(activeName)] ?? { hasMore: true, loading: false });

	// while a history page is being prepended, the pin-to-bottom and
	// new-arrival effects must not fire — scroll anchoring owns the position.
	let prepending = $.state(false);

	// --- history pack: C1+C3 digest of a channel's deep history from the
	// --- squawk-history service, proxied by the UI server at /pack (the
	// --- server holds the feed token; /pack takes seconds on big channels).
	let pack = $.state(null);

	let packQuery = $.state("");
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
	// untrack: ensureChannel reads live.tabs ($state). Without untrack, every
	// ingest re-runs this effect → disconnect/connect → duplicate syslines.
	$.user_effect(() => {
		untrack(() => {
			live.ensureChannel("fleet");

			if (SRC_NATS) {
				// NATS carries live messages only - hydrate history from the file
				// feed first (it stays the source of truth), then go live.
				fetch("wait?channel=fleet&tail=200").then((r) => r.json()).then((d) => {
					if (d && Array.isArray(d.messages)) live.ingestSnapshot("fleet", d.messages);
				}).catch((e) => live.sysLine("snapshot failed: " + (e?.message || e))).finally(() => live.connect());
			} else {
				live.connect();
			}
		});

		return () => {
			live.disconnect();
		};
	});

	// --- count arrivals while stuck (drives the jump pill) ---
	$.user_effect(() => {
		const n = $.get(active).messages.length;

		if ($.get(prepending)) {
			prevCount = n;

			return;
		}

		if ($.get(stuck) && n > prevCount) $.set(newWhileStuck, $.get(newWhileStuck) + (n - prevCount));

		prevCount = n;
	});

	// --- scroll: stick to bottom when new messages arrive (unless stuck) ---
	// On first paint scrollTop is 0 (not "at bottom"), so an atBottom-only
	// check left the feed glued to the top of a huge backlog. When !stuck,
	// always pin to bottom; when stuck, leave the user alone (jump pill).
	$.user_effect(() => {
		const el = $.get(logEl);
		const n = $.get(active).messages.length;

		void $.get(activeName);

		if (!el || !n || $.get(stuck) || $.get(prepending)) return;

		// run after DOM updates
		queueMicrotask(() => {
			el.scrollTop = el.scrollHeight;
		});
	});

	function onLogScroll() {
		if (!$.get(logEl)) return;

		$.set(stuck, $.get(logEl).scrollHeight - $.get(logEl).scrollTop - $.get(logEl).clientHeight > 120);

		if (!$.get(stuck)) $.set(newWhileStuck, 0);

		// near the top of loaded history: page in the next older chunk
		if ($.get(logEl).scrollTop < 90) void loadOlder();
	}

	// Fetch one history page older than the oldest loaded message and
	// prepend it, preserving the exact scroll position (scroll anchoring:
	// record height/top, ingest, then shift top by the height delta).
	async function loadOlder() {
		const name = $.get(activeName);
		const t = live.tabs[name];

		if (!t || !t.messages.length || $.get(prepending)) return;

		const p = $.get(paging)[name] ?? { hasMore: true, loading: false };

		if (p.loading || !p.hasMore) return;

		$.set(
			paging,
			{
				...$.get(paging),
				[name]: { hasMore: p.hasMore, loading: true }
			},
			true
		);

		const el = $.get(logEl);
		const prevH = el ? el.scrollHeight : 0;
		const prevTop = el ? el.scrollTop : 0;

		$.set(prepending, true);

		try {
			const oldestKey = keyOf(t.messages[0]);
			const r = await fetch(`wait?channel=${encodeURIComponent(name)}&before=${oldestKey}&tail=100`);
			const d = await r.json();

			if (!r.ok || !d.ok) throw new Error(d.error || "http " + r.status);

			const fresh = Array.isArray(d.messages) ? d.messages : [];

			if (fresh.length) {
				if (SRC_NATS) live.ingestSnapshot(name, fresh); else live.ingest(name, fresh);
			}

			$.set(
				paging,
				{
					...$.get(paging),
					[name]: { hasMore: !!d.has_more && fresh.length > 0, loading: false }
				},
				true
			);

			await tick();

			if (el) el.scrollTop = prevTop + (el.scrollHeight - prevH);
		} catch(e) {
			$.set(
				paging,
				{
					...$.get(paging),
					[name]: { hasMore: p.hasMore, loading: false }
				},
				true
			);

			live.sysLine("load older failed: " + (e.message || e));
		} finally {
			$.set(prepending, false);
		}
	}

	function jumpToLatest() {
		if ($.get(logEl)) $.get(logEl).scrollTop = $.get(logEl).scrollHeight;

		$.set(stuck, false);
		$.set(newWhileStuck, 0);
	}

	async function fetchPack() {
		const name = $.get(activeName);

		if ($.get(pack)?.loading) return;

		$.set(pack, { loading: true }, true);

		try {
			const r = await fetch(`pack?channel=${encodeURIComponent(name)}&q=${encodeURIComponent($.get(packQuery))}&budget=4000`);
			const d = await r.json();

			if (!r.ok || !d.ok) throw new Error(d.error || "http " + r.status);

			$.set(
				pack,
				{
					used: d.used_tokens_est,
					budget: d.budget_tokens,
					nMsgs: Array.isArray(d.messages) ? d.messages.length : 0,
					digestsTotal: d.digests_total,
					digests: Array.isArray(d.digests) ? d.digests : []
				},
				true
			);
		} catch(e) {
			$.set(pack, { error: e.message || String(e) }, true);
		}
	}

	function showTab(name) {
		$.set(pack, null);

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

	var fragment = root_17();
	var div = $.first_child(fragment);
	var header = $.child(div);
	var div_1 = $.sibling($.child(header), 2);
	var span = $.child(div_1);
	var span_1 = $.sibling(span, 2);
	var text_1 = $.only_child(span_1, true);
	var button = $.sibling(span_1, 2);
	var text_2 = $.only_child(button);

	$.reset(div_1);
	$.reset(header);

	var nav = $.sibling(header, 2);
	var div_2 = $.child(nav);
	var node = $.child(div_2);

	$.each(node, 16, () => Object.keys(live.tabs), (name) => name, ($$anchor, name) => {
		var div_3 = root_1();
		let classes;
		var span_2 = $.child(div_3);
		var text_3 = $.only_child(span_2);
		var node_1 = $.sibling(span_2, 2);

		{
			var consequent = ($$anchor) => {
				var button_1 = root();

				$.template_effect(() => {
					$.set_attribute(button_1, 'title', `close #${name}`);
					$.set_attribute(button_1, 'aria-label', `close #${name}`);
				});

				$.delegated('click', button_1, (e) => {
					e.stopPropagation();
					closeTab(name);
				});

				$.append($$anchor, button_1);
			};

			$.if(node_1, ($$render) => {
				if ($.get(tabCount) > 1) $$render(consequent);
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

	var button_2 = $.sibling(node, 2);

	$.reset(div_2);
	$.reset(nav);

	var div_4 = $.sibling(nav, 2);
	var node_2 = $.child(div_4);

	$.each(node_2, 17, () => live.sysLines, $.index, ($$anchor, s) => {
		var div_5 = root_2();
		var text_4 = $.only_child(div_5, true);

		$.template_effect(() => $.set_text(text_4, $.get(s)));
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
					var p_1 = $.sibling($.child(div_8), 2);
					var text_5 = $.only_child(p_1);

					$.next(2);
					$.reset(div_8);
					$.template_effect(() => $.set_text(text_5, `nothing on #${$.get(activeName) ?? ''} yet`));
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

	{
		var consequent_5 = ($$anchor) => {
			var div_9 = root_9();
			var node_6 = $.child(div_9);

			{
				var consequent_3 = ($$anchor) => {
					var span_3 = root_6();

					$.append($$anchor, span_3);
				};

				var consequent_4 = ($$anchor) => {
					var button_3 = root_7();

					$.delegated('click', button_3, loadOlder);
					$.append($$anchor, button_3);
				};

				var alternate_1 = ($$anchor) => {
					var span_4 = root_8();
					var text_6 = $.only_child(span_4);

					$.template_effect(() => $.set_text(text_6, `— beginning of #${$.get(activeName) ?? ''} —`));
					$.append($$anchor, span_4);
				};

				$.if(node_6, ($$render) => {
					if ($.get(page).loading) $$render(consequent_3); else if ($.get(page).hasMore) $$render(consequent_4, 1); else $$render(alternate_1, -1);
				});
			}

			$.reset(div_9);
			$.append($$anchor, div_9);
		};

		$.if(node_5, ($$render) => {
			if ($.get(active).messages.length > 0) $$render(consequent_5);
		});
	}

	var node_7 = $.sibling(node_5, 2);

	{
		var consequent_10 = ($$anchor) => {
			var div_10 = root_15();
			var div_11 = $.child(div_10);
			var button_4 = $.child(div_11);
			var text_7 = $.only_child(button_4, true);
			var input = $.sibling(button_4, 2);

			$.remove_input_defaults(input);

			var node_8 = $.sibling(input, 2);

			{
				var consequent_6 = ($$anchor) => {
					var fragment_2 = root_10();
					var span_5 = $.first_child(fragment_2);
					var text_8 = $.only_child(span_5);
					var button_5 = $.sibling(span_5, 2);

					$.template_effect(() => $.set_text(text_8, `~${$.get(pack).used ?? ''} of ${$.get(pack).budget ?? ''} tokens · ${$.get(pack).nMsgs ?? ''} messages kept · ${$.get(pack).digestsTotal ?? ''} pruned episodes`));
					$.delegated('click', button_5, () => $.set(pack, null));
					$.append($$anchor, fragment_2);
				};

				$.if(node_8, ($$render) => {
					if ($.get(pack) && !$.get(pack).loading && !$.get(pack).error) $$render(consequent_6);
				});
			}

			var node_9 = $.sibling(node_8, 2);

			{
				var consequent_7 = ($$anchor) => {
					var span_6 = root_11();
					var text_9 = $.only_child(span_6);

					$.template_effect(() => $.set_text(text_9, `pack failed: ${$.get(pack).error ?? ''}`));
					$.append($$anchor, span_6);
				};

				$.if(node_9, ($$render) => {
					if ($.get(pack)?.error) $$render(consequent_7);
				});
			}

			$.reset(div_11);

			var node_10 = $.sibling(div_11, 2);

			{
				var consequent_9 = ($$anchor) => {
					var div_12 = root_14();
					var node_11 = $.child(div_12);

					$.each(node_11, 17, () => $.get(pack).digests.slice(0, 12), (d) => d.episode, ($$anchor, d) => {
						var div_13 = root_12();
						var span_7 = $.child(div_13);
						var text_10 = $.only_child(span_7);
						var text_11 = $.sibling(span_7);

						$.reset(div_13);

						$.template_effect(
							($0, $1) => {
								$.set_attribute(div_13, 'title', `episode ${$.get(d).episode} · seq ${$.get(d).seq_first}–${$.get(d).seq_last}`);
								$.set_text(text_10, `#${$.get(d).episode ?? ''}`);
								$.set_text(text_11, ` · ${$.get(d).count ?? ''} msgs · ${$0 ?? ''} · ${$1 ?? ''}`);
							},
							[
								() => Object.entries($.get(d).senders).map(([s, n]) => n > 1 ? `${s}×${n}` : s).join(", "),
								() => $.get(d).terms.slice(0, 5).join(" · ")
							]
						);

						$.append($$anchor, div_13);
					});

					var node_12 = $.sibling(node_11, 2);

					{
						var consequent_8 = ($$anchor) => {
							var div_14 = root_13();
							var text_12 = $.only_child(div_14);

							$.template_effect(() => $.set_text(text_12, `…and ${$.get(pack).digests.length - 12} more digest spans (of ${$.get(pack).digestsTotal ?? ''} pruned episodes)`));
							$.append($$anchor, div_14);
						};

						$.if(node_12, ($$render) => {
							if ($.get(pack).digests.length > 12) $$render(consequent_8);
						});
					}

					$.reset(div_12);
					$.append($$anchor, div_12);
				};

				$.if(node_10, ($$render) => {
					if ($.get(pack)?.digests?.length) $$render(consequent_9);
				});
			}

			$.reset(div_10);

			$.template_effect(() => {
				button_4.disabled = $.get(pack)?.loading;
				$.set_text(text_7, $.get(pack)?.loading ? "packing…" : "📦 history pack");
			});

			$.delegated('click', button_4, fetchPack);

			$.delegated('keydown', input, (e) => {
				if (e.key === "Enter") {
					e.preventDefault();
					void fetchPack();
				}
			});

			$.bind_value(input, () => $.get(packQuery), ($$value) => $.set(packQuery, $$value));
			$.append($$anchor, div_10);
		};

		$.if(node_7, ($$render) => {
			if ($.get(active).messages.length > 0) $$render(consequent_10);
		});
	}

	var node_13 = $.sibling(node_7, 2);

	$.each(node_13, 19, () => $.get(active).messages, (m) => keyOf(m), ($$anchor, m, i) => {
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

	var node_14 = $.sibling(div_4, 2);

	{
		var consequent_11 = ($$anchor) => {
			var button_6 = root_16();
			var text_13 = $.sibling($.child(button_6));

			$.reset(button_6);

			$.template_effect(() => {
				$.set_attribute(button_6, 'aria-label', `jump to latest, ${$.get(newWhileStuck)} new messages`);
				$.set_text(text_13, ` ${$.get(newWhileStuck) ?? ''} new`);
			});

			$.delegated('click', button_6, jumpToLatest);
			$.append($$anchor, button_6);
		};

		$.if(node_14, ($$render) => {
			if ($.get(stuck) && $.get(newWhileStuck) > 0) $$render(consequent_11);
		});
	}

	var div_15 = $.sibling(node_14, 2);
	var div_16 = $.child(div_15);
	var textarea = $.child(div_16);

	$.remove_textarea_child(textarea);
	$.set_attribute(textarea, 'rows', 1);
	$.bind_this(textarea, ($$value) => $.set(msgEl, $$value), () => $.get(msgEl));

	var button_7 = $.sibling(textarea, 2);

	$.reset(div_16);
	$.next(2);
	$.reset(div_15);

	var footer = $.sibling(div_15, 2);
	var span_8 = $.child(footer);
	var text_14 = $.only_child(span_8);
	var span_9 = $.sibling(span_8, 2);
	var text_15 = $.only_child(span_9);

	$.reset(footer);
	$.reset(div);

	var node_15 = $.sibling(div, 2);

	{
		var consequent_12 = ($$anchor) => {
			AddChannelDialog($$anchor, { onClose: () => $.set(showDlg, false), onAdd: addTab });
		};

		$.if(node_15, ($$render) => {
			if ($.get(showDlg)) $$render(consequent_12);
		});
	}

	$.template_effect(
		($0) => {
			$.set_attribute(div_1, 'data-state', live.status);
			$.set_attribute(div_1, 'aria-label', `connection: ${$.get(connLabel)}`);
			$.set_class(span, 1, `dot ${$.get(dotClass) ?? ''}`);
			$.set_text(text_1, $.get(connLabel));

			$.set_attribute(button, 'title', SRC_NATS
				? "live via NATS+JetStream - click for file-feed websocket"
				: "live via file-feed websocket - click for NATS+JetStream");

			$.set_text(text_2, `src: ${SRC_NATS ? "nats" : "feed"}`);
			$.set_attribute(textarea, 'placeholder', `message #${$.get(activeName)}`);
			textarea.disabled = $.get(sending);
			button_7.disabled = $0;
			$.set_text(text_14, `seq ${($.get(active).cursor || "—") ?? ''}`);
			$.set_text(text_15, `${$.get(tabCount) ?? ''} channel${$.get(tabCount) === 1 ? "" : "s"}`);
		},
		[() => $.get(sending) || !$.get(draft).trim()]
	);

	$.delegated('click', button, () => {
		const u = new URL(location.href);

		if (SRC_NATS) u.searchParams.delete("src"); else u.searchParams.set("src", "nats");

		location.href = u.toString();
	});

	$.delegated('click', button_2, () => $.set(showDlg, true));
	$.event('scroll', div_4, onLogScroll);
	$.delegated('input', textarea, autogrow);

	$.delegated('keydown', textarea, (e) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			sendMsg();
		}
	});

	$.bind_value(textarea, () => $.get(draft), ($$value) => $.set(draft, $$value));
	$.delegated('click', button_7, sendMsg);
	$.append($$anchor, fragment);
	$.pop();
}

$.delegate(['click', 'keydown', 'input']);