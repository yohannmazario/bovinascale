// BovinuScale · Relatório do Dia (Atribuicao 2: consumo total por balanca)
function fmtKg(g) { return g == null ? "–" : (g / 1000).toFixed(2) + " kg"; }

// currentDay comeca nulo: o servidor devolve a data LOCAL dele (evita erro de fuso)
let currentDay = null;

function renderChart(itens) {
  const chart = document.getElementById("chart");
  const data = [...itens].filter((i) => i.consumido_g > 0).sort((a, b) => b.consumido_g - a.consumido_g);
  if (!data.length) {
    chart.innerHTML = `<p style="color:var(--muted);font-size:13px">Sem consumo registrado neste dia.</p>`;
    return;
  }
  const max = Math.max(...data.map((i) => i.consumido_g));
  chart.innerHTML = data.map((i) => {
    const w = Math.max(2, (i.consumido_g / max) * 100);
    return `<div class="chart-row">
      <div class="chart-label" title="${i.name}">${i.name}</div>
      <div class="chart-track"><div class="chart-bar" style="width:${w}%"></div></div>
      <div class="chart-val">${fmtKg(i.consumido_g)}</div>
    </div>`;
  }).join("");
}

function renderHourChart(hourly, peakHour) {
  const chart = document.getElementById("hourChart");
  const entries = Object.entries(hourly || {}).map(([h, g]) => [Number(h), g]);
  if (!entries.length) {
    chart.innerHTML = `<p style="color:var(--muted);font-size:13px">Sem consumo por horário neste dia.</p>`;
    return;
  }
  const max = Math.max(...entries.map(([, g]) => g));
  chart.innerHTML = entries.map(([h, g]) => {
    const w = Math.max(2, (g / max) * 100);
    const peak = h === peakHour ? " peak" : "";
    return `<div class="chart-row${peak}">
      <div class="chart-label">${String(h).padStart(2, "0")}h</div>
      <div class="chart-track"><div class="chart-bar" style="width:${w}%"></div></div>
      <div class="chart-val">${fmtKg(g)}</div>
    </div>`;
  }).join("");
}

async function load() {
  const url = currentDay ? "/api/report?day=" + currentDay : "/api/report";
  const r = await fetch(url);
  const data = await r.json();
  currentDay = data.day;

  document.getElementById("dayName").textContent = data.weekday_name || "";
  document.getElementById("unit").textContent = "Unidade: " + (data.unit || "–");
  document.getElementById("datePick").value = data.day;

  const totalPorcoes = data.itens.reduce((a, i) => a + i.porcoes_estimadas, 0);
  const totalRefills = data.itens.reduce((a, i) => a + i.reposicoes, 0);
  document.getElementById("kpiTotal").textContent = data.total_consumido_kg.toFixed(2);
  document.getElementById("kpiPorcoes").textContent = Math.round(totalPorcoes);
  document.getElementById("kpiRefills").textContent = totalRefills;
  document.getElementById("kpiSobra").textContent = (data.total_sobra_kg || 0).toFixed(2);
  document.getElementById("kpiPico").textContent =
    data.peak_hour == null ? "—" : String(data.peak_hour).padStart(2, "0") + "h";

  renderHourChart(data.hourly, data.peak_hour);
  renderChart(data.itens);

  const itens = [...data.itens].sort((a, b) => b.consumido_g - a.consumido_g);
  document.getElementById("rows").innerHTML = itens.map((i) => `<tr>
      <td><strong>${i.scale_id}</strong></td><td>${i.name}</td><td>${i.location || ""}</td>
      <td class="num">${fmtKg(i.consumido_g)}</td><td class="num">${i.porcoes_estimadas}</td>
      <td class="num">${i.reposicoes}</td><td class="num">${i.atual_g == null ? "–" : fmtKg(i.atual_g)}</td>
      <td class="num">${i.leituras}</td></tr>`).join("");

  document.getElementById("ftConsumo").textContent = data.total_consumido_kg.toFixed(2) + " kg";
  document.getElementById("ftPorcoes").textContent = Math.round(totalPorcoes);
  document.getElementById("ftRefills").textContent = totalRefills;
  document.getElementById("ftSobra").textContent = (data.total_sobra_kg || 0).toFixed(2) + " kg";
}

document.getElementById("btnReload").addEventListener("click", load);
document.getElementById("datePick").addEventListener("change", (e) => {
  currentDay = e.target.value || currentDay;
  load();
});
document.getElementById("btnCsv").addEventListener("click", () => {
  window.location.href = "/api/report.csv?day=" + currentDay;
});
load();
