(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { challenges: [], current: null, starter: "", submission: null, trace: null, traceStep: 0, traceRequest: 0, statuses: {}, profile: null };
  const escapeHtml = (value) => String(value ?? "").replace(/[\x26<>"']/g, (character) => ({
    "\x26": "\x26amp;", "<": "\x26lt;", ">": "\x26gt;", '"': "\x26quot;", "'": "\x26#39;"
  }[character]));
  const api = async (url, options = {}) => {
    const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(response.status >= 500 ? "The service is unavailable. Try again shortly." : data.detail || "Please check the form and try again.");
    return data;
  };
  const learnerId = () => $("learner-id")?.value.trim() || "dojo_learner";
  const setStatus = (message = "") => { const element = $("global-status"); if (element) element.textContent = message; };
  const on = (id, event, handler) => { const element = $(id); if (element) element.addEventListener(event, handler); };
  const outcomeLabel = (outcome) => ({ passed: "passed", wrong_output: "wrong output", runtime_error: "runtime error", timeout: "timeout" }[outcome] || outcome || "unknown");

  function renderList() {
    const list = $("challenge-list");
    if (!list) return;
    const recommended = state.profile?.next_challenge?.id;
    const count = $("challenge-count");
    if (count) count.textContent = `${state.challenges.length} available`;
    list.innerHTML = state.challenges.map((challenge) => {
      const status = state.statuses[challenge.id] || "";
      return `<button class="challenge-item ${challenge.id === state.current?.id ? "active" : ""}" data-id="${escapeHtml(challenge.id)}"><strong>${escapeHtml(challenge.title)}</strong><small>${escapeHtml(challenge.difficulty)} · ${escapeHtml((challenge.concepts || []).slice(0, 2).join(" · "))}</small><span class="challenge-meta"><i class="status-dot ${status === "passed" ? "solved" : status ? "failed" : ""}" aria-label="${status ? escapeHtml(outcomeLabel(status)) : "not attempted"}"></i>${recommended === challenge.id ? `<em class="next-badge">Next for you</em>` : ""}</span></button>`;
    }).join("");
    list.querySelectorAll(".challenge-item").forEach((button) => button.addEventListener("click", () => selectChallenge(button.dataset.id)));
  }

  function updateLineNumbers() {
    const code = $("code");
    const numbers = $("line-numbers");
    if (!code || !numbers) return;
    numbers.textContent = Array.from({ length: code.value.split("\n").length }, (_, index) => index + 1).join("\n");
    numbers.scrollTop = code.scrollTop;
  }

  function resetTrace(message = "Trace an example to inspect source lines and variables.") {
    state.traceRequest += 1;
    state.trace = null; state.traceStep = 0;
    ["trace-view"].forEach((id) => { if ($(id)) $(id).hidden = true; });
    if ($("visualizer-panel")) $("visualizer-panel").hidden = false;
    if ($("trace-empty")) { $("trace-empty").hidden = false; $("trace-empty").textContent = message; }
    if ($("trace-status")) $("trace-status").textContent = "";
    if ($("trace-step")) $("trace-step").textContent = "Step 0 / 0";
    if ($("trace-prev")) $("trace-prev").disabled = true;
    if ($("trace-next")) $("trace-next").disabled = true;
  }

  function selectChallenge(id) {
    state.current = state.challenges.find((challenge) => challenge.id === id); state.submission = null;
    if (!state.current) return;
    const challenge = state.current;
    state.starter = challenge.starter_code || "";
    $("challenge-panel").hidden = false; $("results-panel").hidden = true;
    $("difficulty").textContent = challenge.difficulty; $("title").textContent = challenge.title; $("description").textContent = challenge.description;
    $("concepts").innerHTML = (challenge.concepts || []).map((concept) => `<span>${escapeHtml(concept)}</span>`).join("");
    $("examples").innerHTML = (challenge.examples || []).map((example) => `<div class="example"><code>${escapeHtml(example.call)}</code><br>Expected: <strong>${escapeHtml(example.expected)}</strong></div>`).join("") + `<p class="muted">Function: <code>${escapeHtml(challenge.function_name)}</code>. Hidden tests remain private.</p>`;
    $("code").value = state.starter; $("submit-status").textContent = ""; $("feedback-content").hidden = true; $("feedback-empty").hidden = false; if ($("enhanced-explanation-wrap")) $("enhanced-explanation-wrap").hidden = true; if ($("enhanced-explanation")) $("enhanced-explanation").textContent = ""; if ($("explanation-status")) $("explanation-status").textContent = "";
    $("trace-test").innerHTML = (challenge.examples || []).map((example, index) => `<option value="${index + 1}">${index + 1}: ${escapeHtml(example.call)}</option>`).join("");
    resetTrace(); updateLineNumbers(); renderList();
  }

  function traceValue(value) {
    if (!value || typeof value !== "object") return String(value ?? "<unavailable>");
    if (Array.isArray(value.value)) return `[${value.value.map(traceValue).join(", ")}]${value.truncated ? " …" : ""}`;
    if (value.value && typeof value.value === "object") return `{${Object.entries(value.value).map(([key, item]) => `${key}: ${traceValue(item)}`).join(", ")}}${value.truncated ? " …" : ""}`;
    return String(value.value ?? "<unavailable>");
  }

  function renderTraceSource(activeLine) {
    const source = $("code")?.value || "";
    $("trace-source").innerHTML = source.split("\n").map((line, index) => `<span class="trace-source-line${index + 1 === activeLine ? " active" : ""}"><b>${index + 1}</b>${escapeHtml(line) || " "}</span>`).join("");
  }

  function renderTraceStep() {
    const events = state.trace?.events || []; const event = events[state.traceStep];
    if (!event) return;
    $("trace-view").hidden = false; $("trace-empty").hidden = true; $("trace-step").textContent = `Step ${state.traceStep + 1} / ${events.length}`;
    renderTraceSource(event.line);
    $("trace-line").textContent = `Line ${event.line} · ${event.function}`;
    const labels = { line: "Executed", call: "Function call", return: "Function return" };
    $("trace-event").textContent = `${labels[event.event] || "Trace event"} · public example only`;
    $("trace-vars").innerHTML = Object.entries(event.locals || {}).map(([key, value]) => `<div class="trace-var"><strong>${escapeHtml(key)}</strong><code>${escapeHtml(traceValue(value))}</code><small>${escapeHtml(value.type || "value")}</small></div>`).join("") || `<p class="muted">No local variables were observable at this step.</p>`;
    $("trace-changes").innerHTML = (event.changes || []).map((change) => `<span class="tag">${escapeHtml(change)} changed</span>`).join("") || `<p class="muted">No variable changes were observed at this step.</p>`;
    $("trace-output").textContent = event.return_value ? `Returned ${traceValue(event.return_value)}` : (state.trace.return_value ? `Final result: ${traceValue(state.trace.return_value)}` : "No return value available.");
    $("trace-error").textContent = state.trace.error || "None";
    $("trace-prev").disabled = state.traceStep === 0; $("trace-next").disabled = state.traceStep >= events.length - 1;
  }

  async function traceCode() {
    if (!state.current) return;
    const token = ++state.traceRequest; const button = $("trace-button"); button.disabled = true; $("visualizer-panel").hidden = false; $("trace-view").hidden = true; $("trace-empty").hidden = false; $("trace-empty").textContent = "Tracing the selected public example..."; $("trace-status").textContent = "Tracing safely...";
    try {
      const data = await api("/api/trace", { method: "POST", body: JSON.stringify({ learner_id: learnerId(), challenge_id: state.current.id, code: $("code").value, visible_test: Number($("trace-test").value) }) });
      if (token !== state.traceRequest) return;
      state.trace = data; state.traceStep = 0;
      const complete = data.status === "completed";
      $("trace-status").textContent = complete ? "Trace ready" : `Trace ${data.status.replace("_", " ")}`;
      if (data.events?.length) renderTraceStep(); else { $("trace-empty").textContent = data.error ? `No steps available: ${data.error}.` : "No observable execution steps were produced."; }
    } catch (error) {
      if (token !== state.traceRequest) return;
      $("trace-status").textContent = "Trace failed"; $("trace-empty").textContent = "The trace could not be produced. The editor and submission results were not changed."; $("trace-empty").hidden = false; setStatus(error.message);
    } finally { if (token === state.traceRequest) button.disabled = false; }
  }

  function renderHints() {
    const used = state.submission?.hint_level || 0; const total = 4;
    $("hints").innerHTML = Array.from({ length: total }, (_, index) => index < used ? `<div class="hint"><strong>Hint ${index + 1}</strong><br>${escapeHtml(state.submission.hints?.[index] || "Revealed hint")}</div>` : `<div class="hint locked">Hint ${index + 1}, locked</div>`).join("");
  }

  function renderProfile(profile) {
    state.profile = profile; renderList();
    const mastery = Object.entries(profile.mastery || {});
    $("profile").innerHTML = mastery.length ? mastery.map(([concept, value]) => { const score = Number(value); const tone = score > .6 ? "" : score >= .3 ? "amber" : "coral"; return `<div><dl><dt>${escapeHtml(concept)}</dt><dd>${Math.round(score * 100)}%</dd></dl><div class="progress ${tone}"><span style="width:${Math.max(0, Math.min(100, score * 100))}%"></span></div></div>`; }).join("") : `<p class="muted">No mastery data yet.</p>`;
    $("recommendation").innerHTML = profile.next_challenge ? `<p class="recommendation"><strong>${escapeHtml(profile.next_challenge.id)}</strong><br><small>${escapeHtml(profile.next_challenge.reason)}</small></p><button class="secondary full-width" type="button" data-start-challenge="${escapeHtml(profile.next_challenge.id)}">Start this challenge</button>` : `<p class="muted">No recommendation yet.</p>`;
    $("recommendation").querySelector("[data-start-challenge]")?.addEventListener("click", (event) => selectChallenge(event.currentTarget.dataset.startChallenge));
  }

  async function loadProfile() {
    if ($("profile-status")) $("profile-status").textContent = "Loading...";
    try {
      const profile = await api(`/api/learner/${encodeURIComponent(learnerId())}`); renderProfile(profile);
      const categories = profile.recurring_mistakes || [];
      $("mistakes").innerHTML = categories.length ? categories.map((item) => `<div class="mistake-group"><span class="tag">${escapeHtml(item.category || item)}</span><small>${escapeHtml((item.challenges || []).join(" · "))}</small></div>`).join("") : `<p class="muted">No recurring mistakes yet.</p>`;
      if ($("profile-status")) $("profile-status").textContent = "Updated";
    } catch (error) { if ($("profile-status")) $("profile-status").textContent = "Unavailable"; $("profile").innerHTML = `<p class="muted">Profile unavailable.</p>`; setStatus(error.message); }
  }

  function renderResults(data) {
    state.submission = data; console.debug("[dojo-ai] frontend_response", { source: data.explanation_source, enhanced: Boolean(data.enhanced_explanation) }); const total = data.visible.length + data.hidden.length; const passed = data.visible.filter((item) => item.outcome === "passed").length + data.hidden.filter((item) => item.outcome === "passed").length; const allPassed = passed === total;
    $("results-panel").hidden = false; $("submission-id").textContent = data.submission_id; $("outcome-summary").innerHTML = `<div class="outcome ${allPassed ? "" : "failed"}">${passed} of ${total} tests passed</div>`;
    $("visible-results").innerHTML = data.visible.map((item) => `<div class="test ${item.outcome === "passed" ? "pass" : "fail"}"><strong>${escapeHtml(item.call)}</strong><span>Expected ${escapeHtml(item.expected)} · got ${escapeHtml(item.got)}</span><span class="outcome-chip ${escapeHtml(item.outcome)}">${escapeHtml(outcomeLabel(item.outcome))}</span></div>`).join("");
    $("hidden-results").innerHTML = data.hidden.map((item) => `<div class="hidden-test"><span>Hidden test ${escapeHtml(item.test)}</span><span class="outcome-chip ${escapeHtml(item.outcome)}">${escapeHtml(outcomeLabel(item.outcome))}</span></div>`).join("");
    $("feedback-empty").hidden = true; $("feedback-content").hidden = false; $("explanation").textContent = data.deterministic_explanation || data.explanation || "No explanation available."; const enhanced = data.explanation_source === "enhanced" && typeof data.enhanced_explanation === "string" && data.enhanced_explanation.trim(); if ($("enhanced-explanation")) $("enhanced-explanation").textContent = ""; if ($("enhanced-explanation-wrap")) $("enhanced-explanation-wrap").hidden = !enhanced; if ($("enhanced-explanation")) $("enhanced-explanation").textContent = enhanced || ""; if ($("explanation-status")) $("explanation-status").textContent = enhanced ? "AI response shown; grading remains deterministic." : "AI enhancement unavailable; deterministic explanation is being used."; $("feedback-tags").innerHTML = data.mistake_tags.length ? data.mistake_tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("") : `<p class="muted">No detected mistake pattern.</p>`; $("hint-button").hidden = !data.mistake_tags.length; $("hint-refusal").textContent = ""; renderHints(); state.statuses[state.current.id] = allPassed ? "passed" : "failed"; renderList(); loadProfile(); $("results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function submit() { if (!state.current) return; console.debug("[dojo-ai] submit_entered", { challenge: state.current.id }); const button = $("submit-button"); button.disabled = true; $("submit-status").textContent = "Running tests..."; setStatus(""); try { renderResults(await api("/api/submit", { method: "POST", body: JSON.stringify({ learner_id: learnerId(), challenge_id: state.current.id, code: $("code").value }) })); $("submit-status").textContent = "Submission complete"; } catch (error) { setStatus(error.message); $("submit-status").textContent = "Submission failed"; } finally { button.disabled = false; } }
  async function getHint() { if (!state.submission) return; const button = $("hint-button"); button.disabled = true; try { const hint = await api("/api/hint", { method: "POST", body: JSON.stringify({ submission_id: state.submission.submission_id }) }); state.submission.hint_level = (state.submission.hint_level || 0) + 1; state.submission.hints = [...(state.submission.hints || []), hint.hint]; renderHints(); button.textContent = hint.remaining ? "Show next hint" : "No more hints"; button.hidden = !hint.remaining; $("hint-refusal").textContent = hint.note || ""; } catch (error) { setStatus(error.message); } finally { button.disabled = false; } }
  function resetCode() { $("code").value = state.starter; resetTrace(); updateLineNumbers(); $("code").focus(); }

  async function init() {
    try {
      const badge = $("ai-status-badge");
      try { const ai = await api("/api/ai-status"); if (badge) { const label = ai.state === "enhanced" ? "AI enhancement: available" : ai.state === "disabled" ? "AI enhancement: disabled" : ai.state === "unavailable" ? `AI enhancement: unavailable (${ai.reason || "provider"})` : (ai.enabled ? "AI enhancement: configured" : "AI enhancement: deterministic fallback"); badge.textContent = label; badge.classList.toggle("on", ai.state === "enhanced" || Boolean(ai.enabled)); badge.classList.toggle("off", !ai.enabled); } } catch (_) { if (badge) badge.textContent = "AI enhancement: status unavailable"; }
      state.challenges = await api("/api/challenges"); if (!state.challenges.length) throw new Error("No challenges available"); renderList(); selectChallenge(state.challenges[0].id); await loadProfile();
    } catch (error) { setStatus(error.message); const list = $("challenge-list"); if (list) list.innerHTML = `<p class="empty-state">Unable to load challenges. Try refreshing the page.</p>`; }
  }

  on("submit-button", "click", submit); on("reset-button", "click", resetCode); on("hint-button", "click", getHint); on("profile-button", "click", loadProfile); on("learner-id", "change", loadProfile); on("trace-button", "click", traceCode);
  on("trace-prev", "click", () => { if (state.traceStep) { state.traceStep--; renderTraceStep(); } });
  on("trace-next", "click", () => { if (state.trace && state.traceStep < state.trace.events.length - 1) { state.traceStep++; renderTraceStep(); } });
  on("code", "input", () => { updateLineNumbers(); if (state.trace) resetTrace(); }); on("code", "scroll", () => { if ($("line-numbers")) $("line-numbers").scrollTop = $("code").scrollTop; });
  on("code", "keydown", (event) => { if (event.key === "Tab") { event.preventDefault(); const start = event.target.selectionStart; const indent = "    "; event.target.value = event.target.value.slice(0, start) + indent + event.target.value.slice(event.target.selectionEnd); event.target.selectionStart = event.target.selectionEnd = start + indent.length; updateLineNumbers(); } if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); submit(); } });
  init();
})();
