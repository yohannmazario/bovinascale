const $ = (id) => document.getElementById(id);
let soundOn = localStorage.getItem("bovinu_mesa_beep") !== "0";
let seenPaid = null;
let audioCtx = null;

function fmtClock(d) { return d.toLocaleTimeString("pt-BR", { hour12: false }); }
function fmtMin(sec) {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m} min ${s}s` : `${s}s`;
}
function beep() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const now = audioCtx.currentTime;
    [880, 988, 1174].forEach((freq, i) => {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.connect(g); g.connect(audioCtx.destination);
      o.type = "square";
      o.frequency.value = freq;
      const t = now + i * 0.18;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.22, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
      o.start(t); o.stop(t + 0.17);
    });
  } catch (e) {}
}
function toast(title, msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `<div class="tt">${title}</div><div class="tm">${msg}</div>`;
  $("toasts").appendChild(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 300); }, 7000);
}
function paintSound() {
  $("btnSound").textContent = soundOn ? "🔔 Alertas" : "🔕 Alertas";
  $("btnSound").classList.toggle("ghost", !soundOn);
}

async function act(id, action) {
  const r = await fetch(`/api/mesas/${id}/${action}`, { method: "POST" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "falha");
  return data;
}

function render(data) {
  const resumo = data.resumo || {};
  $("pillTotal").textContent = `Mesas: ${resumo.total || 0}`;
  $("pillLivre").textContent = `Livres: ${resumo.livre || 0}`;
  $("pillOcupada").textContent = `Ocupadas: ${resumo.ocupada || 0}`;
  $("pillLiberada").textContent = `Liberadas: ${resumo.liberada || 0}`;

  const liberadas = (data.mesas || []).filter((m) => m.status === "liberada");
  $("banner").innerHTML = liberadas.length
    ? `<div class="banner-lib">MESA LIBERADA NO CAIXA: ${liberadas.map((m) => m.numero).join(", ")}. Pode limpar e disponibilizar.</div>`
    : "";

  if (seenPaid === null) {
    seenPaid = new Set(liberadas.map((m) => m.id + ":" + m.paid_at));
  } else {
    liberadas.forEach((m) => {
      const key = m.id + ":" + m.paid_at;
      if (!seenPaid.has(key)) {
        seenPaid.add(key);
        toast("Mesa liberada", `Mesa ${m.numero} pagou no caixa.`);
        if (soundOn) beep();
      }
    });
  }

  $("grid").innerHTML = (data.mesas || []).map((m) => {
    const label = m.status === "livre" ? "Livre" : m.status === "ocupada" ? "Ocupada" : "Liberada";
    const when = m.status === "ocupada" ? `No salão há ${fmtMin(m.ocupada_ha_s)}` : m.status === "liberada" ? "Pagamento confirmado" : "Aguardando cliente";
    const btn = m.status === "livre"
      ? `<button class="btn" data-act="ocupar" data-id="${m.id}">Simular chegada</button>`
      : m.status === "liberada"
        ? `<button class="btn" data-act="disponibilizar" data-id="${m.id}">Disponibilizar</button>`
        : `<button class="btn ghost" data-act="pagar" data-id="${m.id}">Simular pagamento</button>`;
    return `<article class="mesa ${m.status}">
      <div class="edge"></div>
      <div class="mesa-top">
        <div>
          <div class="num">${m.numero}</div>
          <div class="chairs">${m.cadeiras} cadeiras</div>
        </div>
        <div class="qr" data-qr="${m.id}" data-num="${m.numero}" data-url="${m.checkin_url}" title="Abrir QR">
          <img src="/api/mesas/${m.id}/qr.svg" alt="QR mesa ${m.numero}">
        </div>
      </div>
      <span class="badge ${m.status === "livre" ? "OK" : m.status === "ocupada" ? "REPOR_AGORA" : "ATENCAO"}">${label}</span>
      <div class="when">${when}</div>
      <div class="actions">${btn}</div>
    </article>`;
  }).join("");

  document.querySelectorAll("[data-act]").forEach((b) => {
    b.addEventListener("click", async () => {
      await act(b.dataset.id, b.dataset.act);
      refresh();
    });
  });
  document.querySelectorAll("[data-qr]").forEach((el) => {
    el.addEventListener("click", () => {
      $("qrTitle").textContent = "Mesa " + el.dataset.num;
      $("qrImg").src = "/api/mesas/" + el.dataset.qr + "/qr.svg";
      $("qrUrl").textContent = el.dataset.url;
      $("qrModal").classList.add("open");
    });
  });
}

async function refresh() {
  try {
    const r = await fetch("/api/mesas");
    render(await r.json());
    $("pillConn").textContent = "● Online";
    $("pillConn").className = "pill conn ok";
  } catch (e) {
    $("pillConn").textContent = "● Offline";
    $("pillConn").className = "pill conn danger";
  }
}

$("btnSound").addEventListener("click", () => {
  soundOn = !soundOn;
  localStorage.setItem("bovinu_mesa_beep", soundOn ? "1" : "0");
  paintSound();
  if (soundOn) beep();
});
$("qrClose").addEventListener("click", () => $("qrModal").classList.remove("open"));
$("qrModal").addEventListener("click", (e) => { if (e.target.id === "qrModal") $("qrModal").classList.remove("open"); });
setInterval(() => { $("clock").textContent = fmtClock(new Date()); }, 1000);
$("clock").textContent = fmtClock(new Date());
paintSound();
refresh();
setInterval(refresh, 2000);
