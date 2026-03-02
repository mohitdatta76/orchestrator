# get_people.ps1 — fetch the people Graph considers most relevant to you,
# based on your communication and collaboration patterns.
# Outputs JSON to stdout.
#
# Usage:
#   pwsh scripts/ps/get_people.ps1 [-Top 25]

param(
    [int]$Top = 25
)

Import-Module Microsoft.Graph.Authentication, Microsoft.Graph.People -ErrorAction Stop

$ctx = Get-MgContext
if (-not $ctx) {
    Write-Error "Not authenticated. Run scripts/ps/connect.ps1 first."
    exit 1
}

$people = Get-MgUserPerson -UserId "me" -Top $Top `
    -Property "id,displayName,scoredEmailAddresses,jobTitle,department,officeLocation,personType"

$result = $people | ForEach-Object {
    [ordered]@{
        name       = $_.DisplayName
        email      = ($_.ScoredEmailAddresses | Select-Object -First 1).Address
        title      = $_.JobTitle
        department = $_.Department
        office     = $_.OfficeLocation
        type       = $_.PersonType.Class   # "Person" vs "Group" etc.
    }
}

[ordered]@{
    fetched_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    top        = $Top
    people     = $result
} | ConvertTo-Json -Depth 4
