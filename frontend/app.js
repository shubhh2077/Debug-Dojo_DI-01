(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { challenges: [], current: null, submission: null };
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>]/g, (c) => ({ "&": "&", "<": "<", ">": ">" }[c]));
  const api = async (url, options = {}) => {
    const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  };
  const learnerId = () => $("learner-id").value.trim() || "dojo_learner";
  const setStatus = (message = "") => { $("global-status").textContent = message; };
  function renderList() {
    $("challenge-count").textContent = `${state.challenges.length} available`;
    $("challenge-list").innerHTML = state.challenges.map((c) => `<button class="challenge-item ${c.id === state.current?.id ? "active" : ""}" data-id="${escapeHtml(c.id)}"><strong>${escapeHtml(c.title)}</strong><small>${escapeHtml(c.difficulty)} · ${escapeHtml(c.concepts.slice(0, 2).join(" · "))}</small></button>`).join("");
    document.querySelectorAll(".challenge-item").forEach((b) => b.addEventListener("click", () => selectChallenge(b.dataset.id)));
  }
  function selectChallenge(id) {
    state.current = state.challenges.find((c) => c.id === id);
    state.submission = null;
    if (!state.current) return;
    const c = state.current;
    $("challenge-panel").hidden = false;
    $("results-panel").hidden = true;
    $("difficulty").textContent = c.difficulty;
    $("difficulty").dataset.level = c.difficulty;
    $("title").textContent = c.title;
    $("description").textContent = c.description;
    $("concepts").innerHTML = c.concepts.map((x) => `<span>${escapeHtml(x)}</span>`).join("");
    $("examples").innerHTML = c.examples.map((x) => `<div class="example"><code>${escapeHtml(x.call)}</code><br>Expected: <strong>${escapeHtml(x.expected)}</strong></div>`).join("") + `<p class="muted">Function: <code>${escapeHtml(c.function_name)}</code>. Hidden tests are used privately by the judge.</p>`;
    $("code").value = c.starter_code;
    $("submit-status").textContent = "";
    $("hint-button").hidden = true;
    renderList();
  }
  function renderResults(data) {
    state.submission = data;
    const passed = data.visible.filter((x) => x.outcome === "passed").length;
    const hiddenPassed = data.hidden.filter((x) => x.outcome === "passed").length;
    const allPassed = data.hidden.every((x) => x.outcome === "passed") && data.visible.every((x) => x.outcome === "passed");
    $("results-panel").hidden = false;
    $("submission-id").textContent = data.submission_id;
    $("outcome-summary").innerHTML = `<div class="outcome ${allPassed ? "" : "failed"}">${allPassed ? "All tests passed." : `${passed}/${data.visible.length} visible tests passed · ${hiddenPassed}/${data.hidden.length} hidden tests passed`}</div>`;
    $("visible-results").innerHTML = data.visible.map((x) => `<div class="test ${x.outcome === "passed" ? "pass" : "fail"}"><strong>Test ${x.test}: ${escapeHtml(x.outcome)}</strong><code>${escapeHtml(x.call)}</code><span>Expected ${escapeHtml(x.expected)} · got ${escapeHtml(x.got)}</span></div>`).join("");
    $("mistakes").innerHTML = data.mistake_tags.length ? `<h3>Detected patterns</h3>${data.mistake_tags.map((x) => `<span class="tag">${escapeHtml(x)}</span>`).join("")}` : `<p class="muted">No recurring mistake pattern detected.</p>`;
    $("explanation").textContent = data.explanation || "No explanation available.";
    $("hint-button").hidden = !data.mistake_tags.length;
    $("hints").innerHTML = "";
    loadProfile();
    $("results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  async function submit() {
    if (!state.current) return;
    const button = $("submit-button");
    button.disabled = true;
    $("submit-status").textContent = "Running safely…";
    setStatus("");
    try {
      renderResults(await api("/api/submit", { method: "POST", body: JSON.stringify({ learner_id: learnerId(), challenge_id: state.current.id, code: $("code").value }) }));
      $("submit-status").textContent = "Submission complete";
    } catch (e) {
      setStatus(e.message);
      $("submit-status").textContent = "Submission failed";
    } finally { button.disabled = false; }
  }
  async function getHint() {
    if (!state.submission) return;
    const button = $("hint-button");
    button.disabled = true;
    try {
      const h = await api("/api/hint", { method: "POST", body: JSON.stringify({ submission_id: state.submission.submission_id }) });
      $("hints").insertAdjacentHTML("beforeend", `<div class="hint"><strong>Hint ${h.level}</strong><br>${escapeHtml(h.hint)}${h.note ? `<br><small>${escapeHtml(h.note)}</small>` : ""}</div>`);
      button.textContent = h.remaining ? `Reveal next hint (${h.remaining} left)` : "No more hints";
      button.hidden = !h.remaining;
    } catch (e) { setStatus(e.message); } finally { button.disabled = false; }
  }
  async function loadProfile() {
    try {
      const p = await api(`/api/learner/${encodeURIComponent(learnerId())}`);
      const mastery = Object.entries(p.mastery || {});
      $("profile").innerHTML = `${mastery.length ? mastery.map(([key, value]) => `<dl><dt>${escapeHtml(key)}</dt><dd>${Math.round(Number(value) * 100)}%</dd></dl>`).join("") : `<p class="muted">No mastery data yet.</p>`}${p.recurring_mistakes?.length ? `<p><strong>Recurring mistakes</strong><br>${p.recurring_mistakes.map((x) => `<span class="tag">${escapeHtml(x.category)}</span>`).join("")}</p>` : ""}${p.next_challenge ? `<p class="recommendation"><strong>Next:</strong> ${escapeHtml(p.next_challenge.id)}<br><small>${escapeHtml(p.next_challenge.reason)}</small></p>` : ""}`;
    } catch (e) { $("profile").innerHTML = `<p class="muted">Profile unavailable: ${escapeHtml(e.message)}</p>`; }
  }
  async function init() {
    try {
      state.challenges = await api("/api/challenges");
      if (!state.challenges.length) throw new Error("No challenges available");
      renderList();
      selectChallenge(state.challenges[0].id);
    } catch (e) {
      setStatus(e.message);
      $("challenge-list").innerHTML = `<p class="empty">Unable to load challenges.</p>`;
    }
  }
  $("submit-button").addEventListener("click", submit);
  $("hint-button").addEventListener("click", getHint);
  $("profile-button").addEventListener("click", loadProfile);
  $("learner-id").addEventListener("change", loadProfile);
  init();
})();
