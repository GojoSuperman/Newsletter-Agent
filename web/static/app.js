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
    return `<article class="card ${ok ? "" : "rejected"}">
      <h3><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.headline)}</a></h3>
      <p>${esc(d.summary)}</p><p class="why">왜 중요한가 · ${esc(d.why)}</p>
      <div class="meta">${esc(d.source)} · ${esc(d.at.slice(0,16).replace("T"," "))}</div>${reason}</article>`;
  }).join("") || "<p class='meta'>발행 카드가 없습니다.</p>";
  setFunnel("published", state.dry_run ? `${(state.verified||[]).length} (dry)` : (state.verified||[]).length);
}
async function loadHistory() {
  const rows = await (await fetch("/api/runs")).json();
  const head = "<tr><th>실행</th><th>수집</th><th>선별</th><th>취재</th><th>검수</th><th>발행</th><th>실패 소스</th><th>초</th></tr>";
  $("#runs").innerHTML = head + rows.slice(-30).reverse().map(r => {
    const secs = Object.values(r.seconds || {}).reduce((a, b) => a + b, 0).toFixed(1);
    const id = `<a href="#" data-run="${esc(r.run_id)}">${esc(r.run_id)}</a>${r.dry_run ? " (dry)" : ""}`;
    return `<tr><td>${id}</td><td>${r.collected}</td><td>${r.picked}</td><td>${r.drafted}</td><td>${r.verified}</td><td>${r.published}</td><td>${esc((r.dead_sources||[]).join(", "))}</td><td>${secs}</td></tr>`;
  }).join("");
  $("#runs").querySelectorAll("a[data-run]").forEach(a => a.addEventListener("click", async (ev) => {
    ev.preventDefault();
    const s = await (await fetch(`/api/run/${a.dataset.run}`)).json();
    logEl.textContent = (s.log || []).join("\n");
    ["collected","picked","drafted","verified"].forEach(k => setFunnel(k, (s[k]||[]).length));
    renderCards(s);
  }));
}

$("#run").addEventListener("click", startRun);
loadHistory();
