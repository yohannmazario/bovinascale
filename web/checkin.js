const params = new URLSearchParams(location.search);
const id = params.get("mesa");
const num = document.getElementById("num");
const state = document.getElementById("state");
const detail = document.getElementById("detail");

function show(mesa, msg) {
  num.textContent = mesa.numero;
  state.textContent = msg;
  state.className = "state " + mesa.status;
  detail.textContent = mesa.cadeiras + " cadeiras · " + (
    mesa.status === "ocupada" ? "mesa marcada como ocupada no salão" :
    mesa.status === "liberada" ? "pagamento já registrado no caixa" :
    "mesa livre"
  );
}

async function run() {
  if (!id) {
    state.textContent = "QR sem número de mesa.";
    return;
  }
  num.textContent = String(id).padStart(2, "0");
  const r = await fetch(`/api/mesas/${id}/ocupar`, { method: "POST" });
  const data = await r.json();
  if (!r.ok) {
    state.textContent = data.error || "Mesa não encontrada.";
    return;
  }
  const mesa = data.mesa;
  if (mesa.status === "ocupada") show(mesa, "Mesa ocupada");
  else show(mesa, mesa.status);
}
run();
