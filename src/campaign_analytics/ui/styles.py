"""Global visual language applied once by the application shell."""

import streamlit as st


def inject_global_styles() -> None:
    """Apply product-level styling beyond Streamlit's base theme tokens."""
    st.markdown(
        """
        <style>
        .block-container { max-width: 1480px; padding: 2.25rem 2.5rem 3.5rem; }
        [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #EAECF0; }
        [data-testid="stSidebar"] > div:first-child { padding: 1.45rem .9rem; }
        [data-testid="stSidebar"] .stRadio label { border-radius: 9px; padding: .25rem .4rem; }
        [data-testid="stSidebar"] .stRadio label:hover { background: #F2F4F7; }
        .brand-mark { align-items: center; background: #0B6E69; border-radius: 10px; color: #FFFFFF;
          display: inline-flex; font-size: 1.2rem; font-weight: 800; height: 32px; justify-content: center;
          margin-bottom: .55rem; width: 32px; }
        .brand-name { color: #101828; font-size: 1.02rem; font-weight: 750; letter-spacing: -.02em; }
        .sidebar-footer { bottom: 1.2rem; color: #98A2B3; font-size: .74rem; position: fixed; }
        .platform-eyebrow { color: #0B6E69; font-size: .75rem; font-weight: 750;
          letter-spacing: .09em; text-transform: uppercase; margin-bottom: .35rem; }
        .platform-title { color: #101828; font-size: clamp(2rem, 4vw, 2.65rem); font-weight: 760;
          letter-spacing: -.045em; line-height: 1.08; margin: 0; }
        .platform-subtitle { color: #667085; font-size: 1rem; line-height: 1.55; margin-top: .6rem; max-width: 760px; }
        .section-heading { color: #101828; font-size: 1.08rem; font-weight: 700; letter-spacing: -.015em;
          margin: 1.8rem 0 .25rem; }
        .kpi-card { background: linear-gradient(145deg, #FFFFFF, #FCFDFD); border: 1px solid #EAECF0;
          border-radius: 16px; box-shadow: 0 2px 7px rgba(16, 24, 40, .04); min-height: 126px; padding: 1.2rem 1.25rem; }
        .kpi-card:hover { border-color: #D0D5DD; box-shadow: 0 8px 20px rgba(16, 24, 40, .07); }
        .kpi-label { color: #667085; font-size: .8rem; font-weight: 650; }
        .kpi-value { color: #101828; font-size: 1.82rem; font-weight: 750; letter-spacing: -.04em; margin-top: .36rem; }
        .kpi-detail { color: #0B6E69; font-size: .78rem; font-weight: 600; margin-top: .42rem; }
        .section-card { background: #FFFFFF; border: 1px solid #EAECF0; border-radius: 16px;
          box-shadow: 0 2px 7px rgba(16, 24, 40, .035); padding: 1.35rem; margin: .8rem 0 1rem; }
        .hero-panel { background: radial-gradient(circle at top right, #D8F0EA, transparent 36%), #103B3A;
          border-radius: 22px; color: #FFFFFF; margin: 1.4rem 0 1.5rem; padding: 2rem; }
        .hero-panel h2 { font-size: 1.65rem; letter-spacing: -.035em; margin: 0 0 .55rem; }
        .hero-panel p { color: #D7ECE9; margin: 0; max-width: 660px; }
        .module-card { background: #FFFFFF; border: 1px solid #EAECF0; border-radius: 14px; min-height: 130px;
          padding: 1rem; }
        .module-card-title { color: #101828; font-size: .92rem; font-weight: 700; margin: .4rem 0 .25rem; }
        .module-card-detail { color: #667085; font-size: .78rem; }
        .empty-state { align-items: center; background: #FFFFFF; border: 1px dashed #D0D5DD; border-radius: 14px;
          color: #667085; display: flex; gap: 1rem; padding: 1.35rem; }
        .empty-icon { align-items: center; background: #F2F4F7; border-radius: 10px; color: #475467;
          display: flex; font-size: 1.35rem; height: 40px; justify-content: center; width: 40px; }
        .nav-section { color: #98A2B3; font-size: .68rem; font-weight: 750;
          letter-spacing: .09em; text-transform: uppercase; margin: 1.35rem 0 .45rem; }
        [data-testid="stExpander"] { border: 1px solid #EAECF0; border-radius: 12px; }
        [data-testid="stDataFrame"] { border: 1px solid #EAECF0; border-radius: 12px; overflow: hidden; }
        @media (max-width: 760px) {
          .block-container { padding: 1.35rem 1rem 2.25rem; }
          .hero-panel { padding: 1.45rem; }
          .sidebar-footer { position: static; margin-top: 2rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

