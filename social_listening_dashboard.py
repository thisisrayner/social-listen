# Shadee.Care – Social Listening Dashboard (v9d – Reddit via praw + Excel upload)
# ------------------------------------------------------------------
# Stable Reddit pull (praw), Excel support restored, no psaw
# ------------------------------------------------------------------

import re
import datetime as dt
from typing import Dict

import pandas as pd
import streamlit as st
import praw
from pathlib import Path

# ---------- Streamlit page config must be first ---------- #
st.set_page_config(page_title="Shadee Live Listening", layout="wide")

# ---------- Reddit API init ---------- #
if "reddit_api" not in st.session_state:
    creds = st.secrets["reddit"]
    reddit = praw.Reddit(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        user_agent=creds["user_agent"],
        check_for_async=False
    )
    st.session_state.reddit_api = reddit
    st.write("🔍 Loaded client_id:", creds["client_id"])
    st.write("🔍 Loaded user_agent:", creds["user_agent"])
    st.warning("⚠️ Reddit identity check skipped – assumed anonymous access")

# ---------- Regex bucket patterns ---------- #
BUCKET_PATTERNS: Dict[str, str] = {
    "self_blame": r"\b(hate(?:s|d)? (?:myself|me|everybody|people)|everyone hate(?:s|d)? (?:me|people)|worthless|i (?:don'?t|do not) deserve to live|i'?m a failure|no one cares|what'?s wrong with me|deserve(?:s)? to suffer)\b",
    "cost_concern": r"\b(can'?t afford|too expensive|cost of therapy|insurance won'?t|money for help|cheap therapy|on a budget)\b",
    "work_burnout": r"\b(burnt out|burned out|exhausted by work|quit(?:ting)? my job|toxic work(?:place)?|overworked|deadlines|study burnout)\b",
    "self_harm": r"\b(kill myself|end my life|suicid(?:e|al)|self[- ]?harm|jump off|take my life|die by suicide)\b",
    "relationship_breakup": r"\b(break[- ]?up|dump(?:ed|ing)?|heart ?broken|ex[- ]?(?:bf|gf)|my ex\b|lost my (partner|girlfriend|boyfriend))\b",
    "friendship_drama": r"\b(friend(?:ship)? (?:ignore(?:d)?|ghost(?:ed|ing)?|betray(?:ed)?|leave|leaving|lost)|lost my friends?|no friends?|cut off friends?|my (?:best )?friend(?:s)? (?:hate|left|stopped talking))\b",
}

BUCKET_COLOURS = {
    "self_blame": "🟥", "cost_concern": "🟨", "work_burnout": "🟩", "self_harm": "🟪",
    "relationship_breakup": "🟦", "friendship_drama": "🟫", "other": "⬜️",
}
COMPILED = {b: re.compile(p, re.I) for b, p in BUCKET_PATTERNS.items()}

@st.cache_data(show_spinner=False)
def tag_bucket(text: str) -> str:
    t = text.lower()
    for b, pat in COMPILED.items():
        if pat.search(t):
            return b
    return "other"

# ---------- Streamlit UI ---------- #
st.title("🔴 Shadee.Care – Reddit Live + Excel Social Listening Dashboard")

st.sidebar.header("Choose Data Source")
source_mode = st.sidebar.radio("Select mode", ["🔴 Live Reddit Pull", "📁 Upload Excel"], horizontal=False)

df = None

