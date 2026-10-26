// ui/markdown.test.ts — bun test suite for the Svelte UI markdown renderer.
// The Python feed renderer got its fixture matrix in e476d8d; this is the
// TS renderer's half: the Sept feature set (headings, lists, quotes, code,
// links, full bodies), first-class raw HTML/CSS passthrough, and the
// 2026-10-19 fix regressions (link &-double-escape, split blockquotes,
// missing image syntax).
import { describe, expect, test } from "bun:test";
import { mdBlock, mdInline, esc, safeHref } from "./markdown";

describe("inline", () => {
  test("bold and italic", () => {
    expect(mdInline("a **bold** b")).toContain("<strong>bold</strong>");
    expect(mdInline("a *italic* b")).toContain("<em>italic</em>");
  });
  test("inline code protects markdown chars", () => {
    expect(mdInline("use `a **not bold** b` here")).toBe(
      "use <code>a **not bold** b</code> here");
  });
  test("plain digits are not sentinel-corrupted", () => {
    expect(mdInline("task 1792426 done in 3 steps")).toBe(
      "task 1792426 done in 3 steps");
  });
  test("html in text is escaped", () => {
    expect(mdInline("1 < 2 & \"q\"")).toBe("1 &lt; 2 &amp; &quot;q&quot;");
  });
  test("link renders with target/rel", () => {
    expect(mdInline("[x](https://a.io/p)")).toBe(
      '<a href="https://a.io/p" target="_blank" rel="noopener">x</a>');
  });
  test("REGRESSION: link query & is escaped exactly once", () => {
    const out = mdInline("[x](https://a.io/?b=1&c=2)");
    expect(out).toContain('href="https://a.io/?b=1&amp;c=2"');
    expect(out).not.toContain("&amp;amp;");
  });
  test("scriptable schemes are blocked", () => {
    expect(safeHref("javascript:alert(1)")).toBe("#blocked");
    expect(safeHref(" data:text/html,x")).toBe("#blocked");
    expect(mdInline("[x](javascript:alert(1))")).toContain('href="#blocked"');
  });
  test("REGRESSION: image syntax renders an img, not bang+link", () => {
    const out = mdInline("![alt text](https://a.io/pic.png)");
    expect(out).toBe('<img src="https://a.io/pic.png" alt="alt text" loading="lazy">');
  });
  test("image src query & escaped exactly once", () => {
    expect(mdInline("![a](https://a.io/p?x=1&y=2)")).toContain("?x=1&amp;y=2");
  });
});

describe("block", () => {
  test("headings", () => {
    expect(mdBlock("# Title")).toBe("<h1>Title</h1>");
    expect(mdBlock("### Sub *em*")).toBe("<h3>Sub <em>em</em></h3>");
  });
  test("paragraph lines join with <br>, blank line splits", () => {
    expect(mdBlock("one\ntwo\n\nthree")).toBe("<p>one<br>two</p><p>three</p>");
  });
  test("fenced code escapes html and ignores markdown", () => {
    expect(mdBlock("```\n<b>**x**</b>\n```")).toBe(
      "<pre><code>&lt;b&gt;**x**&lt;/b&gt;</code></pre>");
  });
  test("unterminated fence still flushes at end", () => {
    expect(mdBlock("```\ncode")).toBe("<pre><code>code</code></pre>");
  });
  test("unordered and ordered lists, switching closes the first", () => {
    expect(mdBlock("- a\n- b")).toBe("<ul><li>a</li><li>b</li></ul>");
    expect(mdBlock("- a\n1. b")).toBe("<ul><li>a</li></ul><ol><li>b</li></ol>");
  });
  test("REGRESSION: consecutive quote lines merge into one blockquote", () => {
    expect(mdBlock("> line one\n> line two")).toBe(
      "<blockquote>line one<br>line two</blockquote>");
  });
  test("quote ends at blank line and at paragraph", () => {
    expect(mdBlock("> q\n\npara")).toBe("<blockquote>q</blockquote><p>para</p>");
    expect(mdBlock("> q\npara")).toBe("<blockquote>q</blockquote><p>para</p>");
  });
  test("raw single-line html passes through untouched", () => {
    expect(mdBlock('<div class="x">hi</div>')).toBe('<div class="x">hi</div>\n');
  });
  test("raw multi-line block passes through until its close tag", () => {
    const src = "<style>\n.a { color: red; }\n</style>\nafter";
    const out = mdBlock(src);
    expect(out).toContain(".a { color: red; }");
    expect(out).toContain("<p>after</p>");
  });
  test("raw html inside a markdown line is escaped, not passed", () => {
    expect(mdBlock("text <b>bold?</b>")).toBe(
      "<p>text &lt;b&gt;bold?&lt;/b&gt;</p>");
  });
  test("long body renders in full (no truncation)", () => {
    const body = "word ".repeat(3000).trim(); // ~15k chars, past every old cap
    const out = mdBlock(body);
    expect(out.length).toBeGreaterThan(14000);
    expect(out).toContain("word");
  });
  test("esc escapes all five attribute chars it owns", () => {
    expect(esc('<a & "b">')).toBe("&lt;a &amp; &quot;b&quot;&gt;");
  });
});
