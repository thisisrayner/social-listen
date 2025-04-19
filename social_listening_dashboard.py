# Shadee.Care – Social Listening Dashboard (v9 k3)
# ---------------------------------------------------------------
# • Excel path unchanged (ALL + date + bucket filters).
# • Live Reddit Pull restored: keywords, subreddit, max‑posts, fetch button.
# • Bucket tagging improved (tight regex); clearer subreddit/channel labeling.
# • Bucket-level trend lines and top sources (Reddit/YouTube aware).
# ---------------------------------------------------------------

import re
import datetime as dt
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st
import praw

# ───────────────────────────────────────────────────────────────
#  Helpers
# ───────────────────────────────────────────────────────────────
DATE_RE = re.compile(r"(\d{1,2}:\d{2})\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")
MON = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun",
     "Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

def parse_post_date(txt: str):
    if not isinstance(txt, str): return pd.NaT
    m = DATE_RE.search(txt)
    if not m: return pd.NaT
    time_s, day, mon_s, year = m.groups()
    hh, mm = map(int, time_s.split(":"))
    try:
        return dt.datetime(int(year), MON[mon_s], int(day), hh, mm)
    except ValueError:
        return pd.NaT

# ── config ─────────────────────────────────────────────────────
st.set_page_config("Shadee Live Listening", layout="wide", initial_sidebar_state="expanded")

if "reddit_api" not in st.session_state and "reddit" in st.secrets:
    creds = st.secrets["reddit"]
    st.session_state.reddit_api = praw.Reddit(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        user_agent=creds["user_agent"],
        check_for_async=False,
    )
    st.sidebar.markdown(f"🔍 **Reddit client**: `{creds['client_id']}` – anon script scope")

# ── bucket logic ─────────────────────────────────────────────────────────
BUCKET_PATTERNS: Dict[str, str] = {
    'self_blame': r"(hate(?:s|d)? (?:myself|me)|everyone hate(?:s|d)? me|worthless|i (?:don't|do not) deserve to live|i'?m a failure|blame myself|all my fault)",
    'cost_concern': r"(can'?t afford|too expensive|cost of therapy|insurance won't|no money for help)",
    'work_burnout': r"(burnt out|burned out|toxic work|overworked|study burnout|no work life balance|exhausted from work)",
    'self_harm': r"(kill myself|end my life|suicid(?:e|al)|self[- ]?harm|cutting myself|hurting myself)",
    'relationship_breakup': r"(break[- ]?up|dump(?:ed)?|heart ?broken|lost my (?:partner|girlfriend|boyfriend)|she left me|he left me)",
    'friendship_drama': r"(friend(?:ship)? (?:ignore(?:d)?|ghost(?:ed)?|lost)|no friends?|friends don't care)",
    'crying_distress': r"(can'?t stop crying|keep on crying|crying every night|cry myself to sleep)",
    'depression_misery': r"(i['’]?m (?:so )?(?:depressed|miserable|numb|empty)|i feel dead inside|life is meaningless|hopeless|no reason to live|can't go on|don't want to exist|done with life)",
    'loneliness_isolation': r"(i['’]?m (?:so )?(?:lonely|alone|isolated)|nobody (?:cares|loves me)|no one to talk to|feel invisible|no support system|abandoned)",
    'family_conflict': r"(my (?:mom|dad|parents|family) (?:hate me|don't understand|abusive|arguing|don't care)|fight with (?:mom|dad|family)|toxic family|family pressure|neglect)",
    'family_loss_or_absence': r"(i miss my (?:mom|dad|parent|family)|grew up without (?:a|my) (?:dad|mom)|orphan|parent passed away|lost (?:my )?(?:dad|mom|guardian))"
}
COMPILED = {name: re.compile(pat, re.I) for name, pat in BUCKET_PATTERNS.items()}
 ─────────────────────────────────────────────────────
st.sidebar.header("📊 Choose Data Source")
MODE = st.sidebar.radio("Select mode", ("Upload Excel", "Live Reddit Pull"), index=0)
end_d = dt.date.today()
start_d = end_d - dt.timedelta(days=30)
start_d, end_d = st.sidebar.date_input("Select Date Range", (start_d, end_d))

# Helper to show top subreddits

def show_top_subreddits(df):
    st.subheader("🧠 Top subreddits")
    if "Subreddit" in df.columns and df["Subreddit"].notna().any():
        st.bar_chart(df["Subreddit"].fillna("Unknown").value_counts().head(10))
    else:
        st.info("Subreddit column not present in this dataset.")

