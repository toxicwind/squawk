/** Markdown renderer with FIRST-CLASS raw HTML/CSS passthrough.
 * Block-level raw HTML (lines starting with <tag) passes through untouched.
 * Standard markdown: headers, code fences, inline code, bold, italic,
 * links, lists, blockquotes, paragraphs. Output is an HTML string.
 * Callers must trust the source (server-auth'd local feed).
 */

const RAW_OPEN = /^<(div|span|section|article|style|details|summary|table|pre|img|a|p|h[1-6]|ul|ol|li|br|hr|button|input)[\s>]/i;
const RAW_CLOSE = /^<\s*\/\s*(div|span|section|article|style|details|summary|table)\s*>/i;

export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const SENT = "⁠"; // sentinel char: \u2060 WORD JOINER, survives esc(), never in real text

export function mdInline(src: string): string {
  const codes: string[] = [];
  let out = src.replace(/`([^`\n]+)`/g, (_m, c) => {
    codes.push(c);
    return SENT + (codes.length - 1) + SENT;
  });
  out = esc(out);
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*\w])\*([^*]+)\*/g, "$1<em>$2</em>");
  out = out.replace(/\[([^\]\n]+)\]\(([^)\s\n]+)\)/g, (_m, t, u) =>
    `<a href="${u}" target="_blank" rel="noopener">${t}</a>`);
  const re = new RegExp(SENT + "(\\d+)" + SENT, "g");
  out = out.replace(re, (_m, i) => `<code>${esc(codes[+i])}</code>`);
  return out;
}

export function mdBlock(src: string): string {
  const lines = src.split("\n");
  let html = "";
  let para: string[] = [];
  let list: string | null = null;
  let inCode = false;
  let inRaw: string | null = null;
  let codeBuf: string[] = [];

  const flushP = () => {
    if (para.length) {
      html += "<p>" + para.map(mdInline).join("<br>") + "</p>";
      para = [];
    }
  };
  const closeL = () => {
    if (list) {
      html += "</" + list + ">";
      list = null;
    }
  };
  const rawClose = (tag: string) => new RegExp("<\\/\\s*" + tag + "\\s*>", "i");

  for (const ln of lines) {
    if (/^```/.test(ln)) {
      flushP();
      closeL();
      if (inCode) {
        html += `<pre><code>${esc(codeBuf.join("\n"))}</code></pre>`;
        codeBuf = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(ln);
      continue;
    }
    if (inRaw) {
      html += ln + "\n";
      if (rawClose(inRaw).test(ln)) inRaw = null;
      continue;
    }
    const rawOpen = ln.match(RAW_OPEN);
    if (rawOpen && !rawClose(rawOpen[1]).test(ln)) {
      // multi-line raw block: pass through until the closing tag
      flushP();
      closeL();
      inRaw = rawOpen[1].toLowerCase();
      html += ln + "\n";
      continue;
    }
    if (RAW_OPEN.test(ln) || RAW_CLOSE.test(ln) || /^<(br|hr|img)[\s>]/i.test(ln)) {
      // single-line raw html
      flushP();
      closeL();
      html += ln + "\n";
      continue;
    }
    const h = ln.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushP();
      closeL();
      html += `<h${h[1].length}>${mdInline(h[2])}</h${h[1].length}>`;
      continue;
    }
    const bq = ln.match(/^>\s?(.*)$/);
    if (bq) {
      flushP();
      closeL();
      html += `<blockquote>${mdInline(bq[1])}</blockquote>`;
      continue;
    }
    const ul = ln.match(/^[-*]\s+(.*)$/);
    const ol = ln.match(/^\d+[.)]\s+(.*)$/);
    if (ul || ol) {
      flushP();
      const t = ul ? "ul" : "ol";
      if (list !== t) {
        closeL();
        html += `<${t}>`;
        list = t;
      }
      html += `<li>${mdInline((ul || ol)![1])}</li>`;
      continue;
    }
    if (/^\s*$/.test(ln)) {
      flushP();
      closeL();
      continue;
    }
    para.push(ln);
  }
  flushP();
  closeL();
  if (inCode) html += `<pre><code>${esc(codeBuf.join("\n"))}</code></pre>`;
  return html;
}
