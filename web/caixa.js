const $ = (id) => document.getElementById(id);

async function pagar(id) {
  const r = await fetch(`/api/mesas/${id}/pagar`, { method: "POST" });
  const data = await r.json();
  if (!r.ok) alert(data.error || "Não foi possível liberar.");
  load();
}

async function load() {
  const data = await (await fetch("/api/mesas")).json();
  const ocupadas = data.mesas.filter((m) => m.status === "ocupada");
  const liberadas = data.mesas.filter((m) => m.status === "liberada");
  $("ocupadas").innerHTML = ocupadas.length
    ? ocupadas.map((m) => `<div class="caixa-row">
        <div><b>Mesa ${m.numero}</b><div class="when">${m.cadeiras} cadeiras</div></div>
        <button class="btn" data-id="${m.id}">Registrar pagamento</button>
      </div>`).join("")
    : `<p style="color:var(--muted)">Nenhuma mesa ocupada no momento.</p>`;
  $("liberadas").innerHTML = liberadas.length
    ? liberadas.map((m) => `<div class="caixa-row">
        <div><b>Mesa ${m.numero}</b><div class="when">Liberada · aguardando limpeza</div></div>
        <span class="badge ATENCAO">Liberada</span>
      </div>`).join("")
    : `<p style="color:var(--muted)">Nenhuma mesa liberada agora.</p>`;
  document.querySelectorAll("[data-id]").forEach((b) => {
    b.addEventListener("click", () => pagar(b.dataset.id));
  });
}
load();
setInterval(load, 3000);
