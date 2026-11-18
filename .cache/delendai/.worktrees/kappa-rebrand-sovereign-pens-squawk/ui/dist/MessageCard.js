import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';
import { mdBlock } from "../markdown.js";

var root = $.from_html(`<span class="to-chip" title="direct message"> </span>`);
var root_1 = $.from_html(`<span class="badge unverified">unverified</span>`);
var root_2 = $.from_html(`<div class="msg-head"><span class="avatar" aria-hidden="true"> </span> <span class="who"> </span> <!> <span class="ts"> </span> <!></div>`);
var root_3 = $.from_html(`<span class="sealed"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg> sealed message — content hidden</span>`);
var root_4 = $.from_html(`<div><!> <div class="body"><!></div></div>`);

export default function MessageCard($$anchor, $$props) {
	$.push($$props, true);

	let compact = $.prop($$props, 'compact', 3, false);

	function fmtTime(ts, seq) {
		const t = ts ? new Date(ts) : new Date(seq);

		if (isNaN(t.getTime())) return "";

		return t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
	}

	function fullDate(ts, seq) {
		const t = ts ? new Date(ts) : new Date(seq);

		return isNaN(t.getTime()) ? undefined : t.toLocaleString();
	}

	/** deterministic avatar hue per sender (0-359) */
	function hueOf(name) {
		let h = 0;

		for (let i = 0; i < name.length; i++) h = h * 31 + name.charCodeAt(i) >>> 0;

		return h % 360;
	}

	let unverified = $.derived(() => !$$props.m.signature);
	let hue = $.derived(() => hueOf($$props.m.from || "?"));
	let initial = $.derived(() => (($$props.m.from || "?").trim().charAt(0) || "?").toUpperCase());
	let stamp = $.derived(() => fmtTime($$props.m.ts, $$props.m.seq));
	let full = $.derived(() => fullDate($$props.m.ts, $$props.m.seq));
	let dm = $.derived(() => $$props.m.to && $$props.m.to !== "all" ? $$props.m.to : "");
	var div = root_4();
	let classes;
	var node = $.child(div);

	{
		var consequent_2 = ($$anchor) => {
			var div_1 = root_2();
			var span = $.child(div_1);
			var text = $.only_child(span, true);
			var span_1 = $.sibling(span, 2);
			var text_1 = $.only_child(span_1, true);
			var node_1 = $.sibling(span_1, 2);

			{
				var consequent = ($$anchor) => {
					var span_2 = root();
					var text_2 = $.only_child(span_2);

					$.template_effect(() => $.set_text(text_2, `→ ${$.get(dm) ?? ''}`));
					$.append($$anchor, span_2);
				};

				$.if(node_1, ($$render) => {
					if ($.get(dm)) $$render(consequent);
				});
			}

			var span_3 = $.sibling(node_1, 2);
			var text_3 = $.only_child(span_3, true);
			var node_2 = $.sibling(span_3, 2);

			{
				var consequent_1 = ($$anchor) => {
					var span_4 = root_1();

					$.template_effect(() => $.set_attribute(span_4, 'title', `signature ${$$props.m.signature || "missing"} — treat the sender and text as unconfirmed`));
					$.append($$anchor, span_4);
				};

				$.if(node_2, ($$render) => {
					if ($.get(unverified)) $$render(consequent_1);
				});
			}

			$.reset(div_1);

			$.template_effect(() => {
				$.set_style(span, `--h:${$.get(hue) ?? ''}`);
				$.set_text(text, $.get(initial));
				$.set_text(text_1, $$props.m.from);
				$.set_attribute(span_3, 'title', $.get(full));
				$.set_text(text_3, $.get(stamp));
			});

			$.append($$anchor, div_1);
		};

		$.if(node, ($$render) => {
			if (!compact()) $$render(consequent_2);
		});
	}

	var div_2 = $.sibling(node, 2);
	var node_3 = $.child(div_2);

	{
		var consequent_3 = ($$anchor) => {
			var span_5 = root_3();

			$.append($$anchor, span_5);
		};

		var alternate = ($$anchor) => {
			var fragment = $.comment();
			var node_4 = $.first_child(fragment);

			$.html(node_4, () => mdBlock($$props.m.text));
			$.append($$anchor, fragment);
		};

		$.if(node_3, ($$render) => {
			if ($$props.m.sealed) $$render(consequent_3); else $$render(alternate, -1);
		});
	}

	$.reset(div_2);
	$.reset(div);

	$.template_effect(() => {
		classes = $.set_class(div, 1, 'msg', null, classes, { compact: compact() });
		$.set_attribute(div, 'title', compact() ? `${$$props.m.from} · ${$.get(stamp)}` : undefined);
	});

	$.append($$anchor, div);
	$.pop();
}