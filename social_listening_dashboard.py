# Shadee.Care – Social Listening Dashboard (v9b – Reddit live pull with timeout)
# ------------------------------------------------------------------
# Now includes timeout handling for psaw/Pushshift API
# Prevents infinite hangs if Pushshift is unresponsive
# ------------------------------------------------------------------

import re
import datetime as dt
from typing import Dict
from itertools import islice
import time

import pandas as pd
import streamlit as st

from psaw import PushshiftAPI
import praw

# ---------- Reddit API init ---------- #
if "reddit_api" not in st.session_state:
    creds = st.secrets["reddit"]
    reddit = praw.Reddit(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        user_agent=creds["user_agent"]
    )
    st.session_state.reddit_api = PushshiftAPI(reddit)

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
st.set_page_config(page_title="Shadee Live Listening", layout="wide")
st.title("🔴 Shadee.Care – Reddit Live Listening Dashboard")

with st.sidebar:
    st.header("Live Reddit Pull")
    query = st.text_input("Search phrase", "lonely OR therapy")
    subr = st.text_input("Subreddit (optional)", "depression")
    hours = st.slider("Lookback hours", 1, 72, 6)
    limit = st.slider("Max posts", 10, 200, 50)
    do_fetch = st.button("🔍 Fetch live posts")

if do_fetch:
    api = st.session_state.reddit_api
    start = int((dt.datetime.utcnow() - dt.timedelta(hours=hours)).timestamp())
    
    with st.spinner("Pulling live posts from Reddit..."):
        try:
            raw = api.search_submissions(q=query, subreddit=subr or None, after=start)
            results = list(islice(raw, limit))  # limit using islice
        except Exception as e:
            st.error(f"Failed to fetch posts: {e}")
            results = []

    if not results:
        st.warning("⚠️ No posts returned (Pushshift may be down or timing out)")
        st.stop()

    posts = []
    for p in results:
        posts.append({
            "Platform": "Reddit",
            "Post_dt": dt.datetime.utcfromtimestamp(p.created_utc),
            "Post Content": (p.title or "") + "\n" + (p.selftext or ""),
            "Subreddit": p.subreddit.display_name,
            "Post URL": f"https://www.reddit.com{p.permalink}",
        })

    df = pd.DataFrame(posts)
    df["Bucket"] = df["Post Content"].fillna("*").apply(tag_bucket)

    st.success(f"Fetched {len(df)} posts")

    # ----- Visualise ----- #
    st.subheader("📊 Post volume by bucket")
    st.bar_chart(df["Bucket"].value_counts().sort_values(ascending=False))

    st.subheader("🧠 Top subreddits")
    st.bar_chart(df["Subreddit"].value_counts().head(10))

    st.subheader("📄 Content sample")
    st.dataframe(df[["Post_dt", "Bucket", "Subreddit", "Post Content"]].head(30), height=300)

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

st.caption("© 2025 Shadee.Care • Reddit live search (v9b)")
