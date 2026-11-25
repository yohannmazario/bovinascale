// BovinuScale · Bovinu's Grill — Painel da Cozinha
// Acompanhamento ao vivo + cardapio por dia + gerenciador +
// previsao de esgotamento, mini-grafico, peso exato e alertas.

const STATUS_LABEL = {
  OK: "OK", ATENCAO: "Atenção", REPOR_AGORA: "Repor agora",
  VAZIA: "Vazia", SEM_LEITURA: "Sem leitura",
};
const DIAS_LONGO = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const DIAS_CURTO = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
function hojeWeekday() { return (new Date().getDay() + 6) % 7; }

let monitorInterval = 600;
let lastCheckAt = Date.now();
let selectedWeekday = hojeWeekday();
let editingScale = null;

const cards = {};
let renderedKey = "";
let draggingId = null;
const sendTimers = {};
const hist = {};        // scale_id -> [net,...] (mini-grafico)
const prevRefill = {};  // scale_id -> bool (detecta transicao p/ REPOR)

// Preferencias persistidas
let notifyEnabled = localStorage.getItem("bovinu_notify") === "1";
let audioCtx = null;

const $ = (id) => document.getElementById(id);
function fmtClock(d) { return d.toLocaleTimeString("pt-BR", { hour12: false }); }
function fmtG(g) {
  if (g == null) return "–";
  if (g >= 1000) return (g / 1000).toFixed(2) + " kg";
  return Math.round(g) + " g";
}
function fromUnix(ts) { return new Date(ts * 1000); }
function classify(pct) {
  if (pct <= 5) return "VAZIA";
  if (pct <= 15) return "REPOR_AGORA";
  if (pct <= 30) return "ATENCAO";
  return "OK";
}
function diasLabel(arr) {
  if (!arr || arr.length === 0) return "—";
  if (arr.length === 7) return ["Todos os dias"];
  return [...arr].sort((a, b) => a - b).map((i) => DIAS_CURTO[i]);
}
async function getJSON(url, opts) { return (await fetch(url, opts)).json(); }

// ---------------- Alertas (som + toast) ----------------
function beep() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const o = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    o.connect(g); g.connect(audioCtx.destination);
    o.type = "triangle"; o.frequency.value = 880;
    g.gain.setValueAtTime(0.0001, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.25, audioCtx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.35);
    o.start(); o.stop(audioCtx.currentTime + 0.36);
  } catch (e) {}
}
function toast(title, msg) {
  const box = $("toasts");
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `<div class="tt">${title}</div><div class="tm">${msg}</div>`;
  box.appendChild(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 300); }, 6000);
}
function updateNotifyBtn() {
  $("btnNotify").textContent = (notifyEnabled ? "🔔" : "🔕") + " Alertas";
  $("btnNotify").classList.toggle("ghost", !notifyEnabled);
}

// ---------------- Envio de leitura ----------------
function sendReading(id, net) {
  net = Math.max(0, Math.round(net));
  fetch("/api/readings", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scale_id: id, net_g: net }),
  }).catch((e) => console.error(e));
}
function queueSend(id, net) {
  clearTimeout(sendTimers[id]);
  sendTimers[id] = setTimeout(() => sendReading(id, net), 120);
}
function paint(id, net) {
  const c = cards[id];
  if (!c) return;
  const pct = Math.min(100, (net / c.cap) * 100);
  const cls = classify(pct);
  c.net = net;
  c.fill.className = "fill-" + cls;
  c.fill.style.width = pct + "%";
  c.edge.className = "edge edge-" + cls;
  c.pctEl.textContent = Math.round(pct * 10) / 10 + "%";
  c.grams.textContent = fmtG(net) + " / " + fmtG(c.cap);
  c.badge.className = "badge " + cls;
  c.badge.textContent = STATUS_LABEL[cls];
  c.root.classList.toggle("needs-refill", pct <= c.refill);
}

// ---------------- Mini-grafico (sparkline) ----------------
function pushHist(id, net, cap) {
  if (!hist[id]) hist[id] = [];
  const arr = hist[id];
  if (arr.length === 0 || arr[arr.length - 1] !== net) arr.push(net);
  while (arr.length > 30) arr.shift();
  drawSpark(id, cap);
}
function drawSpark(id, cap) {
  const c = cards[id];
  if (!c || !c.spark) return;
  const arr = hist[id] || [];
  if (arr.length < 2) { c.spark.setAttribute("points", ""); return; }
  const n = arr.length;
  const pts = arr.map((v, i) => {
    const x = (i / (n - 1)) * 100;
    const y = 28 - Math.min(1, v / cap) * 26 - 1;
    return x.toFixed(1) + "," + y.toFixed(1);
  });
  c.spark.setAttribute("points", pts.join(" "));
}