if source_mode == "🔴 Live Reddit Pull":
    query = st.sidebar.text_input("Search phrase (keywords, OR-supported)", "lonely OR therapy")
    subr = st.sidebar.text_input("Subreddit (e.g. depression or all)", "depression")
    limit = st.sidebar.slider("Max posts to fetch", 10, 200, 50)
    do_fetch = st.sidebar.button("🔍 Fetch live posts")

    if do_fetch:
        reddit = st.session_state.reddit_api
        subreddits = subr.split("+") if "+" in subr else [subr.strip()]
        terms = [t.strip().lower() for t in re.split(r"\bOR\b", query, flags=re.I)]

        posts = []
        with st.spinner("Pulling posts via Reddit API..."):
            try:
                for sr in subreddits:
                    for post in reddit.subreddit(sr).new(limit=limit):
                        content = f"{post.title}\n{post.selftext}".lower()
                        if any(term in content for term in terms):
                            posts.append({
                                "Platform": "Reddit",
                                "Post_dt": dt.datetime.utcfromtimestamp(post.created_utc),
                                "Post Content": post.title + "\n" + post.selftext,
                                "Subreddit": post.subreddit.display_name,
                                "Post URL": f"https://www.reddit.com{post.permalink}",
                            })
            except Exception as e:
                st.error(f"❌ Failed to fetch posts from Reddit: {e}")
                st.stop()

        if not posts:
            st.warning("⚠️ No matching posts found.")
            st.stop()

        df = pd.DataFrame(posts)
        df["Bucket"] = df["Post Content"].fillna("*").apply(tag_bucket)

elif source_mode == "📁 Upload Excel":
    st.sidebar.write("Upload the Excel export (one sheet per search phrase)")
    uploaded_file = st.sidebar.file_uploader("Drag and drop file here", type="xlsx")

    if uploaded_file:
        sheetnames = pd.ExcelFile(uploaded_file).sheet_names
        selected = st.sidebar.selectbox("Choose a sheet / search phrase", sheetnames)
        df = pd.read_excel(uploaded_file, sheet_name=selected)

        st.write("🧾 Columns in uploaded sheet:", df.columns.tolist())

        # --- Flexible column detection --- #
        if "Post Content" not in df.columns:
            first_col = df.columns[0]
            st.warning(f"⚠️ 'Post Content' not found. Renaming '{first_col}' to 'Post Content'.")
            df.rename(columns={first_col: "Post Content"}, inplace=True)

        if "Bucket" not in df.columns:
            df["Bucket"] = df["Post Content"].fillna("*").apply(tag_bucket)

        if "Post_dt" not in df.columns:
            df["Post_dt"] = pd.Timestamp("now")

        if "Subreddit" not in df.columns:
            df["Subreddit"] = "Unknown"
    else:
        st.stop()

# ---------- Shared visual section ---------- #
if df is not None:
    st.success(f"✅ Loaded {len(df)} posts for analysis")

    # Interactive filters
    st.sidebar.subheader("Filter Options")
    unique_buckets = df["Bucket"].unique().tolist()
    selected_buckets = st.sidebar.multiselect("Select Buckets", unique_buckets, default=unique_buckets)

    min_date = df["Post_dt"].min()
    max_date = df["Post_dt"].max()
    date_range = st.sidebar.date_input("Select Date Range", [min_date, max_date])

    if len(date_range) == 2:
        start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        df = df[df["Post_dt"].between(start_date, end_date)]

    df = df[df["Bucket"].isin(selected_buckets)]

    st.subheader("📊 Post volume by bucket")
    st.bar_chart(df["Bucket"].value_counts().sort_values(ascending=False))

    if "Subreddit" in df.columns:
        st.subheader("🧠 Top subreddits")
        st.bar_chart(df["Subreddit"].value_counts().head(10))

    st.subheader("📄 Content sample")
    try:
        preview_cols = [c for c in ["Post_dt", "Bucket", "Subreddit", "Post Content"] if c in df.columns]
        st.dataframe(df[preview_cols].head(30), height=300)
    except Exception as e:
        st.warning(f"⚠️ Could not render content sample: {e}")

    if "other" in df["Bucket"].unique():
        with st.expander("🔍 Top words in 'other'"):
            top = (
                df[df["Bucket"] == "other"]["Post Content"]
                .fillna("")
                .str.lower()
                .str.findall(r"[a-z']{4,}")
                .explode()
                .value_counts()
                .head(40)
                .reset_index().rename(columns={"index": "word", 0: "freq"})
            )
            st.dataframe(top, height=250)

st.caption("© 2025 Shadee.Care • Live Reddit & Excel dashboard (v9d)")
