# connect.ps1 — run once to authenticate with Microsoft Graph
# After this, all other scripts reuse the cached token automatically.
#
# Usage:
#   pwsh scripts/ps/connect.ps1

param(
    [switch]$Force   # re-authenticate even if already connected
)

$RequiredScopes = @(
    "User.Read",
    "User.ReadBasic.All",
    "Calendars.Read",
    "Mail.Read",
    "People.Read",
    "Team.ReadBasic.All",
    "ChannelMessage.Read.All",
    "Chat.Read"
)

# Install module if missing
if (-not (Get-Module -ListAvailable -Name Microsoft.Graph)) {
    Write-Host "Installing Microsoft.Graph module (this takes a few minutes on first run)..."
    Install-Module Microsoft.Graph -Scope CurrentUser -Repository PSGallery -Force
}

Import-Module Microsoft.Graph.Authentication -ErrorAction Stop

# Check if already connected with the right scopes
$ctx = Get-MgContext
if ($ctx -and -not $Force) {
    $missing = $RequiredScopes | Where-Object { $_ -notin $ctx.Scopes }
    if (-not $missing) {
        Write-Host "Already connected as $($ctx.Account) with all required scopes."
        exit 0
    }
    Write-Host "Connected but missing scopes: $($missing -join ', '). Re-authenticating..."
}

Connect-MgGraph -Scopes $RequiredScopes -NoWelcome
$ctx = Get-MgContext
Write-Host "Connected as: $($ctx.Account)"
Write-Host "Scopes granted: $($ctx.Scopes -join ', ')"
