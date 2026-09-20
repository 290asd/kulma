<#
.SYNOPSIS
    Kulma - Windows uninstall script

.DESCRIPTION
    Closes the tray app, removes its autostart entry and Start Menu shortcut,
    and removes the Task Scheduler tasks 'Kulma' and 'Kulma-Reindex'. Does not
    delete settings, the photo index or the log ($env:APPDATA\Kulma), nor the
    JPEG conversion cache and icon ($env:LOCALAPPDATA\Kulma) - delete those
    by hand if you want a full cleanup.
#>

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Kulma - removing the tray app and Task Scheduler tasks"

Get-CimInstance Win32_Process -Filter "Name LIKE 'pythonw%'" |
    Where-Object { $_.CommandLine -like "*kulma_tray.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "-> Tray app closed" }
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Kulma" -ErrorAction SilentlyContinue
Write-Host "-> Autostart removed"
Remove-Item (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Kulma.lnk") -ErrorAction SilentlyContinue
Write-Host "-> Start Menu shortcut removed"


foreach ($name in @("Kulma", "Kulma-Reindex")) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "-> Removed: $name"
    } else {
        Write-Host "-> Not found (already removed?): $name"
    }
}

Write-Host ""
Write-Host "Uninstall complete. The scripts ($env:LOCALAPPDATA\Kulma\bin), settings"
Write-Host "and index ($env:APPDATA\Kulma) were left in place - delete them by hand"
Write-Host "for a full cleanup:"
Write-Host "  Remove-Item -Recurse -Force `"$env:LOCALAPPDATA\Kulma`""
Write-Host "  Remove-Item -Recurse -Force `"$env:APPDATA\Kulma`""
