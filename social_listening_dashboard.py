# Shadee.Care – Social Listening Dashboard (v9f)
# -------------------------------------------------------------
# • Simplified: date‑range picker removed (full data shown)
# • Fixed indentation / duplicate lines causing runtime error
# -------------------------------------------------------------

import re
import datetime as dt
from typing import Dict

import pandas as pd
import streamlit as st
import praw

# ──────────────────────────────────────────────────────────────
#  Page setup & Reddit client
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Shadee Live Listening", layout="wide")

if "reddit_api" not in st.session_state:
    rcreds = st.secrets["reddit"]
    st.session_state.reddit_api = praw.Reddit(
        client_id=rcreds["client_id"],
        client_secret=rcreds["client_secret"],
        user_agent=rcreds["user_agent"],
        check_for_async=False,
    )
    st.write("🔍 Loaded client_id:", rcreds["client_id"])
    st.write("🔍 Loaded user_agent:", rcreds["user_agent"])
    st.warning("⚠️ Reddit identity check skipped – assumed anonymous access")

# ──────────────────────────────────────────────────────────────
#  Bucket regexes
# ──────────────────────────────────────────────────────────────
BUCKET_PATTERNS: Dict[str, str] = {
    "self_blame": r"\b(hate(?:s|d)? (?:myself|me|everybody|people)|everyone hate(?:s|d)? (?:me|people)|worthless|i (?:don'?t|do not) deserve to live|i'?m a failure|no one cares|what'?s wrong with me|deserve(?:s)? to suffer)\b",
    "cost_concern": r"\b(can'?t afford|too expensive|cost of therapy|insurance won'?t|money for help|cheap therapy|on a budget)\b",
    "work_burnout": r"\b(burnt out|burned out|exhausted by work|quit(?:ting)? my job|toxic work(?:place)?|overworked|deadlines|study burnout)\b",
    "self_harm": r"\b(kill myself|end my life|suicid(?:e|al)|self[- ]?harm|jump off|take my life|die by suicide)\b",
    "relationship_breakup": r"\b(break[- ]?up|dump(?:ed|ing)?|heart ?broken|ex[- ]?(?:bf|gf)|my ex\b|lost my (partner|girlfriend|boyfriend))\b",
    "friendship_drama": r"\b(friend(?:ship)? (?:ignore(?:d)?|ghost(?:ed|ing)?|betray(?:ed)?|leave|leaving|lost)|lost my friends?|no friends?|cut off friends?|my (?:best )?friend(?:s)? (?:hate|left|stopped talking))\b",
}
COMPILED = {b: re.compile(p, re.I) for b, p in BUCKET_PATTERNS.items()}

@st.cache_data(show_spinner=False)
def tag_bucket(txt: str) -> str:
    low = txt.lower()
    for b, pat in COMPILED.items():
        if pat.search(low):
            return b
    return "other"

# ──────────────────────────────────────────────────────────────
#  Sidebar – data source (no date range)
# ──────────────────────────────────────────────────────────────
st.title("🔴 Shadee.Care – Reddit Live + Excel Social Listening Dashboard")

st.sidebar.header("Choose Data Source")
source_mode = st.sidebar.radio("Select mode", ["🔴 Live Reddit Pull", "📁 Upload Excel"])

df = None  # will hold dataframe after load

# ──────────────────────────────────────────────────────────────
#  Load data (df)
# ──────────────────────────────────────────────────────────────
if source_mode.startswith("🔴"):
    query = st.sidebar.text_input("Search phrase", "lonely OR therapy")
    subr = st.sidebar.text_input("Subreddit", "depression")
    limit = st.sidebar.slider("Max posts", 10, 200, 50)
    if st.sidebar.button("🔍 Fetch live posts"):
        terms = [t.strip().lower() for t in re.split(r"\bOR\b", query, flags=re.I)]
        subs = subr.split("+") if "+" in subr else [subr]
        rows = []
        with st.spinner("Contacting Reddit…"):
            for sr in subs:
                for p in st.session_state.reddit_api.subreddit(sr).new(limit=limit):
                    body = f"{p.title}\n{p.selftext}".lower()
                    if any(t in body for t in terms):
                        rows.append({
                            "Platform": "Reddit",
                            "Post_dt": dt.datetime.utcfromtimestamp(p.created_utc),
                            "Post Content": p.title + "\n" + p.selftext,
                            "Subreddit": p.subreddit.display_name,
                            "Post URL": f"https://www.reddit.com{p.permalink}",
                        })
        if rows:
            df = pd.DataFrame(rows)
else:
    up = st.sidebar.file_uploader("Drag & drop Excel", type="xlsx")
    if up:
        sheet = st.sidebar.selectbox("Sheet", pd.ExcelFile(up).sheet_names)
        df = pd.read_excel(up, sheet_name=sheet, header=2)
        if "Post Content" not in df.columns and len(df.columns) >= 5:
            df.rename(columns={df.columns[4]: "Post Content"}, inplace=True)
        if "Subreddit" not in df.columns:
            df["Subreddit"] = "Unknown"
        if "Post_dt" not in df.columns:
            df["Post_dt"] = pd.Timestamp.now()

# ──────────────────────────────────────────────────────────────
#  Enrich, bucket‑tag and visualise
# ──────────────────────────────────────────────────────────────
if df is not None and not df.empty:
    df["Post_dt"] = pd.to_datetime(df["Post_dt"], errors="coerce")
    df["Post_date"] = df["Post_dt"].dt.floor("D")

    if "Bucket" not in df.columns:
        df["Bucket"] = df["Post Content"].fillna("*").apply(tag_bucket)

    # bucket selector (no date filter)
    sel_buckets = st.sidebar.multiselect(
        "Select buckets",
        options=df["Bucket"].unique().tolist(),
        default=df["Bucket"].unique().tolist(),
    )
    df = df[df["Bucket"].isin(sel_buckets)]

    st.success(f"✅ {len(df)} posts after filtering")

    # ── Charts ──
    st.subheader("📊 Post volume by bucket")
    st.bar_chart(df["Bucket"].value_counts())

    st.subheader("📈 Post trend over time")
    daily = df.groupby("Post_date").size().rename("Posts").to_frame()
    st.line_chart(daily)

    if "Subreddit" in df.columns:
        st.subheader("🧠 Top subreddits")
        st.bar_chart(df["Subreddit"].value_counts().head(10))

    st.subheader("📄 Content sample")
    st.dataframe(
        df[[c for c in ["Post_dt", "Bucket", "Subreddit", "Post Content"] if c in df.columns]].head(30),
        height=260,
    )

st.caption("© 2025 Shadee.Care • Live Reddit & Excel dashboard (v9f)")
