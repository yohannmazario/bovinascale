#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BovinuScale - Sistema de Monitoramento de Panelas por Balanca
Grupo Bovinu's | Hackathon

Topico 1 - A Ideia:
  Cada panela do buffet tem uma balanca por baixo. A balanca envia o peso
  para este software, que tem 2 atribuicoes:
    1) Acompanhamento de 10 em 10 minutos, avisando a cozinha a quantidade
       de alimento disponivel em cada panela e a necessidade de troca/reposicao.
    2) Registro total do que foi consumido por balanca no final do dia.

Stack: Python puro (biblioteca padrao). Nao precisa instalar nada.
  - http.server  -> API REST + arquivos estaticos
  - sqlite3      -> banco de dados local (bovinus.db)
  - threading    -> monitor que roda de 10 em 10 minutos

Como as balancas se integram:
  Cada balanca (ou o ESP32/Arduino com celula de carga HX711) envia um POST:
      POST /api/readings  { "scale_id": "BAL-01", "gross_g": 7234.5 }
  'gross_g' = peso bruto em gramas (panela + comida).
  O sistema desconta a tara (peso da panela vazia) e calcula o alimento liquido.
"""

import json
import os
import random
import re
import socket
import sqlite3
import threading
import time
from datetime import datetime, date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from qr_svg import to_svg as qr_svg

# Dias da semana (padrao Python: Segunda=0 ... Domingo=6)
WEEKDAY_NAMES = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"]

# ----------------------------------------------------------------------------
# Configuracao
# ----------------------------------------------------------------------------
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DB_PATH = os.path.join(BASE_DIR, "bovinus.db")

# Intervalo do acompanhamento da cozinha (Atribuicao 1).
# Requisito: "de 10 em 10 minutos" = 600s.
# Para demonstrar mais rapido, defina a variavel de ambiente MONITOR_INTERVAL.
MONITOR_INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "600"))

DB_LOCK = threading.Lock()

# ----------------------------------------------------------------------------
# Banco de dados
# ----------------------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with DB_LOCK, db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pots (
                scale_id      TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                location      TEXT,
                tare_g        REAL NOT NULL,   -- peso da panela vazia
                capacity_g    REAL NOT NULL,   -- alimento liquido quando cheia
                refill_pct    REAL NOT NULL,   -- % em que precisa repor (0-100)
                unit          TEXT DEFAULT 'Bovinu''s Grill',
                weekdays      TEXT DEFAULT '0,1,2,3,4,5,6',  -- dias servidos
                active        INTEGER DEFAULT 1,
                created_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS readings (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                scale_id  TEXT NOT NULL,
                gross_g   REAL NOT NULL,
                net_g     REAL NOT NULL,
                ts        REAL NOT NULL,
                day       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_readings_scale_day
                ON readings(scale_id, day);

            CREATE TABLE IF NOT EXISTS kitchen_updates (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           REAL NOT NULL,
                scale_id     TEXT NOT NULL,
                name         TEXT,
                net_g        REAL,
                pct          REAL,
                status       TEXT,
                needs_refill INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_updates_ts
                ON kitchen_updates(ts);

            CREATE TABLE IF NOT EXISTS mesas (
                id           INTEGER PRIMARY KEY,
                cadeiras     INTEGER NOT NULL,
                status       TEXT NOT NULL DEFAULT 'livre',
                occupied_at  REAL,
                paid_at      REAL,
                created_at   TEXT
            );
            """
        )
        # Migracao: adiciona a coluna weekdays em bancos antigos
        ensure_column(conn, "pots", "weekdays", "TEXT DEFAULT '0,1,2,3,4,5,6'")
        conn.execute(
            "UPDATE pots SET weekdays='0,1,2,3,4,5,6' "
            "WHERE weekdays IS NULL OR weekdays=''"
        )
        seed_pots(conn)
        seed_mesas(conn)


