const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const assert = require("assert");
// Usage: node test.js [DIR]. By default, test the product pages in this checkout.
const dir = process.argv[2] ?? path.resolve(__dirname, "../../../../../docs/baseline_check");
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
const groupScores = () => [...d.querySelectorAll("#s2b li span")].map((score) => score.textContent).join(" · ");
const reportAs = (mode) => {
  $("reporter").value = mode;
  ev($("reporter"), "change");
};
let n = 0; const ok = (m) => { n++; console.log("PASS", m); };

// 1. nothing answered
for (const id of ["s1", "s2", "s3", "s4", "s6"]) assert.strictEqual(t(id), "–", id);
assert.strictEqual(groupScores(), "–/4 · –/6 · –/6 · –/7");
assert.ok(t("s2b").includes("Within the home"));
assert.match(t("unans"), /^4 of 4 required questions still unanswered \(Q4 and Q6 are optional\)/);
assert.strictEqual(d.querySelectorAll('input:checked').length, 0);
assert.strictEqual(d.querySelectorAll('#q2 input[type=checkbox]').length, 23);
const help = d.querySelector("#q2").closest("fieldset").querySelector(".help.self").textContent;
assert.ok(help.includes("tick the shorter one too"), "Q2 help explains nested items");
assert.ok(help.split(". ").length <= 3, "Q2 help is short");
assert.ok(t("q2").includes("Keep up all your usual responsibilities, with no days lost"));
assert.ok($("q4leg").textContent.includes("(optional)"));
ok("nothing answered: all dashes, 4 required unanswered, nothing pre-checked, 23 items, short Q2 help, Q4 optional: " + t("unans"));

// 2. None on group 1 -> 0
click($("none_1"));
assert.strictEqual(groupScores(), "–/4 · 0/6 · –/6 · –/7");
assert.strictEqual(t("s2"), "–");
assert.strictEqual(t("s2c"), "3 groups blank");
ok("One answered group shows a zero group score and a blank Q2 total");

// 3. All on group 0 -> 4/4, total 4
click($("all_0"));
assert.strictEqual($("all_0").getAttribute("aria-pressed"), "true");
assert.strictEqual(groupScores(), "4/4 · 0/6 · –/6 · –/7");
assert.strictEqual(t("s2"), "–");
ok("All on group 0 shows 4/4 and leaves the total blank");
// unticking one unpresses All
tick("q2_0", false);
assert.strictEqual($("all_0").getAttribute("aria-pressed"), "false");
assert.strictEqual(groupScores(), "3/4 · 0/6 · –/6 · –/7");
assert.strictEqual(t("s2"), "–");
ok("Unticking one home item unpresses All");

// 4. ticking an item unpresses None
tick("q2_4"); // first item of group 1
assert.strictEqual($("none_1").getAttribute("aria-pressed"), "false");
assert.strictEqual(groupScores(), "3/4 · 1/6 · –/6 · –/7");
ok("Ticking an item unpresses None");
// None again clears the group
click($("none_1"));
assert.strictEqual(groupScores(), "3/4 · 0/6 · –/6 · –/7");
ok("None clears ticked items");

// 5. Assisted self-report preserves the patient's answers and wording.
const visible = (sel) => [...d.querySelectorAll(sel)].filter((x) => !x.hidden).map((x) => x.textContent);
assert.ok(visible("#q2 .self").some((x) => x.includes("your own")));
reportAs("assisted");
assert.strictEqual(t("s5"), "Patient with help");
assert.strictEqual($("assisted-note").hidden, false);
assert.strictEqual(visible("#bc .proxy").length, 0);
assert.strictEqual(groupScores(), "3/4 · 0/6 · –/6 · –/7");
ok("Assisted self-report keeps patient wording and answers");

