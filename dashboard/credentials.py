"""Binance **testnet** API credentials supplied through the dashboard.

Handling rules, and why:

- Credentials live in Streamlit's per-session state and nowhere else. They are never
  written to the trade log, never written to any file, and never logged. Session state is
  server-side memory scoped to one browser session and is discarded when it ends.
- Inputs are rendered with `type="password"` so the secret is not shoulder-readable and
  does not land in the browser's visible DOM as plain text.
- These must be **testnet** keys. `binance_testnet.build_testnet_exchange` points every
  endpoint at `demo-fapi.binance.com`, so a mainnet key cannot trade through this app —
  but it would still have been transmitted to whatever host is serving the dashboard.
  That is the actual hazard, and it is why the UI says testnet-only rather than assuming.
- On a hosted deployment (Streamlit Community Cloud and similar), anything typed into the
  app travels to that host. For a deployment you control, `st.secrets` is the right place
  for credentials; the manual entry path exists for local use.

`resolve()` prefers session-entered keys, then `st.secrets`, then environment variables,
so a local shell export or a configured secret keeps working untouched.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import streamlit as st

SESSION_KEY = "_binance_api_key"
SESSION_SECRET = "_binance_api_secret"

ENV_KEY = "BINANCE_TESTNET_API_KEY"
ENV_SECRET = "BINANCE_TESTNET_API_SECRET"


def _from_secrets() -> Tuple[str, str]:
    try:
        return (
            str(st.secrets.get(ENV_KEY, "")).strip(),
            str(st.secrets.get(ENV_SECRET, "")).strip(),
        )
    except Exception:  # noqa: BLE001 - no secrets.toml configured is normal
        return "", ""


def resolve() -> Tuple[str, str]:
    """Return (api_key, api_secret) from session, then secrets, then environment."""
    key = str(st.session_state.get(SESSION_KEY, "")).strip()
    secret = str(st.session_state.get(SESSION_SECRET, "")).strip()
    if key and secret:
        return key, secret

    key, secret = _from_secrets()
    if key and secret:
        return key, secret

    return os.getenv(ENV_KEY, "").strip(), os.getenv(ENV_SECRET, "").strip()


def source() -> Optional[str]:
    """Where the active credentials came from, for display. None if there are none."""
    if str(st.session_state.get(SESSION_KEY, "")).strip() and str(
        st.session_state.get(SESSION_SECRET, "")
    ).strip():
        return "entered this session"
    k, s = _from_secrets()
    if k and s:
        return "st.secrets"
    if os.getenv(ENV_KEY, "").strip() and os.getenv(ENV_SECRET, "").strip():
        return "environment variables"
    return None


def present() -> bool:
    key, secret = resolve()
    return bool(key and secret)


def store(api_key: str, api_secret: str) -> None:
    st.session_state[SESSION_KEY] = api_key.strip()
    st.session_state[SESSION_SECRET] = api_secret.strip()


def clear() -> None:
    st.session_state.pop(SESSION_KEY, None)
    st.session_state.pop(SESSION_SECRET, None)


def masked(api_key: str) -> str:
    """Show enough of a key to identify it, never enough to use it."""
    key = api_key.strip()
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}{'•' * 8}{key[-4:]}"