def ensure_column(conn, table, col, decl):
    """Adiciona uma coluna se ela ainda nao existir (migracao simples)."""
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def seed_pots(conn):
    """Cria o cardapio de exemplo (variavel por dia da semana) na 1a execucao."""
    cur = conn.execute("SELECT COUNT(*) AS c FROM pots")
    if cur.fetchone()["c"] > 0:
        return
    now = datetime.now().isoformat()
    # Dias: Seg=0, Ter=1, Qua=2, Qui=3, Sex=4, Sab=5, Dom=6
    exemplos = [
        # scale_id, nome, local, tara(g), capacidade(g), repor%, dias
        ("BAL-01", "Arroz Branco",         "Buffet quente - A", 1200, 6000, 25, "0,1,2,3,4,5,6"),
        ("BAL-02", "Feijao Tropeiro",      "Buffet quente - A", 1400, 5000, 25, "0,1,2,3,4,5,6"),
        ("BAL-03", "Farofa da Casa",       "Buffet quente - B", 1100, 4000, 30, "0,1,2,3,4,5,6"),
        ("BAL-04", "Salada Vinagrete",     "Buffet frio - A",    900, 3500, 20, "0,1,2,3,4,5,6"),
        ("BAL-05", "Pao de Alho",          "Buffet quente - C",  800, 3000, 35, "0,1,2,3,4,5,6"),
        # Pratos do dia (variaveis)
        ("BAL-06", "Virado a Paulista",    "Buffet quente - D", 1400, 5000, 25, "0"),         # Segunda
        ("BAL-07", "Macarronada ao Sugo",  "Buffet quente - D", 1500, 5000, 25, "1,4"),       # Ter/Sex
        ("BAL-08", "Feijoada Completa",    "Buffet quente - D", 1600, 7000, 25, "2,5"),       # Qua/Sab
        ("BAL-09", "Strogonoff de Frango", "Buffet quente - E", 1500, 5500, 25, "3"),         # Quinta
        ("BAL-10", "Bacalhau ao Forno",    "Buffet quente - E", 1400, 4500, 25, "4"),         # Sexta
        ("BAL-11", "Picanha na Brasa",     "Estacao Grill",     1800, 6000, 30, "5,6"),       # Sab/Dom
        ("BAL-12", "Costela Fogo de Chao", "Estacao Grill",     2000, 8000, 30, "6"),         # Domingo
    ]
    conn.executemany(
        "INSERT INTO pots (scale_id,name,location,tare_g,capacity_g,refill_pct,weekdays,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(s, n, l, t, c, r, w, now) for (s, n, l, t, c, r, w) in exemplos],
    )


def seed_mesas(conn):
    """Cria 24 mesas numeradas, com 2 a 10 cadeiras, se o salao ainda estiver vazio."""
    n = conn.execute("SELECT COUNT(*) AS c FROM mesas").fetchone()["c"]
    if n > 0:
        return
    rng = random.Random()
    now = datetime.now().isoformat()
    rows = [(i, rng.randint(2, 10), "livre", now) for i in range(1, 25)]
    conn.executemany(
        "INSERT INTO mesas (id, cadeiras, status, created_at) VALUES (?,?,?,?)",
        rows,
    )


def lan_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def public_base(handler=None):
    forced = os.environ.get("PUBLIC_BASE", "").strip().rstrip("/")
    if forced:
        return forced
    external = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if external:
        return external
    host = ""
    proto = "http"
    if handler is not None:
        raw_host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host") or ""
        host = raw_host.split(",")[0].strip()
        raw_proto = handler.headers.get("X-Forwarded-Proto") or ""
        proto = raw_proto.split(",")[0].strip() or "http"
    hostname = host.split(":")[0].lower()
    if hostname and hostname not in ("127.0.0.1", "localhost", "0.0.0.0"):
        if not proto.startswith("http"):
            proto = "http"
        if hostname.endswith(("trycloudflare.com", "onrender.com", "koyeb.app")):
            proto = "https"
        return f"{proto}://{host}"
    return f"http://{lan_ip()}:{PORT}"


def mesa_dict(row, now=None, base=None):
    now = now if now is not None else time.time()
    base = base or public_base()
    occ = row["occupied_at"]
    return {
        "id": row["id"],
        "numero": f"{row['id']:02d}",
        "cadeiras": row["cadeiras"],
        "status": row["status"],
        "occupied_at": occ,
        "paid_at": row["paid_at"],
        "ocupada_ha_s": int(now - occ) if occ and row["status"] == "ocupada" else None,
        "checkin_url": f"{base}/checkin.html?mesa={row['id']}",
    }