// ---------------- Card ----------------
function buildCard(p) {
  const el = document.createElement("div");
  el.className = "card";
  const dias = diasLabel(p.weekdays).map((d) => `<span>${d}</span>`).join("");
  el.innerHTML = `
    <div class="edge"></div>
    <div class="scale-id">${p.scale_id}</div>
    <h2>${p.name}</h2>
    <div class="loc">${p.location || ""} · repor &lt; ${p.refill_pct}%</div>
    <div class="days">${dias}</div>
    <div class="bar"><span class="fill"></span></div>
    <div class="metrics"><div class="pct">–</div><div class="grams">– / ${fmtG(p.capacity_g)}</div></div>
    <div class="trendrow">
      <svg class="spark" viewBox="0 0 100 28" preserveAspectRatio="none"><polyline points=""/></svg>
      <span class="badge SEM_LEITURA">Sem leitura</span>
    </div>
    <div class="forecast" hidden></div>
    <div class="sim">
      <input type="range" class="slider" min="0" max="${p.capacity_g}" step="25" value="0">
      <div class="sim-btns">
        <button data-act="serve">− Servir porção</button>
        <button data-act="minus">− 250 g</button>
        <button data-act="plus">+ 250 g</button>
        <button data-act="fill" class="accent">Encher</button>
        <button data-act="empty" class="danger">Esvaziar</button>
      </div>
      <div class="exact">
        <input type="number" class="exact-input" min="0" max="${p.capacity_g}" placeholder="peso exato (g)">
        <button data-act="set">definir</button>
      </div>
    </div>
    <div class="last">Aguardando balança…</div>`;

  const refs = {
    root: el, edge: el.querySelector(".edge"), fill: el.querySelector(".fill"),
    pctEl: el.querySelector(".pct"), grams: el.querySelector(".grams"),
    badge: el.querySelector(".badge"), last: el.querySelector(".last"),
    slider: el.querySelector(".slider"), spark: el.querySelector(".spark polyline"),
    forecast: el.querySelector(".forecast"), exact: el.querySelector(".exact-input"),
    cap: p.capacity_g, refill: p.refill_pct, net: 0,
  };
  cards[p.scale_id] = refs;

  const slider = refs.slider;
  slider.addEventListener("pointerdown", () => (draggingId = p.scale_id));
  slider.addEventListener("input", () => {
    draggingId = p.scale_id;
    const net = Number(slider.value);
    paint(p.scale_id, net);
    queueSend(p.scale_id, net);
  });
  const stop = () => {
    if (draggingId === p.scale_id) {
      sendReading(p.scale_id, Number(slider.value));
      setTimeout(() => { if (draggingId === p.scale_id) draggingId = null; }, 400);
    }
  };
  slider.addEventListener("pointerup", stop);
  slider.addEventListener("change", stop);

  function apply(net) {
    const c = cards[p.scale_id];
    net = Math.max(0, Math.min(c.cap, net));
    slider.value = net;
    paint(p.scale_id, net);
    sendReading(p.scale_id, net);
  }
  el.querySelectorAll(".sim-btns button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const c = cards[p.scale_id];
      let net = c.net || 0;
      const act = btn.dataset.act;
      if (act === "serve") net -= 120;
      else if (act === "minus") net -= 250;
      else if (act === "plus") net += 250;
      else if (act === "fill") net = c.cap;
      else if (act === "empty") net = 0;
      apply(net);
    });
  });
  const setExact = () => {
    const v = Number(refs.exact.value);
    if (!isNaN(v)) { apply(v); refs.exact.value = ""; }
  };
  el.querySelector('[data-act="set"]').addEventListener("click", setExact);
  refs.exact.addEventListener("keydown", (e) => { if (e.key === "Enter") setExact(); });

  return el;
}

function setForecast(p) {
  const c = cards[p.scale_id];
  if (!c) return;
  const f = c.forecast;
  if (p.needs_refill) {
    f.hidden = false; f.className = "forecast danger";
    f.textContent = "⚠ Reposição necessária agora";
  } else if (p.eta_min != null && p.rate_g_min > 0) {
    f.hidden = false; f.className = "forecast";
    const r = p.rate_g_min >= 1000 ? (p.rate_g_min / 1000).toFixed(1) + " kg" : Math.round(p.rate_g_min) + " g";
    f.textContent = `⏳ Esgota em ~${p.eta_min} min · ${r}/min`;
  } else if (p.rate_g_min > 0) {
    f.hidden = false; f.className = "forecast";
    f.textContent = `↘ Consumo ~${Math.round(p.rate_g_min)} g/min`;
  } else {
    f.hidden = true;
  }
}

