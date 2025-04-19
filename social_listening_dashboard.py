# Shadee.Care – Social Listening Dashboard (v9i)
# ---------------------------------------------------------------
# • Restores **sidebar controls** (mode, file‑upload, sheet picker, bucket
#   filter, and date‑range selector).
# • Keeps ALL‑sheets merge and YouTube handling from v9h.
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
    """Convert strings like 'Posted 05:44 13 Apr 2025' ➜ datetime or pd.NaT."""
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
#  Page setup & Reddit client (for live mode – still optional)
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Shadee Live Listening", layout="wide")

if "reddit_api" not in st.session_state:
    if "reddit" in st.secrets:
        rc = st.secrets["reddit"]
        st.session_state.reddit_api = praw.Reddit(
            client_id=rc["client_id"],
            client_secret=rc["client_secret"],
            user_agent=rc["user_agent"],
            check_for_async=False,
        )
        st.write("🔍 Loaded client_id:", rc["client_id"])
        st.write("🔍 Loaded user_agent:", rc["user_agent"])
    st.warning("⚠️ Using anonymous (script) scope – Reddit identity not fetched")

# ──────────────────────────────────────────────────────────────
#  Buckets (regex) – same as v9h
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
COMPILED = {name: re.compile(pat, re.I) for name, pat in BUCKET_PATTERNS.items()}


# ──────────────────────────────────────────────────────────────
#  Sidebar – mode & file controls
# ──────────────────────────────────────────────────────────────
st.sidebar.title("📊 Choose Data Source")
mode = st.sidebar.radio("Select mode", ("Upload Excel", "Live Reddit Pull"), index=0)

# Excel‑upload widgets
xl_file = st.sidebar.file_uploader("Drag and drop Excel", type="xlsx")

sheet_name = None
if xl_file:
    with pd.ExcelFile(xl_file) as xls:
        sheets = xls.sheet_names
    sheets_display: List[str] = ["ALL"] + sheets
    sheet_name = st.sidebar.selectbox("Sheet", sheets_display, index=0)

# Date‑range selector (defaults last 30 days)
end_d = dt.date.today()
start_d = end_d - dt.timedelta(days=30)
sel_range = st.sidebar.date_input("Select Date Range", (start_d, end_d))
if isinstance(sel_range, tuple):
    start_d, end_d = sel_range

# ──────────────────────────────────────────────────────────────
#  Main logic – Upload Excel mode
# ──────────────────────────────────────────────────────────────
if mode == "Upload Excel" and xl_file:
    # Concatenate all sheets or single one
    dfs = []
    with st.spinner("Reading Excel…"):
        xl = pd.ExcelFile(xl_file)
        names = xl.sheet_names if sheet_name == "ALL" else [sheet_name]
        for s in names:
            df_s = xl.parse(s, skiprows=2)  # data start on row 3
            df_s["Post_dt"] = df_s["Post Date"].map(parse_post_date)
            df_s["Platform"] = df_s["Platform"].str.lower().fillna("unknown")
            dfs.append(df_s)
    df = pd.concat(dfs, ignore_index=True)

    # Filter by date
    mask = (df["Post_dt"].dt.date >= start_d) & (df["Post_dt"].dt.date <= end_d)
    df = df.loc[mask].copy()

    # Tag buckets
    def tag_bucket(text: str):
        if not isinstance(text, str):
            return "other"
        for name, cre in COMPILED.items():
            if cre.search(text):
                return name
        return "other"

    df["Bucket"] = df["Post Content"].apply(tag_bucket)

    # Sidebar bucket multiselect (after we know unique set)
    sel_buckets = st.sidebar.multiselect(
        "Select buckets", df["Bucket"].unique().tolist(), default=df["Bucket"].unique().tolist()
    )
    df = df[df["Bucket"].isin(sel_buckets)]

    st.success(f"✅ {len(df)} posts after filtering")

    # ── Charts ─────────────────────────────────
    st.subheader("📊 Post volume by bucket")
    st.bar_chart(df["Bucket"].value_counts())

    st.subheader("📈 Post trend over time")
    trend = (
        df.set_index("Post_dt")
        .resample("1D")
        .size()
        .loc[start_d:end_d]
    )
    st.line_chart(trend)

    st.subheader("🧠 Top subreddits")
    if "Subreddit" in df.columns:
        tops = df["Subreddit"].fillna("Unknown").value_counts().head(10)
        st.bar_chart(tops)

    st.subheader("📄 Content sample")
    st.dataframe(df[["Post_dt", "Bucket", "Subreddit", "Post Content"]].head(50), height=300)

elif mode == "Live Reddit Pull":
    st.info("🔧 Live mode not yet wired – stay tuned!")
else:
    st.warning("⬅️ Upload an Excel file on the left to begin")
