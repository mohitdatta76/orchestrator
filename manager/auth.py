"""
Microsoft Graph API authentication via MSAL device code flow.

Tokens are cached to disk so authentication persists across sessions
and cron jobs. Refresh tokens last ~90 days — you'll re-auth a few
times a year.

Usage:
  from manager.auth import get_access_token
  token = get_access_token()   # prompts once, silent afterwards

Direct auth check:
  python manager/auth.py        # force a fresh login / check status
"""

import json
import os
import sys
from pathlib import Path

try:
    import msal
    _MSAL_AVAILABLE = True
except ImportError:
    _MSAL_AVAILABLE = False

# Scopes requested — all delegated (as the signed-in user)
SCOPES = [
    "Mail.Read",
    "Calendars.Read",
    "Chat.Read",
    "User.Read",
    "OnlineMeetings.Read",
]

_TOKEN_CACHE_PATH = Path(__file__).parent.parent / ".token_cache.json"


def _load_cache() -> "msal.SerializableTokenCache":
    cache = msal.SerializableTokenCache()
    if _TOKEN_CACHE_PATH.exists():
        cache.deserialize(_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    return cache


def _save_cache(cache: "msal.SerializableTokenCache") -> None:
    if cache.has_state_changed:
        _TOKEN_CACHE_PATH.write_text(cache.serialize(), encoding="utf-8")
        # Restrict file permissions — token cache is sensitive
        _TOKEN_CACHE_PATH.chmod(0o600)


def _build_app(client_id: str, tenant_id: str) -> tuple["msal.PublicClientApplication", "msal.SerializableTokenCache"]:
    cache = _load_cache()
    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )
    return app, cache


def get_access_token(force_refresh: bool = False) -> str | None:
    """
    Return a valid access token for Microsoft Graph.

    Priority:
      1. GRAPH_ACCESS_TOKEN env var (manual override, e.g. from Graph Explorer)
      2. Cached MSAL token (silent refresh if expired)
      3. Device code flow (interactive, opens browser)

    Returns None if auth is not configured (runs in mock mode).
    """
    # Manual override takes priority
    manual_token = os.getenv("GRAPH_ACCESS_TOKEN", "").strip()
    if manual_token and not force_refresh:
        return manual_token

    client_id = os.getenv("GRAPH_CLIENT_ID", "").strip()
    tenant_id = os.getenv("GRAPH_TENANT_ID", "").strip()

    if not client_id or not tenant_id:
        return None  # No auth configured — caller uses mock mode

    if not _MSAL_AVAILABLE:
        print("[auth] msal not installed. Run: pip install msal")
        return None

    app, cache = _build_app(client_id, tenant_id)

    # Try silent token acquisition from cache first
    accounts = app.get_accounts()
    if accounts and not force_refresh:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            return result["access_token"]

    # Cache miss or expired — do device code flow
    return _device_code_flow(app, cache)


def _device_code_flow(app: "msal.PublicClientApplication", cache: "msal.SerializableTokenCache") -> str | None:
    """Prompt the user to authenticate via device code."""
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        print(f"[auth] Failed to create device flow: {flow.get('error_description', flow)}")
        return None

    # Print the prompt clearly
    print("\n" + "="*55)
    print("Microsoft authentication required")
    print("="*55)
    print(f"\n  1. Open:  https://microsoft.com/devicelogin")
    print(f"  2. Enter: {flow['user_code']}")
    print(f"\n  Waiting for you to sign in...\n")

    result = app.acquire_token_by_device_flow(flow)  # blocks until done

    if "access_token" in result:
        _save_cache(cache)
        account = result.get("id_token_claims", {}).get("preferred_username", "unknown")
        print(f"  Signed in as: {account}")
        print(f"  Token cached to: {_TOKEN_CACHE_PATH}")
        print("="*55 + "\n")
        return result["access_token"]
    else:
        error = result.get("error_description") or result.get("error", "unknown error")
        print(f"[auth] Authentication failed: {error}")
        return None


def check_status() -> None:
    """Print current auth status. Used when running this file directly."""
    manual = os.getenv("GRAPH_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("GRAPH_CLIENT_ID", "").strip()
    tenant_id = os.getenv("GRAPH_TENANT_ID", "").strip()

    print("\nAuth status:")

    if manual:
        print("  Mode:  Manual token (GRAPH_ACCESS_TOKEN is set)")
        print("  Note:  This token expires in ~1 hour. For persistent auth,")
        print("         use GRAPH_CLIENT_ID + GRAPH_TENANT_ID instead.")
        return

    if not client_id or not tenant_id:
        print("  Mode:  Mock data (no credentials configured)")
        print("  To enable real data:")
        print("    1. Create an App Registration in portal.azure.com")
        print("    2. Set GRAPH_CLIENT_ID and GRAPH_TENANT_ID in .env")
        return

    print(f"  Mode:  MSAL ({client_id[:8]}...)")
    print(f"  Tenant: {tenant_id}")

    if not _MSAL_AVAILABLE:
        print("  msal:  NOT INSTALLED — run: pip install msal")
        return

    if _TOKEN_CACHE_PATH.exists():
        cache = _load_cache()
        app, _ = _build_app(client_id, tenant_id)
        accounts = app.get_accounts()
        if accounts:
            username = accounts[0].get("username", "unknown")
            print(f"  Cache: Valid ({username})")
            # Try silent to confirm token is refreshable
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                print("  Token: OK (silent refresh succeeded)")
            else:
                print("  Token: Needs re-auth (run: python manager/auth.py --login)")
        else:
            print("  Cache: Present but no accounts found — run: python manager/auth.py --login")
    else:
        print("  Cache: None — run: python manager/auth.py --login")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Manage Microsoft Graph authentication")
    p.add_argument("--login", action="store_true", help="Force a new login")
    p.add_argument("--logout", action="store_true", help="Clear the token cache")
    p.add_argument("--status", action="store_true", help="Show auth status (default)")
    args = p.parse_args()

    if args.logout:
        if _TOKEN_CACHE_PATH.exists():
            _TOKEN_CACHE_PATH.unlink()
            print("Token cache cleared.")
        else:
            print("No token cache found.")
    elif args.login:
        token = get_access_token(force_refresh=True)
        if token:
            print("\nAuthentication successful.")
        else:
            sys.exit(1)
    else:
        check_status()
