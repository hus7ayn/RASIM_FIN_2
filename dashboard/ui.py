"""Shared UI chrome for the dashboard pages."""

from __future__ import annotations

import os

import streamlit as st

DEMO_CAPTION = "This dashboard is a demonstration of the capabilities of the underlying data and models on the backtest"

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
.demo-note{
  font-size:.78rem; color:rgba(140,148,160,.92);
  margin:0 0 .9rem; font-style:italic;
}
</style>
"""


def badge_hidden() -> bool:
    return os.getenv(HIDE_ENV_VAR, "").strip().lower() in ("1", "true", "yes", "on")


def demo_badge(note: str = DEMO_CAPTION) -> None:
    """Render the demo-data note, unless suppressed locally.

    The uppercase "Demo data" pill that used to sit above this was dropped: it only
    repeated, in louder form, what the sentence already says, and read as chrome. The
    sentence itself stays — it is the part that actually tells a reader the figures are
    not measured results.
    """
    if badge_hidden():
        return
    st.markdown(_BADGE_CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="demo-note">{note}</div>', unsafe_allow_html=True)
