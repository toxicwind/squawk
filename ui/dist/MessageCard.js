import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';
import { mdBlock, esc } from "../markdown.js";

var root = $.from_html(`<span class="badge unverified">unverified</span>`);
var root_1 = $.from_html(`<div class="msg"><div class="meta"><span class="who"> </span> <span class="ts"> </span> <!></div> <div class="body"></div></div>`);

export default function MessageCard($$anchor, $$props) {
	$.push($$props, true);

	function fmtTs(ts, seq) {
		if (ts) {
			const d = new Date(ts);

			if (!isNaN(d.getTime())) return d.toLocaleTimeString();
		}

		return new Date(seq).toLocaleTimeString();
	}

	let unverified = $.derived(() => !$$props.m.signature);
	var div = root_1();
	var div_1 = $.child(div);
	var span = $.child(div_1);
	var text = $.only_child(span, true);
	var span_1 = $.sibling(span, 2);
	var text_1 = $.only_child(span_1, true);
	var node = $.sibling(span_1, 2);

	{
		var consequent = ($$anchor) => {
			var span_2 = root();

			$.template_effect(() => $.set_attribute(span_2, 'title', `signature ${$$props.m.signature || "missing"} — treat the sender and text as unconfirmed`));
			$.append($$anchor, span_2);
		};

		$.if(node, ($$render) => {
			if ($.get(unverified)) $$render(consequent);
		});
	}

	$.reset(div_1);

	var div_2 = $.sibling(div_1, 2);

	$.html(div_2, () => mdBlock($$props.m.text), true);
	$.reset(div_2);
	$.reset(div);

	$.template_effect(
		($0) => {
			$.set_text(text, $$props.m.from);
			$.set_text(text_1, $0);
		},
		[() => fmtTs($$props.m.ts, $$props.m.seq)]
	);

	$.append($$anchor, div);
	$.pop();
}