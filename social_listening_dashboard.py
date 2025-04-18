# Shadee.Care – Social Listening Dashboard (v9c – Live Reddit via praw only)
# ------------------------------------------------------------------
# Replaces psaw with direct praw API for stability (Pushshift deprecated)
# Pulls newest posts from subreddit(s), filters by query manually
# ------------------------------------------------------------------

import re
import datetime as dt
from typing import Dict

import pandas as pd
import streamlit as st
import praw

# ---------- Reddit API init ---------- #
if "reddit_api" not in st.session_state:
    creds = st.secrets["reddit"]
    reddit = praw.Reddit(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        user_agent=creds["user_agent"]
    )
    st.session_state.reddit_api = reddit

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
    query = st.text_input("Search phrase (keywords, OR-supported)", "lonely OR therapy")
    subr = st.text_input("Subreddit (e.g. depression or all)", "depression")
    limit = st.slider("Max posts to fetch", 10, 200, 50)
    do_fetch = st.button("🔍 Fetch live posts")

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

    st.success(f"✅ Pulled {len(df)} matching posts from r/{subr}")

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

st.caption("© 2025 Shadee.Care • Reddit live search (v9c – powered by praw)")
