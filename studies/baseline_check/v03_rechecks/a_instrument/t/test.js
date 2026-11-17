const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const assert = require("assert");
// usage: node test.js DIR, where DIR holds index.html (the quiz), methodology.html and blog.html
const dir = process.argv[2];
const read = (f) => fs.readFileSync(path.join(dir, f), "utf8");
const html = read("index.html");
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
ok("nothing answered: all dashes, 5 unanswered, nothing pre-checked, 23 items: " + t("s2b") + " | " + t("unans"));

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

// 8. Q3 chips; Q4 is a 0-100 slider in steps of 5 that stays unanswered until it is moved or tapped
const s = $("q4");
assert.deepStrictEqual([s.type, s.min, s.max, s.step], ["range", "0", "100", "5"]);
assert.ok(s.hasAttribute("data-unset")); assert.strictEqual(t("s4"), "–");
assert.strictEqual(t("q4v"), "Not answered yet"); assert.strictEqual(s.getAttribute("aria-valuetext"), "Not answered yet");
assert.match(t("unans"), /^3 of 5/); // Q2 (2 groups blank), Q3 and Q4 still open; Q1 and Q5 answered above
pick("q3", 4);
s.dispatchEvent(new dom.window.Event("pointerup", { bubbles: true })); // a tap on the untouched slider counts as an answer
assert.strictEqual(t("s4"), "50%");
s.value = "65"; ev(s, "input");
assert.strictEqual(t("s3"), "4 / 10"); assert.strictEqual(t("s4"), "65%"); assert.strictEqual(t("q4v"), "65%");
assert.strictEqual(s.getAttribute("aria-valuetext"), "65%"); assert.ok(!s.hasAttribute("data-unset"));
assert.match(t("unans"), /^1 of 5/); // Q2 still has 2 blank groups
click($("none_2")); click($("none_3"));
assert.strictEqual(t("unans"), "All 5 questions answered.");
assert.strictEqual(d.querySelectorAll('#q3 input').length, 11);
ok("Q3 chips (11); Q4 slider 0–100 step 5, unanswered until touched, tap → 50%, drag → 65%: " + t("unans"));

// 8b. every Q2 group has an "All of these" button that ticks the whole group and can be undone
for (let g = 0; g < 4; g++) {
  const all = $("all_" + g), items = d.querySelectorAll(`#q2 input[data-g="${g}"]`);
  assert.ok(all, "group " + g + " has no All of these button");
  click(all);
  assert.ok([...items].every((x) => x.checked), "All of these ticks group " + g);
  assert.strictEqual(all.getAttribute("aria-pressed"), "true"); assert.strictEqual($("none_" + g).getAttribute("aria-pressed"), "false");
}
assert.strictEqual(t("s2"), "23 / 23"); assert.strictEqual(t("s2b"), "4/4 · 6/6 · 6/6 · 7/7");
click($("all_3"));
assert.strictEqual(t("s2"), "16 / 23"); assert.strictEqual(t("s2b"), "4/4 · 6/6 · 6/6 · –/7"); // cleared = unanswered, not 0
assert.strictEqual(t("s2c"), "1 group blank");
assert.strictEqual($("all_3").getAttribute("aria-pressed"), "false");
ok("All of these on each of the 4 groups: 23 / 23; pressing the last again clears it to blank: " + t("s2b"));

// 9. every question is a fieldset with a legend
assert.strictEqual(d.querySelectorAll("#bc fieldset.q").length, 6);
for (const f of d.querySelectorAll("#bc fieldset.q")) assert.ok(f.querySelector(":scope > legend"));
assert.strictEqual(d.querySelectorAll('#q2 [role=group][aria-labelledby]').length, 4);
ok("6 question fieldsets with legends; 4 labelled Q2 groups");

// 10. the item counts written out in the methodology scoring rules match the quiz
const groups = [...d.querySelectorAll('#q2 [role=group]')].map((g) =>
  [g.querySelector(".gname").firstChild.textContent.trim(), g.querySelectorAll("input[type=checkbox]").length]);
const total = groups.reduce((s, [, k]) => s + k, 0), top2 = groups.slice(-2).reduce((s, [, k]) => s + k, 0);
const method = new JSDOM(read("methodology.html")).window.document;
const rules = method.getElementById("scoring").textContent.replace(/\s+/g, " ");
const ranges = groups.map(([g, k]) => `${g.toLowerCase()} 0–${k}`).join(", ");
for (const s of [`(0–${total})`, `Report the ${groups.length} Q2 group scores`, `(${ranges})`, `top two groups (${top2} items)`])
  assert.ok(rules.includes(s), "methodology scoring is missing: " + s);
ok(`methodology scoring matches the quiz: ${total} items, ${groups.length} groups, top two ${top2}`);

// 11. every link between the three pages points at a page (and anchor) that exists, and each page marks itself in the nav
const pages = { "index.html": d, "methodology.html": method, "blog.html": new JSDOM(read("blog.html")).window.document };
let links = 0;
for (const [name, doc] of Object.entries(pages)) {
  assert.strictEqual(doc.querySelector('nav a[aria-current="page"]').getAttribute("href"), name, name + " nav");
  for (const a of doc.querySelectorAll("a[href]")) {
    const [file, hash] = a.getAttribute("href").split("#");
    if (/^[a-z]+:/.test(file)) continue;
    assert.ok(pages[file], `${name} links to missing page ${file}`);
    if (hash) assert.ok(pages[file].getElementById(hash), `${name} links to missing #${hash} in ${file}`);
    links++;
  }
}
ok(`${links} links between the 3 pages all resolve; each page marks itself in the nav`);
console.log(`\n${n} checks passed`);
