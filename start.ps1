# BovinuScale · partida rapida para demonstracao
# Uso:  .\start.ps1
#       .\start.ps1 -Intervalo 15   # acompanhamento a cada 15s (demo)

param(
  [int]$Intervalo = 30,
  [switch]$Simulador
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "  BovinuScale · Bovinu's Grill" -ForegroundColor Red
Write-Host "  Acompanhamento a cada $Intervalo segundos" -ForegroundColor DarkYellow
Write-Host "  Painel:    http://127.0.0.1:8000/" -ForegroundColor White
Write-Host "  Relatorio: http://127.0.0.1:8000/report.html" -ForegroundColor White
Write-Host ""

$env:MONITOR_INTERVAL = "$Intervalo"

if ($Simulador) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot'; python simulator.py --speed 6"
}

python server.py