// 6. Q1 > 0 reveals triggers
assert.strictEqual($("q1t").hidden, true);
pick("q1", 0); assert.strictEqual($("q1t").hidden, true); assert.strictEqual(t("s1"), "0 / 7");
pick("q1", 2); assert.strictEqual($("q1t").hidden, false); assert.strictEqual(t("s1"), "2 / 7");
assert.strictEqual(d.querySelectorAll('#q1tc input').length, 8);
assert.ok(t("q1tc").includes("No clear reason") && !t("q1tc").includes("Don't know"));
const trigger = d.querySelector("#q1tc input");
click(trigger);
assert.ok(trigger.checked);
pick("q1", 0);
assert.ok($("q1t").hidden && $("q1t").disabled);
assert.ok(!new dom.window.FormData($("bc")).has("q1t"));
pick("q1", 2);
assert.ok(!$("q1t").disabled && !trigger.checked);
ok("Returning Q1 to zero clears and disables the trigger list");

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
assert.match(t("unans"), /^2 of 4/); // Q2 (2 groups blank) and Q3 open; Q1 and Q5 answered above; Q4 optional
pick("q3", 4);
assert.match(t("unans"), /^1 of 4/); // Q2 still has 2 blank groups
click($("none_2")); click($("none_3"));
assert.strictEqual(t("s2"), "3 / 23");
assert.strictEqual(t("unans"), "All 4 required questions answered."); // with Q4 still untouched
assert.strictEqual(t("s4"), "–");
s.dispatchEvent(new dom.window.Event("pointerup", { bubbles: true })); // a tap on the untouched slider counts as an answer
assert.strictEqual(t("s4"), "50%");
s.value = "65"; ev(s, "input");
assert.strictEqual(t("s3"), "4 / 10"); assert.strictEqual(t("s4"), "65%"); assert.strictEqual(t("q4v"), "65%");
assert.strictEqual(s.getAttribute("aria-valuetext"), "65%"); assert.ok(!s.hasAttribute("data-unset"));
assert.strictEqual(d.querySelectorAll('#q3 input').length, 11);
ok("Q3 chips (11); all required answered with Q4 untouched; Q4 slider 0–100 step 5, tap → 50%, drag → 65%");
click($("clear-q4"));
assert.strictEqual(s.value, "50");
assert.ok(s.hasAttribute("data-unset"));
assert.strictEqual(t("s4"), "–");
assert.strictEqual(t("q4v"), "Not answered yet");
assert.strictEqual(s.getAttribute("aria-valuetext"), "Not answered yet");
assert.strictEqual(t("unans"), "All 4 required questions answered.");
ok("Clearing Q4 restores the unanswered state");

// 8b. every Q2 group has an "All of these" button that ticks the whole group and can be undone
for (let g = 0; g < 4; g++) {
  const all = $("all_" + g), items = d.querySelectorAll(`#q2 input[data-g="${g}"]`);
  assert.ok(all, "group " + g + " has no All of these button");
  click(all);
  assert.ok([...items].every((x) => x.checked), "All of these ticks group " + g);
  assert.strictEqual(all.getAttribute("aria-pressed"), "true"); assert.strictEqual($("none_" + g).getAttribute("aria-pressed"), "false");
}
assert.strictEqual(t("s2"), "23 / 23"); assert.strictEqual(groupScores(), "4/4 · 6/6 · 6/6 · 7/7");
click($("all_3"));
assert.strictEqual(t("s2"), "–"); assert.strictEqual(groupScores(), "4/4 · 6/6 · 6/6 · –/7");
assert.strictEqual(t("s2c"), "1 group blank");
assert.strictEqual($("all_3").getAttribute("aria-pressed"), "false");
ok("Completing all groups shows the total. Clearing one group hides it.");
for (let g = 0; g < 4; g++) click($("none_" + g));
assert.strictEqual(t("s2"), "0 / 23");
ok("Explicit zero in all four groups gives a complete zero score");

// Changing who supplies answers requires a fresh check.
$("q6").value = "Test note";
s.value = "35";
ev(s, "input");
dom.window.confirm = () => false;
reportAs("proxy");
assert.strictEqual($("reporter").value, "assisted");
assert.strictEqual(t("s2"), "0 / 23");
assert.strictEqual($("q6").value, "Test note");
dom.window.confirm = () => true;
reportAs("proxy");
assert.strictEqual(t("s5"), "Carer (proxy)");
assert.ok(visible("#bc legend .proxy")[0].includes("were they in a crash or flare"));
assert.ok(visible("#q2 .proxy").some((x) => x.includes("on their own")));
assert.ok(visible("#q6leg .proxy").some((x) => x.includes("for them")));
assert.strictEqual(visible("#bc .self").length, 0);
assert.strictEqual($("q6").value, "");
assert.strictEqual(groupScores(), "–/4 · –/6 · –/6 · –/7");
for (const id of ["s1", "s2", "s3", "s4", "s6"]) assert.strictEqual(t(id), "–", id);
pick("q1", 2);
reportAs("patient");
assert.strictEqual(t("s5"), "Patient");
assert.strictEqual(t("s1"), "–");
assert.strictEqual(visible("#bc .proxy").length, 0);
ok("Changing between patient and proxy starts a fresh check or keeps existing answers if canceled");

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
  assert.strictEqual(doc.compatMode, "CSS1Compat", name);
  assert.strictEqual(doc.documentElement.lang, "en", name);
  assert.ok(doc.querySelector('meta[name="viewport"]'), name);
  assert.ok(doc.title.includes("v0.3.1"), name);
  assert.strictEqual(doc.querySelector("blockquote, q"), null, name);
  assert.strictEqual(doc.querySelector('nav a[aria-current="page"]').getAttribute("href"), name, name + " nav");
  for (const a of doc.querySelectorAll("a[href]")) {
    const [target, hash] = a.getAttribute("href").split("#");
    if (/^[a-z]+:/.test(target)) continue;
    const file = target || name;
    assert.ok(pages[file], `${name} links to missing page ${file}`);
    if (hash) assert.ok(pages[file].getElementById(hash), `${name} links to missing #${hash} in ${file}`);
    links++;
  }
}
ok(`All ${links} local links resolve across the three v0.3.1 pages`);
console.log(`\n${n} checks passed`);