# ──────────────────────────────────────────────────────────────
#  Upload Excel Mode
# ──────────────────────────────────────────────────────────────
if MODE == "Upload Excel":
    xl_file = st.sidebar.file_uploader("Drag and drop Excel", type="xlsx")
    if xl_file is None: st.stop()
    with pd.ExcelFile(xl_file) as xl: sheets = xl.sheet_names
    sheet_choice = st.sidebar.selectbox("Sheet", ["ALL"] + sheets, index=0)

    dfs: List[pd.DataFrame] = []
    with pd.ExcelFile(xl_file) as xl:
        for sh in (sheets if sheet_choice == "ALL" else [sheet_choice]):
            df_s = xl.parse(sh, skiprows=2)
            if {"Post Date", "Post Content"}.issubset(df_s.columns):
                df_s["Post_dt"] = df_s["Post Date"].map(parse_post_date)
                dfs.append(df_s)
            else:
                st.warning(f"Sheet ‘{sh}’ missing columns → skipped")

    if not dfs:
        st.error("No valid sheets found.")
        st.stop()

    df = pd.concat(dfs, ignore_index=True)
    df["Bucket"] = df["Post Content"].apply(tag_bucket)
    df = df.dropna(subset=["Post_dt"]).copy()
    df = df[(df["Post_dt"].dt.date >= start_d) & (df["Post_dt"].dt.date <= end_d)]

    if df.empty:
        st.info("No posts in selected window.")
        st.stop()

    sel_buckets = st.sidebar.multiselect("Select buckets", sorted(df["Bucket"].unique()), default=sorted(df["Bucket"].unique()))
    df = df[df["Bucket"].isin(sel_buckets)]
    st.success(f"✅ {len(df)} posts after filtering")

    st.subheader("📊 Post volume by bucket")
    st.bar_chart(df["Bucket"].value_counts())

    st.subheader("📈 Post trend over time")
    trend = (
        df.set_index("Post_dt")
        .assign(day=lambda _d: _d.index.date)
        .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
        .fillna(0)
    )
    st.line_chart(trend)

    st.subheader("🧠 Top sources (subreddit / channel)")
    source_col = "Subreddit" if "Subreddit" in df.columns and df["Subreddit"].notna().any() else "Username"
    if source_col in df.columns:
        st.bar_chart(df[source_col].fillna("Unknown").value_counts().head(10))
    else:
        st.info("No valid source column found.")

    st.subheader("📄 Content sample")
    show_cols = [c for c in ["Post_dt", "Bucket", "Subreddit", "Platform", "Post Content"] if c in df.columns]
    # Show up to 100 rows, with a visible window of ~20 rows
    st.dataframe(df[show_cols].head(100), height=600)

# ──────────────────────────────────────────────────────────────
#  Live Reddit Pull Mode
# ──────────────────────────────────────────────────────────────
else:
    phrase = st.sidebar.text_input("Search phrase (keywords, OR‑supported)", "lonely OR therapy")
    subreddit = st.sidebar.text_input("Subreddit (e.g. depression or all)", "depression")
    max_posts = st.sidebar.slider("Max posts to fetch", 10, 300, 50)

    if st.sidebar.button("🔍 Fetch live posts"):
        reddit = st.session_state.get("reddit_api")
        if reddit is None:
            st.error("Reddit API not configured.")
            st.stop()

        st.info(f"Fetching from r/{subreddit}...")
        results = reddit.subreddit(subreddit).search(phrase, limit=max_posts)
        posts = [
            {
                "Post_dt": dt.datetime.fromtimestamp(p.created_utc),
                "Post Content": p.title + "\n\n" + (p.selftext or ""),
                "Subreddit": p.subreddit.display_name,
                "Platform": "reddit",
            }
            for p in results
        ]

        if not posts:
            st.warning("No posts returned.")
            st.stop()

        df = pd.DataFrame(posts)
        df["Bucket"] = df["Post Content"].apply(tag_bucket)
        df = df.dropna(subset=["Post_dt"]).copy()

        st.success(f"✅ {len(df)} posts fetched")
        st.subheader("📊 Post volume by bucket")
        st.bar_chart(df["Bucket"].value_counts())

        st.subheader("📈 Post trend over time")
        trend = (
            df.set_index("Post_dt")
            .assign(day=lambda _d: _d.index.date)
            .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
            .fillna(0)
        )
        st.line_chart(trend)

        st.subheader("🧠 Top sources (subreddit)")
        st.bar_chart(df["Subreddit"].fillna("Unknown").value_counts().head(10))

        st.subheader("📄 Content sample")
        show_cols = [c for c in ["Post_dt", "Bucket", "Subreddit", "Post Content"] if c in df.columns]
        # Show up to 100 rows, with a visible window of ~20 rows
        st.dataframe(df[show_cols].head(100), height=600)