function renderStatus(data) {
  monitorInterval = data.monitor_interval || 600;
  const pots = data.pots || [];
  $("empty").hidden = pots.length > 0;

  const key = selectedWeekday + "|" + pots.map((p) => p.scale_id).join(",");
  if (key !== renderedKey) {
    const grid = $("grid");
    grid.innerHTML = "";
    for (const k in cards) delete cards[k];
    pots.forEach((p) => grid.appendChild(buildCard(p)));
    renderedKey = key;
  }

  const counts = { OK: 0, ATENCAO: 0, REPOR_AGORA: 0, VAZIA: 0 };
  pots.forEach((p) => { if (counts[p.status] != null) counts[p.status]++; });
  $("pillTotal").textContent = `Panelas: ${pots.length}`;
  $("pillOk").textContent = `OK: ${counts.OK}`;
  $("pillWarn").textContent = `Atenção: ${counts.ATENCAO}`;
  $("pillDanger").textContent = `Repor agora: ${counts.REPOR_AGORA + counts.VAZIA}`;

  const needing = pots.filter((p) => p.needs_refill);
  $("alerts").innerHTML = needing.map((p) =>
    `<div class="alert"><span class="tag">REPOR</span>
      <strong>${p.name}</strong> (${p.scale_id}) está em ${p.pct}% —
      restam ${fmtG(p.net_g)}. ${p.location || ""}</div>`).join("");

  pots.forEach((p) => {
    const c = cards[p.scale_id];
    if (!c) return;
    // Notificacao ao ENTRAR em estado de reposicao
    const was = prevRefill[p.scale_id] || false;
    if (p.needs_refill && !was && selectedWeekday === hojeWeekday()) {
      toast("Reposição necessária", `${p.name} (${p.scale_id}) em ${p.pct}%`);
      if (notifyEnabled) beep();
    }
    prevRefill[p.scale_id] = p.needs_refill;

    if (p.status === "SEM_LEITURA") { c.last.textContent = "Aguardando balança…"; c.forecast.hidden = true; return; }
    if (draggingId !== p.scale_id) { c.slider.value = p.net_g; paint(p.scale_id, p.net_g); }
    pushHist(p.scale_id, p.net_g, c.cap);
    setForecast(p);
    const por = p.porcoes_restantes != null ? ` · ~${p.porcoes_restantes} porções` : "";
    c.last.textContent = p.last_ts
      ? "Última leitura: " + fmtClock(fromUnix(p.last_ts)) + por
      : "Aguardando balança…";
  });
}

function renderFeed(updates) {
  const feed = $("feed");
  if (!updates.length) {
    feed.innerHTML = `<li><span class="t">Nenhum acompanhamento registrado ainda.</span></li>`;
    return;
  }
  feed.innerHTML = updates.map((u) => {
    const t = fmtClock(fromUnix(u.ts));
    return `<li class="${u.needs_refill ? "refill" : ""}">
      <div><strong>${u.name}</strong> — ${u.pct}%${u.needs_refill ? " · REPOR" : ""}</div>
      <span class="t">${t} · ${u.scale_id}</span></li>`;
  }).join("");
}

