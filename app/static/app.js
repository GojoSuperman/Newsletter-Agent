const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const safeHref = (u) => /^https?:\/\//i.test(u || "") ? esc(u) : null;
const fmtTime = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }); };
const fmtDate = (ymd) => { const [y, m, d] = ymd.split("-").map(Number); const dt = new Date(y, m - 1, d); return `${y}년 ${m}월 ${d}일 (${"일월화수목금토"[dt.getDay()]})`; };

const state = { issues: [], current: null, tab: "published", settings: null };

// ---------- 데이터 ----------
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status}`);
  return body;
}

async function loadIssues(selectId) {
  state.issues = await api("/api/issues");
  renderSidebar();
  const id = selectId || (state.current && state.current.run_id) || (state.issues[0] && state.issues[0].run_id);
  if (id) await openIssue(id); else renderIssue();
}

async function openIssue(runId) {
  state.current = await api(`/api/issues/${runId}`);
  state.current.run_id = runId;
  renderSidebar();
  renderIssue();
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  renderSettingsForm();
  $("#make").disabled = !state.settings.openai_key_tail;
  $("#hours").value = String(state.settings.hours);
  if (!state.settings.openai_key_tail) openSettings();
}

// ---------- 렌더 ----------
function renderSidebar() {
  const today = new Date().toISOString().slice(0, 10);
  $("#issue-list").innerHTML = state.issues.map(i => {
    const active = state.current && state.current.run_id === i.run_id ? "active" : "";
    const badge = i.origin === "github" ? `<span class="badge">GitHub</span>` : "";
    const dot = i.date === today ? `<span class="today">●</span>` : "";
    return `<li class="${active}" data-id="${esc(i.run_id)}">
      <div class="row1">${esc(i.date.slice(5).replace("-", "월 "))}일 ${dot}${badge}</div>
      <div class="row2 meta">발행 ${i.published} · 수집 ${i.collected}${i.sent_at ? " · 발송됨" : ""}</div></li>`;
  }).join("") || `<li class="meta">아직 없음</li>`;
  $$("#issue-list li[data-id]").forEach(li => li.addEventListener("click", () => openIssue(li.dataset.id)));
}

function rejectionReasons(s) {
  const map = {};
  (s.log || []).forEach(l => { const m = l.match(/✗ 탈락 · (.+?) · (.+?) · (.+)$/); if (m) map[`${m[1]}::${m[2]}`] = m[3]; });
  return map;
}

function card(d, reason) {
  const href = safeHref(d.url);
  const title = href ? `<a href="${href}" target="_blank" rel="noopener">${esc(d.headline)}</a>` : esc(d.headline);
  return `<article class="card ${reason ? "rejected" : ""}">
    <div class="meta">${esc(d.source)} · ${esc(fmtTime(d.at))}</div>
    <h3>${title}</h3>
    <p class="summary">${esc(d.summary)}</p>
    <p class="why">➜ 왜 중요한가 · ${esc(d.why)}</p>
    ${reason ? `<p class="reason">검수 탈락 · ${esc(reason)}</p>` : ""}
    ${href ? `<a class="more" href="${href}" target="_blank" rel="noopener">원문 보기 ↗</a>` : ""}
  </article>`;
}

function renderIssue() {
  const s = state.current;
  $("#empty").hidden = !!s; $("#issue").hidden = !s;
  if (!s) return;
  const verifiedUrls = new Set((s.verified || []).map(d => d.url));
  const rejected = (s.drafted || []).filter(d => !verifiedUrls.has(d.url));
  const reasons = rejectionReasons(s);
  const rid = s.run_id;
  $("#issue-date").textContent = fmtDate(`${rid.slice(0,4)}-${rid.slice(4,6)}-${rid.slice(6,8)}`);
  $("#issue-meta").textContent = `발행 ${(s.verified||[]).length}건 · 검수 탈락 ${rejected.length}건 · 수집 ${(s.collected||[]).length}건`;
  $("#n-published").textContent = (s.verified||[]).length;
  $("#n-rejected").textContent = rejected.length;
  $("#n-collected").textContent = (s.collected||[]).length;
  $("#tab-published").innerHTML = (s.verified||[]).map(d => card(d, null)).join("") || `<p class="meta">검수를 통과한 기사가 없습니다.</p>`;
  $("#tab-rejected").innerHTML = rejected.map(d => card(d, reasons[`${d.source}::${d.headline.slice(0,30)}`] || "사유 로그 참조")).join("") || `<p class="meta">탈락한 기사가 없습니다.</p>`;
  renderCollected();
  showTab(state.tab);
  const canSend = (s.verified||[]).length > 0 && state.settings && state.settings.webhook_registered && !s.sent_at && s.dry_run !== false;
  $("#send").disabled = !canSend;
  $("#send-status").textContent = s.sent_at ? `${fmtTime(s.sent_at)} 발송됨`
    : s.dry_run === false ? "이미 발행됨 (GitHub 실행)"
    : !(s.verified||[]).length ? "보낼 기사가 없습니다"
    : !(state.settings && state.settings.webhook_registered) ? "설정에서 Discord 웹훅을 등록하세요"
    : "보낸 적 없음";
}

function renderCollected() {
  const s = state.current; if (!s) return;
  const q = ($("#search").value || "").toLowerCase();
  const picked = new Set((s.picked||[]).map(p => p.url));
  const rows = (s.collected||[]).filter(a => !q || (a.title||"").toLowerCase().includes(q) || (a.source||"").toLowerCase().includes(q));
  $("#collected-table").innerHTML = `<tr><th>출처</th><th>시각</th><th>제목</th></tr>` + rows.map(a => {
    const href = safeHref(a.url);
    const t = href ? `<a href="${href}" target="_blank" rel="noopener">${esc(a.title)}</a>` : esc(a.title);
    return `<tr><td>${esc(a.source)}</td><td class="meta">${esc(fmtTime(a.at))}</td><td>${t}${picked.has(a.url) ? ' <span class="badge pick">선별</span>' : ""}</td></tr>`;
  }).join("");
}

function showTab(name) {
  state.tab = name;
  $$(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab-pane").forEach(p => p.hidden = p.id !== `tab-${name}`);
}

// ---------- 만들기 ----------
async function makeIssue() {
  const ov = $("#overlay"); ov.hidden = false;
  $("#overlay-error").hidden = true; $("#overlay-close").hidden = true; $("#run-log").textContent = "";
  $$("#steps li").forEach(li => { li.className = ""; li.querySelector("em").textContent = ""; });
  $("#make").disabled = true;
  let runId;
  try { ({ run_id: runId } = await api("/api/run", { method: "POST", body: JSON.stringify({ hours: Number($("#hours").value) }) })); }
  catch (e) { showRunError(e.message); return; }
  let reportDone = 0, reportTotal = 0;
  const setStep = (name, cls, note) => { const li = $(`#steps li[data-step="${name}"]`); li.className = cls; if (note !== undefined) li.querySelector("em").textContent = note; };
  setStep("collect", "active");
  const es = new EventSource(`/api/run/${runId}/events`);
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    (e.update && e.update.log || []).forEach(l => $("#run-log").textContent += l + "\n");
    if (e.node === "collect") { setStep("collect", "done", `${(e.update.collected||[]).length}건`); setStep("select", "active"); }
    if (e.node === "select") { reportTotal = (e.update.picked||[]).length; setStep("select", "done", `${reportTotal}건`); if (reportTotal) setStep("report", "active"); else { setStep("report", "done", "건너뜀"); setStep("verify", "active"); } }
    if (e.node === "report") { reportDone += 1; setStep("report", reportDone >= reportTotal ? "done" : "active", `${reportDone} / ${reportTotal}`); if (reportDone >= reportTotal) setStep("verify", "active"); }
    if (e.node === "verify") { setStep("verify", "done", `${(e.update.verified||[]).length}건 통과`); setStep("publish", "active"); }
    if (e.node === "publish") { setStep("publish", "done"); }
    if (e.node === "__end__") { es.close(); ov.hidden = true; $("#make").disabled = false; loadIssues(runId); }
    if (e.node === "__error__") { es.close(); showRunError(e.error); }
  };
  es.onerror = () => { es.close(); showRunError("연결이 끊겼습니다"); };
}

