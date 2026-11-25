#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simulador de balancas do BovinuScale.

Simula o hardware real: cada balanca sob uma panela mede o peso bruto
(panela + comida) e envia para o servidor via:
    POST /api/readings  { "scale_id": "BAL-01", "gross_g": <peso> }

Comportamento:
  - Comeca com as panelas cheias.
  - A cada ciclo, parte do alimento e "consumido" (peso cai).
  - Quando uma panela fica muito baixa, a cozinha "repoe" (peso sobe).

Uso:
  python simulator.py                # ritmo padrao (1 leitura a cada 3s)
  python simulator.py --interval 1   # mais rapido
  python simulator.py --speed 8      # consumo 8x mais agressivo (demo)

Dica para demo: rode o servidor com acompanhamento rapido:
  Windows PowerShell:  $env:MONITOR_INTERVAL=30; python server.py
"""

import argparse
import json
import random
import time
import urllib.request

SERVER = "http://127.0.0.1:8000"


def http_get(path):
    with urllib.request.urlopen(SERVER + path, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SERVER + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=3.0,
                    help="segundos entre leituras (padrao 3)")
    ap.add_argument("--speed", type=float, default=3.0,
                    help="fator de consumo (maior = esvazia mais rapido)")
    args = ap.parse_args()

    pots = http_get("/api/pots")
    if not pots:
        print("Nenhuma panela cadastrada. Inicie o server.py primeiro.")
        return

    # Estado: alimento liquido atual de cada panela (comeca cheia)
    estado = {}
    for p in pots:
        estado[p["scale_id"]] = {
            "net": p["capacity_g"],
            "tare": p["tare_g"],
            "cap": p["capacity_g"],
            "name": p["name"],
        }

    print(f"Simulando {len(pots)} balancas. Ctrl+C para parar.")
    print("-" * 56)
    try:
        while True:
            for sid, st in estado.items():
                # consumo aleatorio proporcional a capacidade
                consumo = random.uniform(0, st["cap"] * 0.01 * args.speed)
                st["net"] = max(0.0, st["net"] - consumo)

                # reposicao quando fica baixo (simula a cozinha trocando a panela)
                if st["net"] <= st["cap"] * 0.12 and random.random() < 0.6:
                    st["net"] = st["cap"] * random.uniform(0.9, 1.0)
                    acao = "REPOSTA"
                else:
                    acao = ""

                gross = round(st["tare"] + st["net"], 1)
                try:
                    http_post("/api/readings",
                              {"scale_id": sid, "gross_g": gross})
                except Exception as e:  # noqa
                    print("Falha ao enviar:", e)
                    continue

                pct = round(st["net"] / st["cap"] * 100)
                flag = f"  <-- {acao}" if acao else ""
                print(f"{sid} {st['name'][:18]:<18} {pct:3d}%  "
                      f"bruto={gross:>7.0f}g{flag}")
            print("-" * 56)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSimulador encerrado.")


if __name__ == "__main__":
    main()
