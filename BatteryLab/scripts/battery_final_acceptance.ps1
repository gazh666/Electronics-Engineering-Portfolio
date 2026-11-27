$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)

$commands = @(
    @("python", "-B", "-m", "scripts.hardening_afe"),
    @("python", "-B", "-m", "scripts.hardening_protection"),
    @("python", "-B", "-m", "scripts.hardening_charging"),
    @("python", "-B", "-m", "scripts.hardening_ecm"),
    @("python", "-B", "-m", "scripts.hardening_system"),
    @("python", "-B", "-m", "scripts.hardening_domain"),
    @("python", "-B", "-m", "scripts.hardening_eda"),
    @("python", "-B", "-m", "scripts.audit_resume_metrics"),
    @("python", "-B", "-m", "scripts.hardening_portfolio_v2"),
    @("python", "-B", "-m", "scripts.battery_stage10_demo"),
    @("python", "-B", "-m", "pytest", "tests", "-q")
)

$results = @()
foreach ($cmd in $commands) {
    $label = $cmd -join " "
    Write-Host "===== $label ====="
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $output = & conda run --no-capture-output -n kaifa_battery @cmd 2>&1
    $timer.Stop()
    $exit = $LASTEXITCODE
    $tail = ($output | Select-Object -Last 8) -join "`n"
    $results += [pscustomobject]@{
        command = $label
        exit_code = $exit
        duration_s = [math]::Round($timer.Elapsed.TotalSeconds, 2)
        output_tail = $tail
    }
    Write-Host "exit=$exit duration=$([math]::Round($timer.Elapsed.TotalSeconds,2))s"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dir = Join-Path "results\stage10" ("final_acceptance_" + $stamp)
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$results | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $dir "acceptance.json") -Encoding UTF8

$lines = @("# Final acceptance command log", "", "| command | exit code | duration (s) |", "|---|---|---|")
foreach ($item in $results) {
    $lines += ("| " + $item.command + " | " + $item.exit_code + " | " + $item.duration_s + " |")
}
$lines += @("", "## Output tails", "")
foreach ($item in $results) {
    $lines += @(("### " + $item.command), '```text', $item.output_tail, '```', "")
}
$lines -join "`n" | Set-Content -Path (Join-Path $dir "acceptance.md") -Encoding UTF8
Write-Host "WROTE $dir"
