import 'svelte/internal/disclose-version';
import * as $ from 'svelte/internal/client';

var root = $.from_html(`<div class="dlg-err" role="alert"> </div>`);
var root_1 = $.from_html(`<div id="dlg-back" role="presentation"><div id="dlg" role="dialog" aria-modal="true" aria-label="add channel"><p class="dlg-title">new channel</p> <p class="dlg-sub">tune into another feed</p> <input placeholder="channel name" aria-label="channel name" autocapitalize="none" spellcheck="false"/> <!> <div class="row"><button class="btn ghost">cancel</button> <button class="btn primary">add channel</button></div></div></div>`);

export default function AddChannelDialog($$anchor, $$props) {
	$.push($$props, true);

	const VALID_NAME = /^[a-z0-9-_]{1,32}$/;
	let name = $.state("");
	let err = $.state("");
	let inputEl = $.state(null);

	$.user_effect(() => {
		$.get(inputEl)?.focus();
	});

	function submit() {
		const n = $.get(name).trim().toLowerCase();

		if (!VALID_NAME.test(n)) {
			$.set(err, "channel names are 1-32 chars: a-z 0-9 - _");

			return;
		}

		$$props.onAdd(n);
	}

	var div = root_1();
	var div_1 = $.child(div);
	var input = $.sibling($.child(div_1), 4);

	$.remove_input_defaults(input);
	$.bind_this(input, ($$value) => $.set(inputEl, $$value), () => $.get(inputEl));

	var node = $.sibling(input, 2);

	{
		var consequent = ($$anchor) => {
			var div_2 = root();
			var text = $.only_child(div_2, true);

			$.template_effect(() => $.set_text(text, $.get(err)));
			$.append($$anchor, div_2);
		};

		$.if(node, ($$render) => {
			if ($.get(err)) $$render(consequent);
		});
	}

	var div_3 = $.sibling(node, 2);
	var button = $.child(div_3);
	var button_1 = $.sibling(button, 2);

	$.reset(div_3);
	$.reset(div_1);
	$.reset(div);

	$.delegated('click', div, (e) => {
		if (e.target === e.currentTarget) $$props.onClose();
	});

	$.delegated('keydown', div, (e) => {
		if (e.key === "Escape") $$props.onClose();
	});

	$.delegated('input', input, () => $.set(err, ""));

	$.delegated('keydown', input, (e) => {
		if (e.key === "Enter") submit();
	});

	$.bind_value(input, () => $.get(name), ($$value) => $.set(name, $$value));

	$.delegated('click', button, function (...$$args) {
		$$props.onClose?.apply(this, $$args);
	});

	$.delegated('click', button_1, submit);
	$.append($$anchor, div);
	$.pop();
}

$.delegate(['click', 'keydown', 'input']);