# get_teams_mentions.ps1 — fetch recent Teams chat messages where you are @mentioned.
# Checks all your active chats for the last N days.
# Outputs JSON to stdout.
#
# Usage:
#   pwsh scripts/ps/get_teams_mentions.ps1 [-Days 3]
#
# Note: ChannelMessage.Read.All scope is required and may need admin consent
# in some tenants. If this fails, chat-based mentions still work with Chat.Read.

param(
    [int]$Days = 3
)

Import-Module Microsoft.Graph.Authentication, Microsoft.Graph.Teams -ErrorAction Stop

$ctx = Get-MgContext
if (-not $ctx) {
    Write-Error "Not authenticated. Run scripts/ps/connect.ps1 first."
    exit 1
}

$myId    = (Get-MgUser -UserId "me" -Property "id").Id
$cutoff  = (Get-Date).AddDays(-$Days)
$mentions = [System.Collections.Generic.List[object]]::new()

# --- Chat-based mentions (1:1 and group chats) ---
$chats = Get-MgUserChat -UserId "me" -All `
    -Filter "lastUpdatedDateTime ge $($cutoff.ToString('yyyy-MM-ddTHH:mm:ss'))Z" `
    -Property "id,chatType,topic,lastUpdatedDateTime" `
    -ErrorAction SilentlyContinue

foreach ($chat in $chats) {
    $msgs = Get-MgUserChatMessage -UserId "me" -ChatId $chat.Id -Top 50 `
        -Property "id,body,from,createdDateTime,mentions,messageType" `
        -ErrorAction SilentlyContinue

    foreach ($msg in $msgs) {
        if ($msg.MessageType -ne "message") { continue }
        $created = [datetime]$msg.CreatedDateTime
        if ($created -lt $cutoff) { continue }

        $mentionsMe = $msg.Mentions | Where-Object { $_.Mentioned.User.Id -eq $myId }
        if (-not $mentionsMe) { continue }

        $mentions.Add([ordered]@{
            source       = "chat"
            chat_type    = $chat.ChatType
            chat_topic   = $chat.Topic
            message_id   = $msg.Id
            from         = $msg.From.User.DisplayName
            created      = $msg.CreatedDateTime
            body_preview = ($msg.Body.Content -replace '<[^>]+>', '')[0..300] -join ''
        })
    }
}

[ordered]@{
    fetched_at  = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    days_window = $Days
    mention_count = $mentions.Count
    mentions    = $mentions
} | ConvertTo-Json -Depth 5
