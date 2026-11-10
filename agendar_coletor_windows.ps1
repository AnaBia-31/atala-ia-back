# Agenda o coletor de preços no Agendador de Tarefas do Windows (a cada 6 horas).
# Use se o GitHub Actions não conseguir acessar as lojas. O PC precisa estar ligado
# nos horários da coleta (se estiver desligado, roda assim que ligar).
#
# Uso (PowerShell, na pasta do atala-ia-back, com o venv já criado):
#   .\agendar_coletor_windows.ps1 -Api "https://atala-ia-back.onrender.com"
#
# Para remover depois:
#   Unregister-ScheduledTask -TaskName "Atala.ia - Coletor de precos" -Confirm:$false

param(
    [string]$Api = "http://127.0.0.1:8000"
)

$pasta = $PSScriptRoot
$python = Join-Path $pasta "venv\Scripts\python.exe"
$coletor = Join-Path $pasta "coletor.py"
$log = Join-Path $pasta "coletor.log"

if (-not (Test-Path $python)) {
    Write-Error "Não achei $python. Crie o venv antes (veja o README)."
    exit 1
}

# cmd /c para salvar a saída num arquivo de log
$comando = "/c `"`"$python`" `"$coletor`" --api $Api >> `"$log`" 2>&1`""
$acao = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $comando -WorkingDirectory $pasta
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours 6)
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName "Atala.ia - Coletor de precos" -Action $acao -Trigger $gatilho `
    -Settings $config -Description "Coleta preços para o Atala.ia ($Api)" -Force | Out-Null

Write-Host "Agendado! Primeira coleta em 1 minuto, depois a cada 6 horas."
Write-Host "Resultado de cada coleta: $log"