def list_mesas(conn, base=None):
    now = time.time()
    base = base or public_base()
    rows = conn.execute("SELECT * FROM mesas ORDER BY id").fetchall()
    mesas = [mesa_dict(r, now, base) for r in rows]
    resumo = {"livre": 0, "ocupada": 0, "liberada": 0, "total": len(mesas)}
    for m in mesas:
        if m["status"] in resumo:
            resumo[m["status"]] += 1
    return {"base": base, "resumo": resumo, "mesas": mesas}


# ----------------------------------------------------------------------------
# Regras de negocio
# ----------------------------------------------------------------------------

def today_str():
    return date.today().isoformat()


def current_weekday():
    return datetime.now().weekday()  # Segunda=0 ... Domingo=6


def parse_weekdays(s):
    """Converte '0,2,5' -> [0, 2, 5]."""
    out = []
    for part in str(s or "").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


def served_on(pot, weekday):
    return weekday in parse_weekdays(pot["weekdays"])


def classify(pct):
    """Define o status da panela a partir do % de alimento disponivel."""
    if pct <= 5:
        return "VAZIA"
    if pct <= 15:
        return "REPOR_AGORA"
    if pct <= 30:
        return "ATENCAO"
    return "OK"


def consumption_rate(conn, scale_id, cap):
    """Estima a taxa de consumo (g/min) a partir das leituras recentes.
    Considera apenas as quedas de peso (ignora reposicoes)."""
    rows = conn.execute(
        "SELECT net_g, ts FROM readings WHERE scale_id=? ORDER BY ts DESC LIMIT 15",
        (scale_id,),
    ).fetchall()
    if len(rows) < 2:
        return 0.0
    rows = list(reversed(rows))
    refill_jump = (cap or 1) * 0.10
    consumed = 0.0
    prev = None
    for r in rows:
        net = max(0.0, r["net_g"])
        if prev is not None:
            delta = net - prev
            if delta < 0:
                consumed += -delta
        prev = net
    elapsed_min = (rows[-1]["ts"] - rows[0]["ts"]) / 60.0
    # Janela minima para evitar taxas absurdas em ajustes muito rapidos
    if elapsed_min < 0.33:
        return 0.0
    return consumed / elapsed_min


def pot_snapshot(conn, pot):
    """Monta o estado atual de uma panela a partir da ultima leitura."""
    row = conn.execute(
        "SELECT gross_g, net_g, ts FROM readings WHERE scale_id=? ORDER BY ts DESC LIMIT 1",
        (pot["scale_id"],),
    ).fetchone()

    cap = pot["capacity_g"] or 1
    weekdays = parse_weekdays(pot["weekdays"])
    if row is None:
        return {
            "scale_id": pot["scale_id"],
            "name": pot["name"],
            "location": pot["location"],
            "unit": pot["unit"],
            "capacity_g": cap,
            "tare_g": pot["tare_g"],
            "refill_pct": pot["refill_pct"],
            "weekdays": weekdays,
            "net_g": None,
            "pct": None,
            "status": "SEM_LEITURA",
            "needs_refill": False,
            "rate_g_min": 0.0,
            "eta_min": None,
            "porcoes_restantes": None,
            "last_ts": None,
        }

    net = max(0.0, row["net_g"])
    pct = round(min(100.0, (net / cap) * 100), 1)
    status = classify(pct)
    needs_refill = pct <= pot["refill_pct"]

    # Previsao de esgotamento ate o limite de reposicao
    rate = consumption_rate(conn, pot["scale_id"], cap)
    threshold_net = cap * (pot["refill_pct"] / 100.0)
    eta_min = None
    if rate > 0.5 and net > threshold_net:
        eta_min = int(round((net - threshold_net) / rate))
    porcoes_restantes = round(net / 120.0, 1)  # porcao media ~120g

    return {
        "scale_id": pot["scale_id"],
        "name": pot["name"],
        "location": pot["location"],
        "unit": pot["unit"],
        "capacity_g": cap,
        "tare_g": pot["tare_g"],
        "refill_pct": pot["refill_pct"],
        "weekdays": weekdays,
        "net_g": round(net, 1),
        "pct": pct,
        "status": status,
        "needs_refill": needs_refill,
        "rate_g_min": round(rate, 1),
        "eta_min": eta_min,
        "porcoes_restantes": porcoes_restantes,
        "last_ts": row["ts"],
    }