function showRunError(msg) {
  $("#overlay-error").textContent = "오류: " + msg; $("#overlay-error").hidden = false;
  $("#log-details").open = true; $("#overlay-close").hidden = false; $("#make").disabled = false;
}

// ---------- 발송 ----------
async function sendIssue() {
  const s = state.current; if (!s) return;
  if (!confirm(`${(s.verified||[]).length}건을 Discord로 보낼까요? 보낸 뒤에는 되돌릴 수 없습니다.`)) return;
  $("#send").disabled = true; $("#send-status").textContent = "보내는 중…";
  try { await api(`/api/issues/${s.run_id}/send`, { method: "POST" }); await loadIssues(s.run_id); }
  catch (e) { $("#send-status").textContent = "발송 실패: " + e.message; $("#send").disabled = false; }
}

// ---------- 설정 ----------
function openSettings() { $("#settings").hidden = false; $("#backdrop").hidden = false; }
function closeSettings() { $("#settings").hidden = true; $("#backdrop").hidden = true; }
function renderSettingsForm() {
  const s = state.settings; if (!s) return;
  $("#key-status").textContent = s.openai_key_tail ? `등록됨 · ${s.openai_key_tail}` : "미등록";
  $("#hook-status").textContent = s.webhook_registered ? "등록됨" : "미등록";
  $("#clear-hook").hidden = !s.webhook_registered;
  $("#f-model").value = s.openai_model; $("#f-hours").value = s.hours;
  $("#f-key").value = ""; $("#f-hook").value = "";
}
async function saveSettings(ev) {
  ev.preventDefault();
  const body = { openai_model: $("#f-model").value, hours: Number($("#f-hours").value) };
  if ($("#f-key").value) body.openai_api_key = $("#f-key").value.trim();
  if ($("#f-hook").value) body.discord_webhook_url = $("#f-hook").value.trim();
  if ($("#f-hook").dataset.clear === "1") body.discord_webhook_url = "";
  $("#settings-error").hidden = true;
  try {
    state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
    delete $("#f-hook").dataset.clear;
    renderSettingsForm(); closeSettings();
    $("#make").disabled = !state.settings.openai_key_tail; $("#hours").value = String(state.settings.hours);
    renderIssue();
  } catch (e) { $("#settings-error").textContent = e.message; $("#settings-error").hidden = false; }
}

// ---------- 이벤트 ----------
$("#make").addEventListener("click", makeIssue);
$("#send").addEventListener("click", sendIssue);
$("#open-settings").addEventListener("click", openSettings);
$("#close-settings").addEventListener("click", closeSettings);
$("#backdrop").addEventListener("click", closeSettings);
$("#settings-form").addEventListener("submit", saveSettings);
$("#clear-hook").addEventListener("click", () => { $("#f-hook").dataset.clear = "1"; $("#hook-status").textContent = "저장하면 해제됨"; });
$("#overlay-close").addEventListener("click", () => { $("#overlay").hidden = true; });
$("#search").addEventListener("input", renderCollected);
$$(".tab").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));

(async () => {
  try { await loadSettings(); await loadIssues(); }
  catch (e) {
    $("#empty").hidden = false;
    $("#empty").textContent = "불러오기 실패: " + e.message;
    openSettings();
  }
})();
