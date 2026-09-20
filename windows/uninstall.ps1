<#
.SYNOPSIS
    Kulma - Windows-poistoskripti

.DESCRIPTION
    Poistaa Task Scheduler -tehtavat 'Kulma' ja 'Kulma-Reindex'. Ei poista
    asetuksia, kuvaindeksia eika lokia ($env:APPDATA\Kulma) eika
    JPEG-muunnosvalimuistia ($env:LOCALAPPDATA\Kulma\cache) - poista ne
    kasin jos haluat siivota kokonaan.
#>

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Kulma - poistetaan Task Scheduler -tehtavat"

foreach ($name in @("Kulma", "Kulma-Reindex")) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "-> Poistettu: $name"
    } else {
        Write-Host "-> Ei loytynyt (jo poistettu?): $name"
    }
}

Write-Host ""
Write-Host "Tehtavat poistettu. Skriptit ($env:LOCALAPPDATA\Kulma\bin), asetukset"
Write-Host "ja indeksi ($env:APPDATA\Kulma) jaivat paikoilleen - poista ne kasin"
Write-Host "jos haluat siivota kokonaan:"
Write-Host "  Remove-Item -Recurse -Force `"$env:LOCALAPPDATA\Kulma`""
Write-Host "  Remove-Item -Recurse -Force `"$env:APPDATA\Kulma`""