// ---------------- Menu lateral ----------------
async function buildDayList() {
  let pots = [];
  try { pots = await getJSON("/api/pots"); } catch (e) {}
  const counts = Array(7).fill(0);
  pots.forEach((p) => (p.weekdays || []).forEach((d) => { if (counts[d] != null) counts[d]++; }));
  const hoje = hojeWeekday();
  $("dayList").innerHTML = DIAS_LONGO.map((nome, i) =>
    `<button class="day-btn ${i === selectedWeekday ? "active" : ""}" data-wd="${i}">
      <span>${nome}${i === hoje ? ' <span class="today-tag">hoje</span>' : ""}</span>
      <span class="cnt">${counts[i]} pratos</span></button>`).join("");
  document.querySelectorAll(".day-btn").forEach((b) => {
    b.addEventListener("click", () => {
      selectedWeekday = Number(b.dataset.wd);
      document.querySelectorAll(".day-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      updateDayBadge();
      refresh();
    });
  });
}
function updateDayBadge() {
  const hoje = hojeWeekday();
  $("dayBadge").textContent = DIAS_LONGO[selectedWeekday] + (selectedWeekday === hoje ? " (hoje)" : "");
}

// ---------------- Modal: gerenciar cardápio ----------------
function buildDayChips() {
  $("f_days").innerHTML = DIAS_CURTO.map((d, i) =>
    `<button type="button" class="daychip" data-wd="${i}">${d}</button>`).join("");
  document.querySelectorAll("#f_days .daychip").forEach((c) =>
    c.addEventListener("click", () => c.classList.toggle("on")));
}
function selectedChips() {
  return [...document.querySelectorAll("#f_days .daychip.on")].map((c) => Number(c.dataset.wd));
}
function setChips(arr) {
  document.querySelectorAll("#f_days .daychip").forEach((c) =>
    c.classList.toggle("on", arr.includes(Number(c.dataset.wd))));
}
function toGrams(value, unit) {
  const v = parseFloat(value);
  if (isNaN(v)) return NaN;
  return unit === "kg" ? v * 1000 : v;
}
function showFormMsg(text, ok) {
  const m = $("formMsg");
  m.textContent = text;
  m.className = "msg " + (ok ? "ok" : "err");
  if (ok) setTimeout(() => (m.className = "msg"), 2500);
}
function resetForm() {
  editingScale = null;
  $("formTitle").textContent = "Adicionar prato";
  $("btnAddDish").textContent = "Adicionar ao cardápio";
  $("btnResetForm").style.display = "none";
  $("f_name").value = ""; $("f_scale").value = ""; $("f_scale").disabled = false;
  $("f_loc").value = "";
  $("f_tare").value = ""; $("f_tare_unit").value = "kg";
  $("f_cap").value = ""; $("f_cap_unit").value = "kg";
  $("f_refill").value = 25;
  setChips([selectedWeekday]);
  suggestScaleId();
}
async function suggestScaleId() {
  if (editingScale) return;
  try {
    const pots = await getJSON("/api/pots");
    let max = 0;
    pots.forEach((p) => { const m = /BAL-(\d+)/.exec(p.scale_id); if (m) max = Math.max(max, parseInt(m[1], 10)); });
    $("f_scale").value = "BAL-" + String(max + 1).padStart(2, "0");
  } catch (e) {}
}
async function loadDishes() {
  let pots = [];
  try { pots = await getJSON("/api/pots"); } catch (e) {}
  pots.sort((a, b) => a.scale_id.localeCompare(b.scale_id));
  $("dishList").innerHTML = pots.map((p) => {
    const dias = [].concat(diasLabel(p.weekdays)).join(" · ");
    return `<div class="dish-row">
      <div class="info"><b>${p.name}</b> <span style="color:var(--muted)">(${p.scale_id})</span>
        <div class="meta">${p.location || ""} · Cap. ${fmtG(p.capacity_g)} · Tara ${fmtG(p.tare_g)} · Repor &lt;${p.refill_pct}%<br>
          <span class="d">Dias: ${dias}</span></div></div>
      <div class="dish-actions">
        <button class="mini" data-edit="${p.scale_id}">Editar</button>
        <button class="mini del" data-del="${p.scale_id}">Remover</button>
      </div></div>`;
  }).join("") || `<p style="color:var(--muted);font-size:13px">Nenhum prato cadastrado.</p>`;
  document.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => removeDish(b.dataset.del)));
  document.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => editDish(b.dataset.edit, pots)));
}
function editDish(scaleId, pots) {
  const p = pots.find((x) => x.scale_id === scaleId);
  if (!p) return;
  editingScale = scaleId;
  $("formTitle").textContent = "Editar: " + p.name;
  $("btnAddDish").textContent = "Salvar alterações";
  $("btnResetForm").style.display = "inline-block";
  $("f_name").value = p.name;
  $("f_scale").value = p.scale_id; $("f_scale").disabled = true;
  $("f_loc").value = p.location || "";
  $("f_tare").value = p.tare_g; $("f_tare_unit").value = "g";
  $("f_cap").value = p.capacity_g; $("f_cap_unit").value = "g";
  $("f_refill").value = p.refill_pct;
  setChips(p.weekdays || []);
  $("f_name").focus();
}
async function addDish() {
  const name = $("f_name").value.trim();
  const scale = $("f_scale").value.trim();
  const tare = toGrams($("f_tare").value, $("f_tare_unit").value);
  const cap = toGrams($("f_cap").value, $("f_cap_unit").value);
  const refill = parseFloat($("f_refill").value);
  const dias = selectedChips();
  if (!name) return showFormMsg("Informe o nome do prato.", false);
  if (!scale) return showFormMsg("Informe o ID da balança.", false);
  if (isNaN(tare) || tare < 0) return showFormMsg("Tara inválida.", false);
  if (isNaN(cap) || cap <= 0) return showFormMsg("Capacidade inválida.", false);
  if (cap <= tare) return showFormMsg("Capacidade deve ser maior que a tara.", false);
  if (isNaN(refill) || refill < 1 || refill > 100) return showFormMsg("% de reposição entre 1 e 100.", false);
  if (dias.length === 0) return showFormMsg("Selecione ao menos um dia.", false);
  const r = await fetch("/api/pots", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scale_id: scale, name, location: $("f_loc").value.trim(),
      tare_g: tare, capacity_g: cap, refill_pct: refill, weekdays: dias }),
  }).then((x) => x.json());
  if (r.error) return showFormMsg(r.error, false);
  showFormMsg(editingScale ? "Prato atualizado!" : "Prato adicionado ao cardápio!", true);
  resetForm(); await loadDishes(); await buildDayList(); refresh();
}
async function removeDish(scaleId) {
  if (!confirm("Remover o prato " + scaleId + " do cardápio?")) return;
  await fetch("/api/pots?scale_id=" + encodeURIComponent(scaleId), { method: "DELETE" });
  await loadDishes(); await buildDayList(); refresh();
}
async function resetDay() {
  if (!confirm("Zerar todas as leituras e o consumo de hoje?")) return;
  await fetch("/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  for (const k in hist) delete hist[k];
  for (const k in prevRefill) delete prevRefill[k];
  toast("Dia zerado", "Leituras de hoje apagadas.");
  refresh();
}
function openModal() { $("manageModal").classList.add("open"); resetForm(); loadDishes(); }
function closeModal() { $("manageModal").classList.remove("open"); }

// ---------------- Clock / refresh ----------------
function tickClock() {
  $("clock").textContent = fmtClock(new Date());
  const elapsed = (Date.now() - lastCheckAt) / 1000;
  const remaining = Math.max(0, monitorInterval - (elapsed % monitorInterval));
  const m = Math.floor(remaining / 60), s = Math.floor(remaining % 60);
  $("nextCheck").textContent = `Próximo acompanhamento em ${m}:${String(s).padStart(2, "0")}`;
}
function setOnline(ok) {
  const el = $("pillConn");
  if (!el) return;
  el.textContent = ok ? "● Online" : "● Offline";
  el.classList.toggle("ok", ok);
  el.classList.toggle("danger", !ok);
}
async function refresh() {
  try {
    const [status, updates] = await Promise.all([
      getJSON("/api/status?weekday=" + selectedWeekday),
      getJSON("/api/kitchen-updates"),
    ]);
    setOnline(true);
    renderStatus(status);
    renderFeed(updates);
  } catch (e) {
    setOnline(false);
    console.error(e);
  }
}
async function demoFill() {
  const r = await fetch("/api/demo/fill", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ weekday: selectedWeekday }),
  }).then((x) => x.json());
  toast("Panelas cheias", `${r.panelas || 0} balanças do dia preenchidas.`);
  refresh();
}
async function demoServe() {
  const r = await fetch("/api/demo/serve", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ weekday: selectedWeekday }),
  }).then((x) => x.json());
  toast("Serviço simulado", `Rodada de clientes em ${r.panelas || 0} panelas.`);
  refresh();
}

