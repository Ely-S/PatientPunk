const { JSDOM } = require("jsdom");
const fs = require("fs");
const assert = require("assert");
const html = fs.readFileSync(process.argv[2], "utf8");
const dom = new JSDOM(html, { runScripts: "dangerously" });
const d = dom.window.document;
const $ = (id) => d.getElementById(id);
const ev = (el, t) => el.dispatchEvent(new dom.window.Event(t, { bubbles: true }));
const click = (el) => el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
const pick = (name, value) => { const x = d.querySelector(`input[name="${name}"][value="${value}"]`); x.checked = true; ev(x, "change"); };
const tick = (id, on = true) => { const x = $(id); x.checked = on; ev(x, "change"); };
const t = (id) => $(id).textContent;
let n = 0; const ok = (m) => { n++; console.log("PASS", m); };

// 1. nothing answered
for (const id of ["s1", "s2", "s3", "s4", "s6"]) assert.strictEqual(t(id), "–", id);
assert.strictEqual(t("s2b"), "–/4 · –/6 · –/6 · –/7");
assert.match(t("unans"), /^5 of 5 questions still unanswered/);
assert.strictEqual(d.querySelectorAll('input:checked').length, 0);
assert.strictEqual(d.querySelectorAll('#q2 input[type=checkbox]').length, 23);
assert.strictEqual(d.querySelector('[data-count="total"]').textContent, "23");
assert.strictEqual(d.querySelector('[data-count="top2"]').textContent, "13");
ok("nothing answered: all dashes, 5 unanswered, nothing pre-checked, 23 items, counts filled: " + t("s2b") + " | " + t("unans"));

// 2. None on group 1 -> 0
click($("none_1"));
assert.strictEqual(t("s2b"), "–/4 · 0/6 · –/6 · –/7"); assert.strictEqual(t("s2"), "0 / 23"); assert.strictEqual(t("s2c"), "3 groups blank");
ok("None on group 1: " + t("s2") + " | " + t("s2b") + " | " + t("s2c"));

// 3. All on group 0 -> 4/4, total 4
click($("all_0"));
assert.strictEqual($("all_0").getAttribute("aria-pressed"), "true");
assert.strictEqual(t("s2b"), "4/4 · 0/6 · –/6 · –/7"); assert.strictEqual(t("s2"), "4 / 23");
ok("All on group 0: " + t("s2") + " | " + t("s2b"));
// unticking one unpresses All
tick("q2_0", false);
assert.strictEqual($("all_0").getAttribute("aria-pressed"), "false"); assert.strictEqual(t("s2"), "3 / 23");
ok("unticking one home item unpresses All: " + t("s2"));

// 4. ticking an item unpresses None
tick("q2_4"); // first item of group 1
assert.strictEqual($("none_1").getAttribute("aria-pressed"), "false");
assert.strictEqual(t("s2b"), "3/4 · 1/6 · –/6 · –/7");
ok("ticking an item unpresses None: " + t("s2b"));
// None again clears the group
click($("none_1")); assert.strictEqual(t("s2b"), "3/4 · 0/6 · –/6 · –/7");
ok("None clears ticked items: " + t("s2b"));

// 5. proxy toggle swaps text
const visible = (sel) => [...d.querySelectorAll(sel)].filter((x) => !x.hidden).map((x) => x.textContent);
assert.ok(visible("#q2 .self").some((x) => x.includes("your own")));
const p = $("proxy"); p.checked = true; ev(p, "change");
assert.strictEqual(t("s5"), "Carer (proxy)");
assert.ok(visible("#bc legend .proxy")[0].includes("were they in a crash or flare"));
assert.ok(visible("#q2 .proxy").some((x) => x.includes("on their own")));
assert.strictEqual(visible("#bc .self").length, 0);
ok("proxy toggle: " + visible("#bc legend .proxy")[0] + " | item: " + visible("#q2 .proxy")[0]);
p.checked = false; ev(p, "change"); assert.strictEqual(visible("#bc .proxy").length, 0);
ok("proxy off restores self wording");

// 6. Q1 > 0 reveals triggers
assert.strictEqual($("q1t").hidden, true);
pick("q1", 0); assert.strictEqual($("q1t").hidden, true); assert.strictEqual(t("s1"), "0 / 7");
pick("q1", 2); assert.strictEqual($("q1t").hidden, false); assert.strictEqual(t("s1"), "2 / 7");
assert.strictEqual(d.querySelectorAll('#q1tc input').length, 8);
ok("Q1=0 keeps triggers hidden; Q1=2 reveals 8 triggers: " + t("s1"));

// 7. Q5 No earlier check -> missing
pick("q5", "none"); assert.strictEqual(t("s6"), "Missing (first check)");
pick("q5", "1"); assert.strictEqual(t("s6"), "A little better");
pick("q5", "none");
ok("Q5 'No earlier check' shows: " + t("s6"));

// 8. Q3/Q4 chips, unanswered count down to 0
pick("q3", 4); pick("q4", 60);
assert.strictEqual(t("s3"), "4 / 10"); assert.strictEqual(t("s4"), "60%");
assert.match(t("unans"), /^1 of 5/); // Q2 still has 2 blank groups
click($("none_2")); click($("none_3"));
assert.strictEqual(t("unans"), "All 5 questions answered.");
assert.strictEqual(d.querySelectorAll('#q3 input').length, 11); assert.strictEqual(d.querySelectorAll('#q4 input').length, 11);
assert.strictEqual(d.querySelectorAll('input[type=range]').length, 0);
ok("Q3/Q4 chips (11 each, no sliders): " + t("s3") + ", " + t("s4") + " | " + t("unans"));

// 9. every question is a fieldset with a legend
assert.strictEqual(d.querySelectorAll("#bc fieldset.q").length, 6);
for (const f of d.querySelectorAll("#bc fieldset.q")) assert.ok(f.querySelector(":scope > legend"));
assert.strictEqual(d.querySelectorAll('#q2 [role=group][aria-labelledby]').length, 4);
ok("6 question fieldsets with legends; 4 labelled Q2 groups");
console.log(`\n${n} checks passed`);
