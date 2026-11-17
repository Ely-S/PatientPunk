
(function () {
  // Each item: [label, hint, proxyLabel?, proxyHint?]. The first group gets an "All of these" button.
  const GROUPS = [
    ["Within the home", [
      ["Get to the toilet on your own", "walking or with an aid", "Get to the toilet on their own"],
      ["Brush your teeth or wash your face", "sitting or standing", "Brush their teeth or wash their face"],
      ["Hold a phone or tablet to read a message", "propped up is fine"],
      ["Have a 5-minute conversation", "in person or by phone"]]],
    ["Everyday basics", [
      ["Sit up for most of the day", "or in a supported chair"],
      ["Shower or bathe", "standing or seated"],
      ["Make a simple meal", "e.g. toast, a sandwich"],
      ["Have a 30-minute conversation", "in person, phone or video"],
      ["Read or watch something for 30 minutes", "and follow it"],
      ["Leave the house", "for any reason"]]],
    ["Getting out and keeping up", [
      ["Walk for 15 minutes outside", "at your own pace", null, "at their own pace"],
      ["Stand for 20 minutes", "e.g. queueing, cooking at the stove"],
      ["Do household chores", "e.g. laundry, cleaning, cooking a full meal"],
      ["Go grocery shopping or run errands", "in person"],
      ["See friends or family for an hour or more", "outside your home", null, "outside their home"],
      ["Work, study or volunteer for half a day", "about 4 hours, any setting"]]],
    ["Full days and beyond", [
      ["Do light exercise on purpose", "e.g. gentle swim, yoga, easy bike ride"],
      ["Walk for 45 minutes or more", "in one go"],
      ["Do 3 or more hours of focused mental work", "e.g. reading, screens, planning, paperwork"],
      ["Do a full day of work, study or caring", "about 8 hours of demanding tasks, without needing to lie down"],
      ["Go out for an evening or an outing of 3+ hours", "e.g. dinner, an event, a day trip, time outdoors"],
      ["Keep up your usual responsibilities on every day you're counting, with no days lost", "work, study, caring or running a home",
       "Keep up their usual responsibilities on every day you're counting, with no days lost"],
      ["Be as physically active as before you got sick", "your old exercise, sport or physical job",
       "Be as physically active as before they got sick", "their old exercise, sport or physical job"]]]
  ];
  const TOTAL = GROUPS.reduce((n, g) => n + g[1].length, 0);
  const TRIGGERS = ["Physical activity", "Mental effort", "Emotional stress", "Sensory overload", "Infection", "Treatment or procedure", "Menstrual cycle", "Don't know"];
  const CHANGE = ["Much worse", "Worse", "A little worse", "About the same", "A little better", "Better", "Much better"];
  const DASH = "–";
  const $ = (id) => document.getElementById(id);
  const both = (s, p) => p ? `<span class="self">${s}</span><span class="proxy" hidden>${p}</span>` : s;
  const chip = (name, value, text, type = "radio") => `<label><input type="${type}" name="${name}" value="${value}"><span>${text}</span></label>`;

  for (let i = 0; i <= 7; i++) $("q1").insertAdjacentHTML("beforeend", chip("q1", i, i));
  TRIGGERS.forEach((t, i) => $("q1tc").insertAdjacentHTML("beforeend", chip("q1t", i, t, "checkbox")));
  for (let i = 0; i <= 10; i++) $("q3").insertAdjacentHTML("beforeend", chip("q3", i, i));
  for (let i = 0; i <= 100; i += 10) $("q4").insertAdjacentHTML("beforeend", chip("q4", i, i + "%"));
  CHANGE.forEach((c, i) => $("q5").insertAdjacentHTML("beforeend", chip("q5", i - 3, c)));
  $("q5").insertAdjacentHTML("beforeend", chip("q5", "none", "No earlier check"));

  const q2 = $("q2");
  let idx = 0;
  GROUPS.forEach(([name, items], g) => {
    const all = g === 0 ? `<button type="button" class="gbtn" data-all="${g}" id="all_${g}" aria-pressed="false">All of these</button>` : "";
    const rows = items.map(([a, h, pa, ph]) =>
      `<label><input type="checkbox" id="q2_${idx++}" data-g="${g}"><span>${both(a, pa)}<small>${both(h, ph)}</small></span></label>`).join("");
    q2.insertAdjacentHTML("beforeend", `<div class="grp" role="group" aria-labelledby="gname_${g}">
      <div class="ghead"><span class="gname" id="gname_${g}">${name} <span>(${items.length})</span></span>
      <span class="gbtns">${all}<button type="button" class="gbtn" data-none="${g}" id="none_${g}" aria-pressed="false">None of these this week</button></span></div>
      <div class="checks">${rows}</div></div>`);
  });

  // Counts quoted in the scoring notes come from GROUPS, so they can't drift from the form.
  const fill = (k, v) => document.querySelectorAll(`[data-count="${k}"]`).forEach((x) => { x.textContent = v; });
  fill("total", TOTAL);
  fill("groups", GROUPS.length);
  fill("ranges", GROUPS.map(([n, it]) => `${n.toLowerCase()} 0–${it.length}`).join(", "));
  fill("top2", GROUPS.slice(-2).reduce((n, g) => n + g[1].length, 0));

  const boxes = (g) => [...q2.querySelectorAll(`input[data-g="${g}"]`)];
  const pressed = (b) => b && b.getAttribute("aria-pressed") === "true";
  const press = (b, on) => { if (b) b.setAttribute("aria-pressed", on ? "true" : "false"); };

  q2.addEventListener("click", (e) => {
    const b = e.target.closest("button.gbtn");
    if (!b) return;
    const g = b.dataset.none ?? b.dataset.all, on = !pressed(b);
    if (b.dataset.none !== undefined) {
      if (on) boxes(g).forEach((x) => { x.checked = false; });
      press(b, on);
    } else {
      boxes(g).forEach((x) => { x.checked = on; });
      press($("none_" + g), false);
    }
    update();
  });
  q2.addEventListener("change", (e) => {
    const x = e.target;
    if (!x.matches("input[data-g]")) return;
    if (x.checked) press($("none_" + x.dataset.g), false);
  });

  $("proxy").addEventListener("change", () => {
    const p = $("proxy").checked;
    document.querySelectorAll("#bc .self").forEach((x) => { x.hidden = p; });
    document.querySelectorAll("#bc .proxy").forEach((x) => { x.hidden = !p; });
    update();
  });

  const val = (n) => { const x = document.querySelector(`input[name="${n}"]:checked`); return x ? x.value : null; };

  function update() {
    const q1 = val("q1"), q3 = val("q3"), q4 = val("q4"), q5 = val("q5");
    $("s1").textContent = q1 === null ? DASH : q1 + " / 7";
    $("q1t").hidden = !(Number(q1) > 0);

    let acts = 0, blank = 0;
    const subs = GROUPS.map((g, i) => {
      const n = boxes(i).filter((x) => x.checked).length;
      press($("all_" + i), n === g[1].length);
      const answered = n > 0 || pressed($("none_" + i));
      acts += n;
      if (!answered) blank++;
      return (answered ? n : DASH) + "/" + g[1].length;
    });
    const anyAnswered = blank < GROUPS.length;
    $("s2").textContent = anyAnswered ? acts + " / " + TOTAL : DASH;
    $("s2b").textContent = subs.join(" · ");
    $("s2c").textContent = anyAnswered && blank ? `${blank} ${blank === 1 ? "group" : "groups"} blank` : "";

    $("s3").textContent = q3 === null ? DASH : q3 + " / 10";
    $("s4").textContent = q4 === null ? DASH : q4 + "%";
    $("s6").textContent = q5 === null ? DASH : q5 === "none" ? "Missing (first check)" : CHANGE[Number(q5) + 3];
    $("s5").textContent = $("proxy").checked ? "Carer (proxy)" : "Patient";

    const left = [q1 === null, blank > 0, q3 === null, q4 === null, q5 === null].filter(Boolean).length;
    $("unans").textContent = left ? `${left} of 5 questions still unanswered (Q6 is optional).` : "All 5 questions answered.";
  }
  $("bc").addEventListener("input", update);
  $("bc").addEventListener("change", update);
  update();
})();