def all_status(conn, weekday=None):
    pots = conn.execute("SELECT * FROM pots WHERE active=1 ORDER BY scale_id").fetchall()
    if weekday is not None:
        pots = [p for p in pots if served_on(p, weekday)]
    return [pot_snapshot(conn, p) for p in pots]


def consumption_report(conn, day=None):
    """
    Atribuicao 2: registro total consumido por balanca no dia.
    Consumo = soma de todas as QUEDAS de peso liquido entre leituras.
    Reposicoes (subidas de peso) nao contam como consumo.
    """
    day = day or today_str()
    try:
        wd = date.fromisoformat(day).weekday()
    except ValueError:
        wd = current_weekday()
    pots = conn.execute("SELECT * FROM pots WHERE active=1 ORDER BY scale_id").fetchall()
    pots = [p for p in pots if served_on(p, wd)]
    itens = []
    total_consumido = 0.0
    total_sobra = 0.0
    hourly = {}  # hora -> gramas consumidas (para hora de pico)
    for p in pots:
        rows = conn.execute(
            "SELECT net_g, ts FROM readings WHERE scale_id=? AND day=? ORDER BY ts ASC",
            (p["scale_id"], day),
        ).fetchall()

        consumido = 0.0
        reposto = 0.0
        refills = 0
        cap = p["capacity_g"] or 1
        refill_jump = cap * 0.10  # subida > 10% da capacidade = reposicao
        prev = None
        prev_ts = None
        for r in rows:
            net = max(0.0, r["net_g"])
            if prev is not None:
                delta = net - prev
                if delta < 0:
                    consumido += -delta
                    hr = datetime.fromtimestamp(r["ts"]).hour
                    hourly[hr] = hourly.get(hr, 0.0) + (-delta)
                elif delta >= refill_jump:
                    reposto += delta
                    refills += 1
            prev = net
            prev_ts = r["ts"]

        atual = round(prev, 1) if prev is not None else None
        if atual is not None:
            total_sobra += atual
        porcoes = round(consumido / 120.0, 1)  # porcao media estimada ~120g
        total_consumido += consumido
        itens.append(
            {
                "scale_id": p["scale_id"],
                "name": p["name"],
                "location": p["location"],
                "consumido_g": round(consumido, 1),
                "consumido_kg": round(consumido / 1000.0, 2),
                "porcoes_estimadas": porcoes,
                "reposicoes": refills,
                "reposto_g": round(reposto, 1),
                "leituras": len(rows),
                "atual_g": atual,
                "capacity_g": cap,
            }
        )

    peak_hour = None
    peak_consumo = 0.0
    if hourly:
        peak_hour = max(hourly, key=hourly.get)
        peak_consumo = hourly[peak_hour]

    return {
        "day": day,
        "weekday": wd,
        "weekday_name": WEEKDAY_NAMES[wd],
        "unit": pots[0]["unit"] if pots else "Bovinu's Grill",
        "total_consumido_g": round(total_consumido, 1),
        "total_consumido_kg": round(total_consumido / 1000.0, 2),
        "total_sobra_g": round(total_sobra, 1),
        "total_sobra_kg": round(total_sobra / 1000.0, 2),
        "peak_hour": peak_hour,
        "peak_consumo_kg": round(peak_consumo / 1000.0, 2),
        "hourly": {str(h): round(g, 1) for h, g in sorted(hourly.items())},
        "itens": itens,
    }


def run_kitchen_check(conn):
    """Executa 1 acompanhamento (Atribuicao 1) e grava no log da cozinha."""
    snaps = all_status(conn, current_weekday())
    now = time.time()
    rows = []
    for s in snaps:
        if s["status"] == "SEM_LEITURA":
            continue
        rows.append(
            (now, s["scale_id"], s["name"], s["net_g"], s["pct"],
             s["status"], 1 if s["needs_refill"] else 0)
        )
    if rows:
        conn.executemany(
            "INSERT INTO kitchen_updates (ts,scale_id,name,net_g,pct,status,needs_refill) "
            "VALUES (?,?,?,?,?,?,?)",
            rows,
        )
    return len([r for r in rows if r[6] == 1])


