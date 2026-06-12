$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "Project1_LSQ_Monthly_Update"
$RunScript = Join-Path $ProjectDir "Run_Project1_Update_Scheduled.ps1"

if (!(Test-Path $RunScript)) {
    throw "Could not find $RunScript"
}

$TaskRun = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"' + $RunScript + '\"'
& schtasks.exe /Create /TN $TaskName /TR $TaskRun /SC MONTHLY /D 10 /ST 09:00 /F | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "It will run monthly on the 10th at 9:00 AM when this Windows user is logged in."
Write-Host "Output folder: $ProjectDir"
