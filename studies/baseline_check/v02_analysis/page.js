
(function () {
  const GROUPS = [
    ["Everyday basics", [
      ["Sit up for most of the day", "or in a supported chair"],
      ["Shower or bathe", "standing or seated"],
      ["Make a simple meal", "e.g. toast, a sandwich"],
      ["Have a 30-minute conversation", "in person, phone or video"],
      ["Read or watch something for 30 minutes", "and follow it"],
      ["Leave the house", "for any reason"]]],
    ["Getting out and keeping up", [
      ["Walk for 15 minutes outside", "at your own pace"],
      ["Stand for 20 minutes", "e.g. queueing, cooking at the stove"],
      ["Do household chores", "e.g. laundry, cleaning, cooking a full meal"],
      ["Go grocery shopping or run errands", "in person"],
      ["See friends or family for an hour or more", "outside your home"],
      ["Work, study or volunteer for half a day", "about 4 hours, any setting"]]],
    ["Full days and beyond", [
      ["Do light exercise on purpose", "e.g. gentle swim, yoga, easy bike ride"],
      ["Walk for 45 minutes or more", "in one go"],
      ["Do 3 or more hours of focused mental work", "e.g. reading, screens, planning, paperwork"],
      ["Do a full day of work, study or caring", "about 8 hours of demanding tasks, without needing to lie down"],
      ["Go out for an evening or an outing of 3+ hours", "e.g. dinner, an event, a day trip, time outdoors"],
      ["Keep up a full week of your usual responsibilities", "work, study, caring or running a home, with no days lost"],
      ["Be as physically active as before you got sick", "your old exercise, sport or physical job"]]]
  ];
  const ACTS = GROUPS.flatMap(g => g[1]);
  const CHANGE = ["Much worse", "Worse", "A little worse", "About the same", "A little better", "Better", "Much better"];
  const $ = (id) => document.getElementById(id);
  const q1 = $("q1");
  for (let i = 0; i <= 7; i++) q1.insertAdjacentHTML("beforeend", `<label><input type="radio" name="q1" id="q1_${i}" value="${i}" ${i === 0 ? "checked" : ""}><span>${i}</span></label>`);
  const q2 = $("q2");
  let idx = 0;
  GROUPS.forEach(([name, items], g) => {
    q2.insertAdjacentHTML("beforeend", `<div class="group"><span class="gname">${name} <span>(${items.length})</span></span><button type="button" class="none" id="none_${g}" data-none="${g}" aria-pressed="false">None of these this week</button></div>`);
    items.forEach(([a, h]) => { q2.insertAdjacentHTML("beforeend", `<label><input type="checkbox" id="q2_${idx}" data-g="${g}"><span>${a}<small>${h}</small></span></label>`); idx++; });
  });
  q2.addEventListener("click", (e) => {
    const b = e.target.closest("button.none");
    if (!b) return;
    const g = b.dataset.none, on = b.getAttribute("aria-pressed") !== "true";
    if (on) q2.querySelectorAll(`input[data-g="${g}"]`).forEach((x) => { x.checked = false; });
    b.setAttribute("aria-pressed", on ? "true" : "false");
    update();
  });
  q2.addEventListener("change", (e) => {
    if (e.target.matches("input[data-g]") && e.target.checked) $("none_" + e.target.dataset.g).setAttribute("aria-pressed", "false");
  });
  $("proxy").addEventListener("change", () => {
    const p = $("proxy").checked;
    document.querySelectorAll("#bc .self").forEach((x) => { x.hidden = p; });
    document.querySelectorAll("#bc .proxy").forEach((x) => { x.hidden = !p; });
    update();
  });
  const q5 = $("q5");
  CHANGE.forEach((c, i) => q5.insertAdjacentHTML("beforeend", `<label><input type="radio" name="q5" id="q5_${i}" value="${i - 3}" ${i === 3 ? "checked" : ""}><span>${c}</span></label>`));
  function update() {
    const crash = document.querySelector('input[name="q1"]:checked').value;
    const acts = q2.querySelectorAll("input:checked").length;
    $("q3v").textContent = $("q3").value;
    $("q4v").textContent = $("q4").value + "%";
    $("s1").textContent = crash + " / 7";
    $("s2").textContent = acts + " / " + ACTS.length;
    $("s2b").textContent = GROUPS.map((g, i) => {
      const n = q2.querySelectorAll(`input[data-g="${i}"]:checked`).length;
      const answered = n > 0 || $("none_" + i).getAttribute("aria-pressed") === "true";
      return (answered ? n : "–") + "/" + g[1].length;
    }).join(" · ");
    $("s5").textContent = $("proxy").checked ? "Carer (proxy)" : "Patient";
    $("s3").textContent = $("q3").value + " / 10";
    $("s4").textContent = $("q4").value + "%";
  }
  $("bc").addEventListener("input", update);
  $("bc").addEventListener("change", update);
  update();
})();
