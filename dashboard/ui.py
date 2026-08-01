"""Shared UI chrome for the dashboard pages."""

from __future__ import annotations

import os

import streamlit as st

DEMO_CAPTION = "Illustrative figures for interface demonstration — not real trading results."

# Set HIDE_DEMO_BADGE=1 to suppress the on-screen demo badge.
#
# It exists as a local switch rather than a code deletion because the same codebase is
# deployed to Streamlit Community Cloud, where apps are reachable by URL to anyone who
# has it. The badge is redundant for the author, who knows the figures are invented, but
# it is the only thing distinguishing them from real results for anyone else who opens
# the app. Setting this in a local shell keeps the local view clean while a deployment
# that does not set it still discloses.
#
# File exports are labelled regardless of this flag: a CSV or PDF can be forwarded long
# after the context is lost, and hiding an on-screen badge costs nothing there.
HIDE_ENV_VAR = "HIDE_DEMO_BADGE"

_BADGE_CSS = """
<style>
.demo-badge{
  display:inline-flex; align-items:center; gap:.5rem;
  font-size:.74rem; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
  color:#8a5a12; background:rgba(214,163,90,.14);
  border:1px solid rgba(214,163,90,.55); border-radius:999px;
  padding:.28rem .7rem; margin:0 0 .35rem;
}
.demo-badge .dot{
  width:.42rem; height:.42rem; border-radius:50%; background:#d6a35a; flex:none;
}
@media (prefers-color-scheme: dark){
  .demo-badge{ color:#d6a35a; background:rgba(214,163,90,.10); }
}
.demo-note{
  font-size:.8rem; color:rgba(140,148,160,.95); margin:0 0 .9rem;
}
</style>
"""


def badge_hidden() -> bool:
    return os.getenv(HIDE_ENV_VAR, "").strip().lower() in ("1", "true", "yes", "on")


def demo_badge(note: str = DEMO_CAPTION) -> None:
    """Render a compact 'demo data' badge, unless suppressed locally.

    Deliberately understated rather than an error banner — a red alert box reads as a
    malfunction. See HIDE_ENV_VAR above for why suppression is an environment switch
    instead of removing the call sites.
    """
    if badge_hidden():
        return
    st.markdown(_BADGE_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="demo-badge"><span class="dot"></span>Demo data</div>'
        f'<div class="demo-note">{note}</div>',
        unsafe_allow_html=True,
    )
