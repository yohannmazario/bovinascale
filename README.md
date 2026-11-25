# BovinuScale · Bovinu's Grill — Monitoramento de Panelas por Balança

Protótipo de hackathon para o **Grupo Bovinu's** (identidade **Bovinu's Grill**) que resolve o **Tópico 1 – A Ideia**:
cada panela do buffet tem uma **balança por baixo**, integrada a este software, com **2 atribuições**:

1. **Acompanhamento de 10 em 10 minutos** — avisa a cozinha quanto de alimento
   resta em cada panela e sinaliza a **necessidade de troca/reposição**.
2. **Registro total do consumo por balança no final do dia** — relatório com o
   quanto foi servido de cada prato.

Feito em **Python puro (biblioteca padrão)** — não precisa instalar nada.

---

## Como rodar

### Opção rápida (demo)
```powershell
.\start.ps1                # acompanhamento a cada 30s
.\start.ps1 -Intervalo 15  # mais rápido
.\start.ps1 -Simulador     # também abre o simulador automático
```

### Manual
```powershell
python server.py
```
Abra no navegador:
- Painel da cozinha: http://127.0.0.1:8000/
- Relatório do dia: http://127.0.0.1:8000/report.html

Por padrão o acompanhamento roda **de 10 em 10 minutos** (600 s). Para a demo:
```powershell
$env:MONITOR_INTERVAL=15; python server.py
```

---

## Funcionalidades

### Painel da cozinha
- Status ao vivo por panela (% , kg, status OK / Atenção / Repor)
- **Slider + botões** para simular a balança (servir, ±250 g, encher, esvaziar)
- **Peso exato em gramas** digitável em cada card
- **Previsão de esgotamento** (minutos até o limite de reposição)
- **Mini-gráfico** da tendência de peso
- **Porções restantes** estimadas (~120 g)
- **Alertas sonoros + toast** quando uma panela entra em “Repor”
- **Indicador Online/Offline**
- **Encher todas** / **Simular serviço** (modo demonstração)

### Cardápio por dia da semana
- Menu lateral com Segunda–Domingo e contagem de pratos
- Cardápio variável (pratos fixos + pratos do dia)
- **Gerenciar cardápio**: adicionar, editar e remover pratos
- Balança **metrificada**: tara e capacidade em kg/g + % de reposição
- **Zerar leituras de hoje** (útil na apresentação)

### Relatório do dia
- Consumo total (kg), porções, reposições, **sobra** e **horário de pico**
- Gráfico de consumo **por horário** e **por prato**
- Seletor de data
- **Exportar CSV** e Imprimir/PDF

---

## Integração com a balança real

Cada balança (ou um ESP32/Arduino com célula de carga **HX711**) só precisa
enviar o peso bruto em gramas:

```http
POST /api/readings
Content-Type: application/json

{ "scale_id": "BAL-01", "gross_g": 7234.5 }
```

Alternativa (UI / testes): enviar o peso líquido direto:
```json
{ "scale_id": "BAL-01", "net_g": 6000 }
```

---

## API

| Método | Rota                   | Descrição                                        |
|--------|------------------------|--------------------------------------------------|
| POST   | `/api/readings`        | Balança envia uma leitura de peso                |
| GET    | `/api/status?weekday=N`| Estado das panelas de um dia (Seg=0 … Dom=6)     |
| GET    | `/api/kitchen-updates` | Histórico dos acompanhamentos (10 em 10 min)     |
| GET    | `/api/report`          | Relatório de consumo (`?day=AAAA-MM-DD`)         |
| GET    | `/api/report.csv`      | Exportação CSV do relatório                      |
| GET    | `/api/pots`            | Lista completa do cardápio                       |
| POST   | `/api/pots`            | Cadastra/edita um prato (com `weekdays`)         |
| DELETE | `/api/pots?scale_id=X` | Remove um prato do cardápio                      |
| POST   | `/api/snapshot`        | Força um acompanhamento imediato                 |
| POST   | `/api/reset`           | Zera leituras do dia                             |
| POST   | `/api/demo/fill`       | Enche todas as panelas do dia                    |
| POST   | `/api/demo/serve`      | Simula uma rodada de consumo                     |

### Cadastrar um prato
`weekdays` usa o padrão Segunda=0 … Domingo=6.
```json
{
  "scale_id": "BAL-13",
  "name": "Costela ao Bafo",
  "location": "Estação Grill",
  "tare_g": 1500,
  "capacity_g": 7000,
  "refill_pct": 25,
  "weekdays": [2, 5]
}
```

---

## Como o consumo é calculado

O consumo do dia é a **soma de todas as quedas** de peso líquido medidas pela
balança. Quando o peso **sobe** (a cozinha repôs a panela), isso é contado como
**reposição**, não como consumo.

## Status das panelas

| Status        | Faixa         | Cor      |
|---------------|---------------|----------|
| OK            | > 30%         | Verde    |
| Atenção       | 15% – 30%     | Amarelo  |
| Repor agora   | ≤ 15%         | Vermelho |
| Vazia         | ≤ 5%          | Vermelho |

Além disso, cada panela tem seu próprio limite `refill_pct` que dispara o alerta
de **REPOR** no painel.

---

## Arquivos

```
server.py       # servidor + API + banco (SQLite) + monitor de 10 min
simulator.py    # simulador das balanças (demo sem hardware)
start.ps1       # partida rápida para demonstração
web/
  index.html    # painel da cozinha
  report.html   # relatório de consumo do dia
  app.js, report.js, styles.css, favicon.svg
bovinus.db      # criado automaticamente na primeira execução
```

> Protótipo para validação da ideia. Em produção, trocar SQLite por um banco
> central e as balanças passam a enviar leituras reais via rede (Wi-Fi).
