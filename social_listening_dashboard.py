# Shadee.Care – Social Listening Dashboard (v9j)
# ---------------------------------------------------------------
# • Sidebar controls + ALL‑sheet merge remain.
# • Fixes KeyError when a column is missing (e.g. no **Subreddit** column).
# • Guards all visualisations against empty data after filtering.
# ---------------------------------------------------------------

import re
import datetime as dt
from typing import Dict, List
from pathlib import Path

import pandas as pd
import streamlit as st
import praw

# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────
DATE_RE = re.compile(r"(\d{1,2}:\d{2})\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")
MON = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    1,
)}

def parse_post_date(txt: str):
    """Convert strings like 'Posted 05:44 13 Apr 2025' ➜ Datetime (UTC‑naive) or pd.NaT."""
    if not isinstance(txt, str):
        return pd.NaT
    m = DATE_RE.search(txt)
    if not m:
        return pd.NaT
    time_s, day, mon_s, year = m.groups()
    hh, mm = map(int, time_s.split(":"))
    try:
        return dt.datetime(int(year), MON[mon_s], int(day), hh, mm)
    except Exception:
        return pd.NaT

# ──────────────────────────────────────────────────────────────
#  Page setup & Reddit client (for future live mode)
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Shadee Live Listening", layout="wide")

if "reddit_api" not in st.session_state:
    if "reddit" in st.secrets:
        creds = st.secrets["reddit"]
        st.session_state.reddit_api = praw.Reddit(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
            user_agent=creds["user_agent"],
            check_for_async=False,
        )
        st.write("🔍 Loaded client_id:", creds["client_id"])
        st.write("🔍 Loaded user_agent:", creds["user_agent"])
    st.warning("⚠️ Using anonymous (script) scope – Reddit identity not fetched")

# ──────────────────────────────────────────────────────────────
#  Buckets (regex)
# ──────────────────────────────────────────────────────────────
BUCKET_PATTERNS: Dict[str, str] = {
    "self_blame": r"\b(hate(?:s|d)? (?:myself|me)|everyone hate(?:s|d)? me|worthless|i (?:don'?t|do not) deserve to live|i'?m a failure)\b",
    "cost_concern": r"\b(can'?t afford|too expensive|cost of therapy|insurance won'?t)\b",
    "work_burnout": r"\b(burnt out|burned out|toxic work|overworked|study burnout)\b",
    "self_harm": r"\b(kill myself|end my life|suicid(?:e|al)|self[- ]?harm)\b",
    "relationship_breakup": r"\b(break[- ]?up|dump(?:ed)?|heart ?broken|lost my (?:partner|girlfriend|boyfriend))\b",
    "friendship_drama": r"\b(friend(?:ship)? (?:ignore(?:d)?|ghost(?:ed)?|lost)|no friends?)\b",
    "crying_distress": r"\b(can'?t stop crying|keep on crying)\b",
}
COMPILED: Dict[str, re.Pattern] = {n: re.compile(p, re.I) for n, p in BUCKET_PATTERNS.items()}

# ──────────────────────────────────────────────────────────────
#  Sidebar controls
# ──────────────────────────────────────────────────────────────
st.sidebar.title("📊 Choose Data Source")
mode = st.sidebar.radio("Select mode", ("Upload Excel", "Live Reddit Pull"), index=0)

xl_file = st.sidebar.file_uploader("Drag & drop Excel", type="xlsx")
sheet_name = None
if xl_file:
    with pd.ExcelFile(xl_file) as xls:
        sheets = xls.sheet_names
    sheet_name = st.sidebar.selectbox("Sheet", ["ALL"] + sheets, index=0)

# date‑range (last 30 days by default)
end_d = dt.date.today()
start_d = end_d - dt.timedelta(days=30)
sel_range = st.sidebar.date_input("Select Date Range", (start_d, end_d))
if isinstance(sel_range, tuple):
    start_d, end_d = sel_range

# ──────────────────────────────────────────────────────────────
#  Excel‑processing path
# ──────────────────────────────────────────────────────────────
if mode == "Upload Excel" and xl_file:
    dfs: List[pd.DataFrame] = []
    xl = pd.ExcelFile(xl_file)
    targets = xl.sheet_names if sheet_name == "ALL" else [sheet_name]
    for s in targets:
        df_s = xl.parse(s, skiprows=2)  # first two rows are header meta
        if "Post Date" not in df_s.columns or "Post Content" not in df_s.columns:
            st.error(f"❌ Required columns missing in sheet ‘{s}’. Skipped.")
            continue
        df_s["Post_dt"] = df_s["Post Date"].map(parse_post_date)
        df_s["Platform"] = df_s["Platform"].str.lower().fillna("unknown")
        dfs.append(df_s)
    if not dfs:
        st.stop()
    df = pd.concat(dfs, ignore_index=True)

    # date filter
    mask = (df["Post_dt"].dt.date >= start_d) & (df["Post_dt"].dt.date <= end_d)
    df = df.loc[mask].copy()

    # bucket tagging
    def tag_bucket(text: str):
        if not isinstance(text, str):
            return "other"
        for n, cre in COMPILED.items():
            if cre.search(text):
                return n
        return "other"

    df["Bucket"] = df["Post Content"].apply(tag_bucket)

    # after buckets → filter list
    sel_buckets = st.sidebar.multiselect(
        "Select buckets", sorted(df["Bucket"].unique()), default=list(sorted(df["Bucket"].unique()))
    )
    df = df[df["Bucket"].isin(sel_buckets)]

    st.success(f"✅ {len(df)} posts after filtering")

    if df.empty:
        st.warning("No rows match the current filters.")
        st.stop()

    # ── charts ───────────────────────────────
    st.subheader("📊 Post volume by bucket")
    st.bar_chart(df["Bucket"].value_counts())

    st.subheader("📈 Post trend over time")
    trend = (
        df.set_index("Post_dt").resample("1D").size().loc[start_d:end_d]
    )
    st.line_chart(trend)

    st.subheader("🧠 Top subreddits")
    if "Subreddit" in df.columns:
        top_sub = df["Subreddit"].fillna("Unknown").value_counts().head(10)
        st.bar_chart(top_sub)
    else:
        st.info("Subreddit column not present in this dataset.")

    st.subheader("📄 Content sample")
    subset_cols = [c for c in ["Post_dt", "Bucket", "Subreddit", "Post Content"] if c in df.columns]
    st.dataframe(df[subset_cols].head(50), height=300)

elif mode == "Live Reddit Pull":
    st.info("🔧 Live mode not yet wired – stay tuned!")
else:
    st.warning("⬅️ Upload an Excel file on the left to begin")
