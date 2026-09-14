const $ = (s) => document.querySelector(s);
const logEl = $("#log");
let draftedCount = 0;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function setFunnel(k, v) { const el = document.querySelector(`[data-k="${k}"]`); if (el) el.textContent = v; }

function resetView() {
  logEl.textContent = "";
  draftedCount = 0;
  ["collected","picked","drafted","verified","published"].forEach(k => setFunnel(k, "–"));
  $("#cardlist").innerHTML = "";
}

function onUpdate(node, u) {
  (u.log || []).forEach(l => logEl.textContent += l + "\n");
  if (u.collected) setFunnel("collected", u.collected.length);
  if (u.picked) setFunnel("picked", u.picked.length);
  if (u.drafted) { draftedCount += u.drafted.length; setFunnel("drafted", draftedCount); }
  if (u.verified) setFunnel("verified", u.verified.length);
}

async function startRun() {
  $("#run").disabled = true;
  resetView();
  const body = { hours: Number($("#hours").value), dry_run: $("#dry").checked };
  const r = await fetch("/api/run", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
  if (!r.ok) { logEl.textContent = "실행 실패: " + (await r.text()); $("#run").disabled = false; return; }
  const { run_id } = await r.json();
  const es = new EventSource(`/api/run/${run_id}/events`);
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.node === "__end__") { es.close(); $("#run").disabled = false; renderCards(e.state); loadHistory(); return; }
    if (e.node === "__error__") { logEl.textContent += "⚠ 오류: " + e.error + "\n"; es.close(); $("#run").disabled = false; return; }
    onUpdate(e.node, e.update);
  };
  es.onerror = () => { es.close(); $("#run").disabled = false; };
}

function renderCards(state) {
  const okUrls = new Set((state.verified || []).map(d => d.url));
  const rejectedReason = {};
  (state.log || []).forEach(l => { const m = l.match(/✗ 탈락 · (.+?) · (.+?) · (.+)$/); if (m) rejectedReason[`${m[1]}::${m[2]}`] = m[3]; });
  $("#cardlist").innerHTML = (state.drafted || []).map(d => {
    const ok = okUrls.has(d.url);
    const reason = ok ? "" : `<div class="meta">검수 탈락: ${esc(rejectedReason[`${d.source}::${d.headline.slice(0,30)}`] || "사유 로그 참조")}</div>`;
    const safeUrl = /^https?:\/\//i.test(d.url);
    const heading = safeUrl
      ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.headline)}</a>`
      : esc(d.headline);
    return `<article class="card ${ok ? "" : "rejected"}">
      <h3>${heading}</h3>
      <p>${esc(d.summary)}</p><p class="why">왜 중요한가 · ${esc(d.why)}</p>
      <div class="meta">${esc(d.source)} · ${esc(d.at.slice(0,16).replace("T"," "))}</div>${reason}</article>`;
  }).join("") || "<p class='meta'>발행 카드가 없습니다.</p>";
  setFunnel("published", state.dry_run ? `${(state.verified||[]).length} (dry)` : (state.verified||[]).length);
}
async function loadHistory() {
  const rows = await (await fetch("/api/runs")).json();
  const recent = rows.slice(-30).reverse();
  const head = "<tr><th>실행</th><th>출처</th><th>수집</th><th>선별</th><th>취재</th><th>추출률</th><th>검수</th><th>발행</th><th>실패 소스</th><th>초</th></tr>";
  $("#runs").innerHTML = head + recent.map(r => {
    const secs = Object.values(r.seconds || {}).reduce((a, b) => a + b, 0).toFixed(1);
    const id = `<a href="#" data-run="${esc(r.run_id)}">${esc(r.run_id)}</a>${r.dry_run ? " (dry)" : ""}`;
    const rate = r.picked ? `${Math.round((r.drafted / r.picked) * 100)}%` : "–";
    const origin = r.origin === "github" ? `<span class="origin">GitHub</span>` : `<span class="origin local">로컬</span>`;
    return `<tr><td>${id}</td><td>${origin}</td><td>${r.collected}</td><td>${r.picked}</td><td>${r.drafted}</td><td>${rate}</td><td>${r.verified}</td><td>${r.published}</td><td>${esc((r.dead_sources||[]).join(", "))}</td><td>${secs}</td></tr>`;
  }).join("");
  $("#runs").querySelectorAll("a[data-run]").forEach(a => a.addEventListener("click", async (ev) => {
    ev.preventDefault();
    const row = rows.find(r => r.run_id === a.dataset.run) || {};
    const res = await fetch(`/api/run/${a.dataset.run}`);
    if (!res.ok) {                                   // 결과 파일이 없는 실행(예: 초기 워크플로) — 요약 숫자만 보여준다
      resetView();
      ["collected","picked","drafted","verified"].forEach(k => setFunnel(k, row[k] ?? "–"));
      setFunnel("published", row.dry_run ? `${row.published ?? 0} (dry)` : (row.published ?? "–"));
      logEl.textContent = `이 실행(${a.dataset.run})은 건수 요약만 남아 있어 로그와 카드를 볼 수 없습니다.\n결과 파일(store/runs/<id>.json) 저장은 그 이후 실행부터 적용됩니다.`;
      $("#cardlist").innerHTML = "<p class='meta'>카드 기록 없음</p>";
      return;
    }
    const s = await res.json();
    logEl.textContent = (s.log || []).join("\n");
    ["collected","picked","drafted","verified"].forEach(k => setFunnel(k, (s[k]||[]).length));
    renderCards(s);
  }));
  renderSourceBars(recent);
}

function renderSourceBars(rows) {
  const totals = {};
  rows.forEach(r => Object.entries(r.by_source || {}).forEach(([name, n]) => {
    totals[name] = (totals[name] || 0) + n;
  }));
  const max = Math.max(1, ...Object.values(totals));
  $("#sourcebars").innerHTML = Object.entries(totals)
    .sort((a, b) => b[1] - a[1])
    .map(([name, n]) => `<div class="bar"><span class="bar-label">${esc(name)}</span><span class="bar-fill" style="width:${Math.round((n / max) * 100)}%"></span><span class="bar-n">${n}</span></div>`)
    .join("") || "<p class='meta'>데이터가 없습니다.</p>";
}

async function syncFromGithub() {
  const btn = $("#sync"), msg = $("#syncmsg");
  btn.disabled = true; msg.textContent = "가져오는 중…";
  try {
    const r = await (await fetch("/api/sync", { method: "POST" })).json();
    msg.textContent = r.ok ? "GitHub 기록을 가져왔습니다" : "가져오기 실패: " + r.output;
    if (r.ok) await loadHistory();
  } catch (e) {
    msg.textContent = "가져오기 실패: " + e;
  } finally {
    btn.disabled = false;
  }
}

$("#run").addEventListener("click", startRun);
$("#sync").addEventListener("click", syncFromGithub);
loadHistory();