def monitor_loop():
    """Thread que dispara o acompanhamento de 10 em 10 minutos."""
    while True:
        time.sleep(MONITOR_INTERVAL)
        try:
            with DB_LOCK, db() as conn:
                pendentes = run_kitchen_check(conn)
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] Acompanhamento da cozinha executado. "
                  f"Panelas para repor: {pendentes}")
        except Exception as e:  # noqa
            print("Erro no monitor:", e)


# ----------------------------------------------------------------------------
# HTTP Handler
# ----------------------------------------------------------------------------

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silencia o log padrao

    # ---------- helpers ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        safe = os.path.normpath(path).lstrip("\\/")
        full = os.path.join(WEB_DIR, safe)
        if not os.path.abspath(full).startswith(os.path.abspath(WEB_DIR)):
            self.send_error(403)
            return
        if not os.path.isfile(full):
            self.send_error(404)
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path

        if p == "/api/status":
            qs = parse_qs(parsed.query)
            wd_raw = qs.get("weekday", [None])[0]
            weekday = int(wd_raw) if (wd_raw and wd_raw.lstrip("-").isdigit()) \
                else current_weekday()
            with DB_LOCK, db() as conn:
                data = all_status(conn, weekday)
            return self._json({
                "monitor_interval": MONITOR_INTERVAL,
                "server_time": time.time(),
                "weekday": weekday,
                "weekday_names": WEEKDAY_NAMES,
                "pots": data,
            })

        if p == "/api/pots":
            # Retorna TODO o cardapio (todos os dias) para o gerenciador
            with DB_LOCK, db() as conn:
                rows = conn.execute(
                    "SELECT * FROM pots WHERE active=1 ORDER BY scale_id"
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["weekdays"] = parse_weekdays(r["weekdays"])
                out.append(d)
            return self._json(out)

        if p == "/api/report/today":
            with DB_LOCK, db() as conn:
                return self._json(consumption_report(conn))

        if p == "/api/report":
            qs = parse_qs(parsed.query)
            day = qs.get("day", [None])[0]
            with DB_LOCK, db() as conn:
                return self._json(consumption_report(conn, day))

        if p == "/api/report.csv":
            qs = parse_qs(parsed.query)
            day = qs.get("day", [None])[0]
            with DB_LOCK, db() as conn:
                rep = consumption_report(conn, day)
            lines = ["Balanca;Prato;Local;Consumido_kg;Porcoes;Reposicoes;Sobra_kg;Leituras"]
            for i in rep["itens"]:
                sobra = (i["atual_g"] or 0) / 1000.0
                lines.append(
                    f'{i["scale_id"]};{i["name"]};{i.get("location","")};'
                    f'{i["consumido_kg"]:.2f};{i["porcoes_estimadas"]};'
                    f'{i["reposicoes"]};{sobra:.2f};{i["leituras"]}'
                )
            lines.append(
                f'TOTAL;;;{rep["total_consumido_kg"]:.2f};;;'
                f'{rep["total_sobra_kg"]:.2f};'
            )
            body = ("\ufeff" + "\r\n".join(lines)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="consumo-{rep["day"]}.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if p == "/api/kitchen-updates":
            with DB_LOCK, db() as conn:
                rows = conn.execute(
                    "SELECT * FROM kitchen_updates ORDER BY ts DESC LIMIT 60"
                ).fetchall()
            return self._json([dict(r) for r in rows])

        if p == "/api/mesas":
            with DB_LOCK, db() as conn:
                return self._json(list_mesas(conn, public_base(self)))

        mesa_match = re.fullmatch(r"/api/mesas/(\d+)(?:/(qr\.svg))?$", p)
        if mesa_match and mesa_match.group(2) == "qr.svg":
            mid = int(mesa_match.group(1))
            with DB_LOCK, db() as conn:
                row = conn.execute("SELECT * FROM mesas WHERE id=?", (mid,)).fetchone()
            if row is None:
                return self._json({"error": "mesa nao encontrada"}, 404)
            svg = qr_svg(mesa_dict(row, base=public_base(self))["checkin_url"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(svg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(svg)
            return

        return self._serve_static(p)

    # ---------- POST ----------
    def do_POST(self):
        parsed = urlparse(self.path)
        p = parsed.path

        if p == "/api/readings":
            body = self._read_json()
            scale_id = body.get("scale_id")
            gross = body.get("gross_g")
            net_in = body.get("net_g")  # alternativa: peso liquido direto (UI)
            if not scale_id or (gross is None and net_in is None):
                return self._json(
                    {"error": "scale_id e (gross_g ou net_g) sao obrigatorios"}, 400)

            now = time.time()
            with DB_LOCK, db() as conn:
                pot = conn.execute(
                    "SELECT * FROM pots WHERE scale_id=?", (scale_id,)
                ).fetchone()
                if pot is None:
                    return self._json({"error": f"balanca {scale_id} nao cadastrada"}, 404)
                try:
                    if gross is None:
                        net = max(0.0, float(net_in))
                        gross = net + pot["tare_g"]
                    else:
                        gross = float(gross)
                        net = max(0.0, gross - pot["tare_g"])
                except (TypeError, ValueError):
                    return self._json({"error": "peso invalido"}, 400)
                conn.execute(
                    "INSERT INTO readings (scale_id,gross_g,net_g,ts,day) VALUES (?,?,?,?,?)",
                    (scale_id, gross, net, now, today_str()),
                )
                snap = pot_snapshot(conn, pot)
            return self._json({"ok": True, "snapshot": snap})

        if p == "/api/snapshot":
            # Forca um acompanhamento imediato (util na demonstracao)
            with DB_LOCK, db() as conn:
                pendentes = run_kitchen_check(conn)
            return self._json({"ok": True, "panelas_para_repor": pendentes})

        if p == "/api/reset":
            # Zera as leituras/acompanhamentos de um dia (util para demo)
            body = self._read_json()
            day = body.get("day") or today_str()
            with DB_LOCK, db() as conn:
                n1 = conn.execute("DELETE FROM readings WHERE day=?", (day,)).rowcount
                conn.execute(
                    "DELETE FROM kitchen_updates WHERE ts >= ?",
                    (datetime.fromisoformat(day + "T00:00:00").timestamp(),),
                )
            return self._json({"ok": True, "day": day, "leituras_removidas": n1})

        if p == "/api/demo/fill":
            # Enche todas as panelas do dia (ou weekday informado)
            body = self._read_json()
            wd = body.get("weekday")
            if wd is None:
                wd = current_weekday()
            else:
                wd = int(wd)
            now = time.time()
            with DB_LOCK, db() as conn:
                pots = [p for p in conn.execute(
                    "SELECT * FROM pots WHERE active=1").fetchall() if served_on(p, wd)]
                for pot in pots:
                    net = pot["capacity_g"]
                    gross = net + pot["tare_g"]
                    conn.execute(
                        "INSERT INTO readings (scale_id,gross_g,net_g,ts,day) "
                        "VALUES (?,?,?,?,?)",
                        (pot["scale_id"], gross, net, now, today_str()),
                    )
            return self._json({"ok": True, "panelas": len(pots), "weekday": wd})

        if p == "/api/demo/serve":
            # Simula uma rodada de clientes: consome 5-18% de cada panela
            body = self._read_json()
            wd = body.get("weekday")
            if wd is None:
                wd = current_weekday()
            else:
                wd = int(wd)
            now = time.time()
            with DB_LOCK, db() as conn:
                pots = [p for p in conn.execute(
                    "SELECT * FROM pots WHERE active=1").fetchall() if served_on(p, wd)]
                for pot in pots:
                    last = conn.execute(
                        "SELECT net_g FROM readings WHERE scale_id=? "
                        "ORDER BY ts DESC LIMIT 1", (pot["scale_id"],)
                    ).fetchone()
                    if last is None:
                        net = pot["capacity_g"] * random.uniform(0.7, 1.0)
                    else:
                        net = max(0.0, last["net_g"])
                    drop = pot["capacity_g"] * random.uniform(0.05, 0.18)
                    net = max(0.0, net - drop)
                    gross = net + pot["tare_g"]
                    conn.execute(
                        "INSERT INTO readings (scale_id,gross_g,net_g,ts,day) "
                        "VALUES (?,?,?,?,?)",
                        (pot["scale_id"], gross, net, now, today_str()),
                    )
            return self._json({"ok": True, "panelas": len(pots), "weekday": wd})

        mesa_post = re.fullmatch(r"/api/mesas/(\d+)/(ocupar|pagar|disponibilizar)", p)
        if mesa_post:
            mid = int(mesa_post.group(1))
            action = mesa_post.group(2)
            now = time.time()
            with DB_LOCK, db() as conn:
                row = conn.execute("SELECT * FROM mesas WHERE id=?", (mid,)).fetchone()
                if row is None:
                    return self._json({"error": "mesa nao encontrada"}, 404)
                status = row["status"]
                if action == "ocupar":
                    if status != "ocupada":
                        conn.execute(
                            "UPDATE mesas SET status='ocupada', occupied_at=?, paid_at=NULL WHERE id=?",
                            (now, mid),
                        )
                elif action == "pagar":
                    if status != "ocupada":
                        return self._json({"error": "so e possivel pagar uma mesa ocupada"}, 409)
                    conn.execute(
                        "UPDATE mesas SET status='liberada', paid_at=? WHERE id=?",
                        (now, mid),
                    )
                else:  # disponibilizar
                    conn.execute(
                        "UPDATE mesas SET status='livre', occupied_at=NULL, paid_at=NULL WHERE id=?",
                        (mid,),
                    )
                row = conn.execute("SELECT * FROM mesas WHERE id=?", (mid,)).fetchone()
                return self._json({"ok": True, "mesa": mesa_dict(row)})

        if p == "/api/pots":
            body = self._read_json()
            req = ["scale_id", "name", "tare_g", "capacity_g", "refill_pct"]
            if any(not str(body.get(k, "")).strip() for k in req):
                return self._json({"error": f"campos obrigatorios: {req}"}, 400)
            # weekdays pode vir como lista [0,2,5] ou string "0,2,5"
            wd = body.get("weekdays", "0,1,2,3,4,5,6")
            if isinstance(wd, list):
                wd = ",".join(str(int(x)) for x in wd)
            wd = ",".join(str(x) for x in parse_weekdays(wd)) or "0,1,2,3,4,5,6"
            try:
                tare = float(body["tare_g"])
                cap = float(body["capacity_g"])
                refill = float(body["refill_pct"])
            except (TypeError, ValueError):
                return self._json({"error": "tara/capacidade/% invalidos"}, 400)
            with DB_LOCK, db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO pots "
                    "(scale_id,name,location,tare_g,capacity_g,refill_pct,unit,weekdays,active,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,1,?)",
                    (
                        str(body["scale_id"]).strip(), str(body["name"]).strip(),
                        body.get("location", ""), tare, cap, refill,
                        body.get("unit", "Bovinu's Grill"), wd,
                        datetime.now().isoformat(),
                    ),
                )
            return self._json({"ok": True})

        return self._json({"error": "rota nao encontrada"}, 404)

    # ---------- DELETE ----------
    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/pots":
            qs = parse_qs(parsed.query)
            sid = qs.get("scale_id", [None])[0]
            if not sid:
                return self._json({"error": "scale_id obrigatorio"}, 400)
            with DB_LOCK, db() as conn:
                conn.execute("DELETE FROM pots WHERE scale_id=?", (sid,))
            return self._json({"ok": True, "removido": sid})
        return self._json({"error": "rota nao encontrada"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    init_db()
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 60)
    print("  BovinuScale - Monitoramento de Panelas por Balanca")
    print("  Grupo Bovinu's")
    print("=" * 60)
    base = public_base()
    print(f"  Painel da cozinha    : http://127.0.0.1:{PORT}/")
    print(f"  Atendimento (salao)  : http://127.0.0.1:{PORT}/atendimento.html")
    print(f"  Caixa                : http://127.0.0.1:{PORT}/caixa.html")
    print(f"  QR das mesas (rede)  : {base}/atendimento.html")
    print(f"  Relatorio do dia     : http://127.0.0.1:{PORT}/report.html")
    print(f"  Acompanhamento a cada: {MONITOR_INTERVAL}s "
          f"({MONITOR_INTERVAL // 60} min)")
    print("=" * 60)
    print("  Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        server.shutdown()


if __name__ == "__main__":
    main()
