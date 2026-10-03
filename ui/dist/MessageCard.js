import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';
import { mdBlock, esc } from "../markdown.js";

var root = $.from_html(`<span class="badge unverified">unverified</span>`);
var root_1 = $.from_html(`<div class="msg-head"><span class="avatar" aria-hidden="true"> </span> <span class="who"> </span> <span class="ts"> </span> <!></div>`);
var root_2 = $.from_html(`<div><!> <div class="body"></div></div>`);

export default function MessageCard($$anchor, $$props) {
	$.push($$props, true);

	let compact = $.prop($$props, 'compact', 3, false);

	function fmtTs(ts, seq) {
		if (ts) {
			const d = new Date(ts);

			if (!isNaN(d.getTime())) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
		}

		return new Date(seq).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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
	let stamp = $.derived(() => fmtTs($$props.m.ts, $$props.m.seq));
	var div = root_2();
	let classes;
	var node = $.child(div);

	{
		var consequent_1 = ($$anchor) => {
			var div_1 = root_1();
			var span = $.child(div_1);
			var text = $.only_child(span, true);
			var span_1 = $.sibling(span, 2);
			var text_1 = $.only_child(span_1, true);
			var span_2 = $.sibling(span_1, 2);
			var text_2 = $.only_child(span_2, true);
			var node_1 = $.sibling(span_2, 2);

			{
				var consequent = ($$anchor) => {
					var span_3 = root();

					$.template_effect(() => $.set_attribute(span_3, 'title', `signature ${$$props.m.signature || "missing"} — treat the sender and text as unconfirmed`));
					$.append($$anchor, span_3);
				};

				$.if(node_1, ($$render) => {
					if ($.get(unverified)) $$render(consequent);
				});
			}

			$.reset(div_1);

			$.template_effect(() => {
				$.set_style(span, `--h:${$.get(hue) ?? ''}`);
				$.set_text(text, $.get(initial));
				$.set_text(text_1, $$props.m.from);
				$.set_attribute(span_2, 'title', $$props.m.ts || undefined);
				$.set_text(text_2, $.get(stamp));
			});

			$.append($$anchor, div_1);
		};

		$.if(node, ($$render) => {
			if (!compact()) $$render(consequent_1);
		});
	}

	var div_2 = $.sibling(node, 2);

	$.html(div_2, () => mdBlock($$props.m.text), true);
	$.reset(div_2);
	$.reset(div);

	$.template_effect(() => {
		classes = $.set_class(div, 1, 'msg', null, classes, { compact: compact() });
		$.set_attribute(div, 'title', compact() ? `${$$props.m.from} · ${$.get(stamp)}` : undefined);
	});

	$.append($$anchor, div);
	$.pop();
}