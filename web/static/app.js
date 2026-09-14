const $ = (s) => document.querySelector(s);
const logEl = $("#log");

function setFunnel(k, v) { const el = document.querySelector(`[data-k="${k}"]`); if (el) el.textContent = v; }

function resetView() {
  logEl.textContent = "";
  ["collected","picked","drafted","verified","published"].forEach(k => setFunnel(k, "–"));
  $("#cardlist").innerHTML = "";
}

function onUpdate(node, u) {
  (u.log || []).forEach(l => logEl.textContent += l + "\n");
  if (u.collected) setFunnel("collected", u.collected.length);
  if (u.picked) setFunnel("picked", u.picked.length);
  if (u.drafted) setFunnel("drafted", Number($("[data-k=drafted]").textContent) || 0 + u.drafted.length);
  if (u.verified) setFunnel("verified", u.verified.length);
  if (node === "publish") setFunnel("published", u.published_count ?? "–");
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

function renderCards(state) { /* Task 9에서 채운다 */ }
async function loadHistory() { /* Task 10에서 채운다 */ }

$("#run").addEventListener("click", startRun);
loadHistory();
