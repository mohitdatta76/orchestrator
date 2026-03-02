# get_email.ps1 — fetch high-signal email: flagged, high-importance, and
# messages where you're in the To field (not CC) from the last N days.
# Outputs JSON to stdout.
#
# Usage:
#   pwsh scripts/ps/get_email.ps1 [-Days 3]

param(
    [int]$Days = 3
)

Import-Module Microsoft.Graph.Authentication, Microsoft.Graph.Mail -ErrorAction Stop

$ctx = Get-MgContext
if (-not $ctx) {
    Write-Error "Not authenticated. Run scripts/ps/connect.ps1 first."
    exit 1
}

$since = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-ddTHH:mm:ss")
$props  = "id,subject,from,toRecipients,receivedDateTime,bodyPreview,importance,isRead,flag,conversationId,hasAttachments"

function Format-Message($m) {
    [ordered]@{
        id              = $m.Id
        subject         = $m.Subject
        from            = $m.From.EmailAddress.Address
        from_name       = $m.From.EmailAddress.Name
        received        = $m.ReceivedDateTime
        is_read         = $m.IsRead
        importance      = $m.Importance
        flagged         = ($m.Flag.FlagStatus -eq "Flagged")
        has_attachments = $m.HasAttachments
        preview         = $m.BodyPreview
        conversation_id = $m.ConversationId
        to              = $m.ToRecipients | ForEach-Object { $_.EmailAddress.Address }
    }
}

# Flagged messages (any age)
$flagged = Get-MgUserMessage -UserId "me" -All `
    -Filter "flag/flagStatus eq 'flagged'" `
    -Property $props |
    ForEach-Object { Format-Message $_ }

# High importance, recent
$highPri = Get-MgUserMessage -UserId "me" -All `
    -Filter "importance eq 'high' and receivedDateTime ge $since" `
    -Property $props |
    ForEach-Object { Format-Message $_ }

# Unread, sent directly To you (not CC), recent
$direct = Get-MgUserMessage -UserId "me" -All `
    -Filter "isRead eq false and receivedDateTime ge $since" `
    -Property $props |
    Where-Object {
        # Keep only if you're in the To line (not just CC'd)
        $myEmail = $ctx.Account
        $_.to -contains $myEmail
    } |
    ForEach-Object { Format-Message $_ }

[ordered]@{
    fetched_at  = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    days_window = $Days
    flagged     = $flagged
    high_priority = $highPri
    direct_unread = $direct
} | ConvertTo-Json -Depth 5
