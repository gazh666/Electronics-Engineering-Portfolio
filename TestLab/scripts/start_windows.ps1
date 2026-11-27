# TestLab 一键启动（Windows / conda kaifa 环境）
# 用法: .\scripts\start_windows.ps1
# 停止: 在运行窗口按 Ctrl+C
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location $ProjectRoot

Write-Host "TestLab - SIMULATION MODE"
Write-Host "结果目录: $(if ($env:TESTLAB_RESULTS_DIR) { $env:TESTLAB_RESULTS_DIR } else { Join-Path $ProjectRoot 'results' })"

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "Conda is unavailable. Open Miniconda Prompt or configure Conda first."
}

conda run -n kaifa python -c "import streamlit"

if ($LASTEXITCODE -ne 0) {
    throw "The kaifa environment or Streamlit is unavailable."
}

conda run --no-capture-output -n kaifa python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501

exit $LASTEXITCODE
