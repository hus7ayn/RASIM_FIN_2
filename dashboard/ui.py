"""Shared UI chrome for the dashboard pages."""

from __future__ import annotations

import streamlit as st

DEMO_CAPTION = "Illustrative figures for interface demonstration — not real trading results."

_BADGE_CSS = """
<style>
.rasim-demo-badge{
  display:inline-flex; align-items:center; gap:.5rem;
  font-size:.74rem; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
  color:#8a5a12; background:rgba(214,163,90,.14);
  border:1px solid rgba(214,163,90,.55); border-radius:999px;
  padding:.28rem .7rem; margin:0 0 .35rem;
}
.rasim-demo-badge .dot{
  width:.42rem; height:.42rem; border-radius:50%; background:#d6a35a; flex:none;
}
@media (prefers-color-scheme: dark){
  .rasim-demo-badge{ color:#d6a35a; background:rgba(214,163,90,.10); }
}
.rasim-demo-note{
  font-size:.8rem; color:rgba(140,148,160,.95); margin:0 0 .9rem;
}
</style>
"""


def demo_badge(note: str = DEMO_CAPTION) -> None:
    """Render a compact 'demo data' badge.

    Deliberately understated rather than an error banner — a red alert box reads as a
    malfunction and got in the way of demoing the UI. It still has to be present and
    legible on every page that shows invented numbers, so the disclosure survives; only
    its styling is toned down.
    """
    st.markdown(_BADGE_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="rasim-demo-badge"><span class="dot"></span>Demo data</div>'
        f'<div class="rasim-demo-note">{note}</div>',
        unsafe_allow_html=True,
    )
