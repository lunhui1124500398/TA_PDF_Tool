$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = "D:\Conda_Data\envs\ta_ocr_gpu\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python environment not found: $pythonExe"
}

Set-Location $projectRoot
& $pythonExe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