// ---------------- Eventos ----------------
if (localStorage.getItem("bovinu_side") === "1") document.body.classList.add("side-collapsed");
$("btnSide").addEventListener("click", () => {
  document.body.classList.toggle("side-collapsed");
  localStorage.setItem("bovinu_side", document.body.classList.contains("side-collapsed") ? "1" : "0");
});
$("btnNotify").addEventListener("click", () => {
  notifyEnabled = !notifyEnabled;
  localStorage.setItem("bovinu_notify", notifyEnabled ? "1" : "0");
  updateNotifyBtn();
  if (notifyEnabled) beep();
});
$("btnManage").addEventListener("click", openModal);
$("btnCloseModal").addEventListener("click", closeModal);
$("manageModal").addEventListener("click", (e) => { if (e.target.id === "manageModal") closeModal(); });
$("btnAddDish").addEventListener("click", addDish);
$("btnResetForm").addEventListener("click", resetForm);
$("btnResetDay").addEventListener("click", resetDay);
$("btnFillAll").addEventListener("click", demoFill);
$("btnServe").addEventListener("click", demoServe);
$("btnSnapshot").addEventListener("click", async () => {
  await fetch("/api/snapshot", { method: "POST" });
  lastCheckAt = Date.now();
  toast("Acompanhamento", "Check-in da cozinha registrado.");
  refresh();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

// ---------------- Início ----------------
updateNotifyBtn();
buildDayChips();
buildDayList();
updateDayBadge();
setInterval(tickClock, 1000);
setInterval(refresh, 4000);
tickClock();
refresh();
