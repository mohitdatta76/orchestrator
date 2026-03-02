# get_direct_reports.ps1 — fetch your direct reports and their direct reports
# Walks two levels (appropriate for M2 / manager of managers).
# Outputs JSON to stdout.
#
# Usage:
#   pwsh scripts/ps/get_direct_reports.ps1

Import-Module Microsoft.Graph.Authentication, Microsoft.Graph.Users -ErrorAction Stop

$ctx = Get-MgContext
if (-not $ctx) {
    Write-Error "Not authenticated. Run scripts/ps/connect.ps1 first."
    exit 1
}

function Get-ReportInfo($userId) {
    $u = Get-MgUser -UserId $userId `
        -Property "id,displayName,mail,jobTitle,department,officeLocation,accountEnabled"
    [ordered]@{
        id              = $u.Id
        name            = $u.DisplayName
        email           = $u.Mail
        title           = $u.JobTitle
        department      = $u.Department
        office          = $u.OfficeLocation
    }
}

$me = Get-MgUser -UserId "me" -Property "id,displayName,mail,jobTitle"

# Level 1: your direct reports
$l1 = Get-MgUserDirectReport -UserId "me" -All
$reports = $l1 | ForEach-Object {
    $info = Get-ReportInfo $_.Id

    # Level 2: their direct reports
    $l2 = Get-MgUserDirectReport -UserId $_.Id -All -ErrorAction SilentlyContinue
    $info["direct_reports"] = $l2 | ForEach-Object { Get-ReportInfo $_.Id }

    $info
}

[ordered]@{
    me      = [ordered]@{ name = $me.DisplayName; email = $me.Mail; title = $me.JobTitle }
    reports = $reports
} | ConvertTo-Json -Depth 6
