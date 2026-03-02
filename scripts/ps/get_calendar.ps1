# get_calendar.ps1 — fetch calendar events for the next N days
# Outputs JSON to stdout.
#
# Usage:
#   pwsh scripts/ps/get_calendar.ps1 [-Days 7]

param(
    [int]$Days = 7
)

Import-Module Microsoft.Graph.Authentication, Microsoft.Graph.Calendar -ErrorAction Stop

$ctx = Get-MgContext
if (-not $ctx) {
    Write-Error "Not authenticated. Run scripts/ps/connect.ps1 first."
    exit 1
}

$start = (Get-Date).ToString("yyyy-MM-ddT00:00:00")
$end   = (Get-Date).AddDays($Days).ToString("yyyy-MM-ddT23:59:59")

$events = Get-MgUserCalendarView -UserId "me" -StartDateTime $start -EndDateTime $end `
    -Property "id,subject,start,end,location,attendees,bodyPreview,isAllDay,isCancelled,organizer,importance,onlineMeetingUrl" `
    -All

$result = $events | Where-Object { -not $_.IsCancelled } | ForEach-Object {
    [ordered]@{
        id             = $_.Id
        subject        = $_.Subject
        start          = $_.Start.DateTime
        end            = $_.End.DateTime
        is_all_day     = $_.IsAllDay
        location       = $_.Location.DisplayName
        organizer      = $_.Organizer.EmailAddress.Address
        importance     = $_.Importance
        online_url     = $_.OnlineMeetingUrl
        body_preview   = $_.BodyPreview
        attendees      = $_.Attendees | ForEach-Object {
            [ordered]@{
                name   = $_.EmailAddress.Name
                email  = $_.EmailAddress.Address
                status = $_.Status.Response
            }
        }
    }
}

$result | ConvertTo-Json -Depth 5
