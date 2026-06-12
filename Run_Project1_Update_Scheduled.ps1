$ErrorActionPreference = "Continue"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogPath = Join-Path $ProjectDir "automation_last_run.log"

Add-Content -Path $LogPath -Value "===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') scheduled PowerShell run ====="
Set-Location $ProjectDir

& py -m pip install -r requirements.txt *>> $LogPath
if ($LASTEXITCODE -ne 0) {
    Add-Content -Path $LogPath -Value "pip exit code: $LASTEXITCODE"
    exit $LASTEXITCODE
}

& py scripts\update_project1_monthly.py --source spartan --output-dir $ProjectDir *>> $LogPath
$ExitCode = $LASTEXITCODE
Add-Content -Path $LogPath -Value "script exit code: $ExitCode"
exit $ExitCode
