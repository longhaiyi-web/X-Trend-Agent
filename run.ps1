param(
    [int]$Port = 8501
)

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Error "未找到 .venv。请先按 README.md 的步骤创建虚拟环境并安装依赖。"
    exit 1
}

& $venvPython -m streamlit run (Join-Path $projectRoot "app.py") --server.port $Port

