# Shadee.Care – Social Listening Dashboard (v9 k5)
# ---------------------------------------------------------------
# • Excel + date + bucket filters (ALL / sheet, last 30 days default).
# • Live Reddit Pull: keywords, subreddit, max‑posts, fetch button.
# • Bucket tagging with regex boundaries; top subreddits (Reddit only).
# ---------------------------------------------------------------

import re
import datetime as dt
from typing import Dict, List

import pandas as pd
import streamlit as st
import praw

# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────
# Matches strings like "05:44 19 Apr 2025"
DATE_RE = re.compile(r"(\d{1,2}:\d{2})\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")
MON = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun",
     "Jul","Aug","Sep","Oct","Nov","Dec"], 1)}


def parse_post_date(txt: str) -> pd.Timestamp:
    """
    Parse strings like "05:44 19 Apr 2025" into a pandas Timestamp, or return NaT.
    """
    if not isinstance(txt, str):
        return pd.NaT
    m = DATE_RE.search(txt)
    if not m:
        return pd.NaT
    time_s, day, mon_s, year = m.groups()
    hh, mm = map(int, time_s.split(":"))
    try:
        return pd.Timestamp(year=int(year), month=MON[mon_s], day=int(day), hour=hh, minute=mm)
    except Exception:
        return pd.NaT


# ── config ────────────────────────────────────────────────────
st.set_page_config(page_title="Shadee Live Listening", layout="wide", initial_sidebar_state="expanded")

if "reddit_api" not in st.session_state and "reddit" in st.secrets:
    creds = st.secrets["reddit"]
    st.session_state.reddit_api = praw.Reddit(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        user_agent=creds["user_agent"],
        check_for_async=False,
    )
    st.sidebar.markdown(f"🔍 **Reddit client**: `{creds['client_id']}` – anon script scope")

# ── bucket logic ──────────────────────────────────────────────
BUCKET_PATTERNS: Dict[str, str] = {
    "self_blame":           r"\b(hate(?:s|d)? (?:myself|me)|everyone hate(?:s|d)? me|worthless|i (?:don't|do not) deserve to live|i'm a failure|blame myself|all my fault)\b",
    "cost_concern":         r"\b(can't afford|too expensive|cost of therapy|insurance won't cover|no money for help)\b",
    "work_burnout":         r"\b(burnt out|burned out|toxic work|overworked|no work[- ]life balance|exhausted from work)\b",
    "self_harm":            r"\b(kill myself|end my life|suicid(?:e|al)|self[- ]?harm|cutting myself)\b",
    "relationship_breakup": r"\b(break[- ]?up|dump(?:ed)?|heartbroken|lost my (?:partner|girlfriend|boyfriend)|she left me|he left me)\b",
    "friendship_drama":     r"\b(friend(?:ship)? (?:ignored|ghosted|lost)|no friends?|friends don't care)\b",
    "crying_distress":      r"\b(can't stop crying|cry myself to sleep|crying every night)\b",
    "depression_misery":    r"\b(i(?:'m| am) (?:so )?(depressed|miserable|numb|empty)|i feel dead inside|life is meaningless|hopeless|no reason to live|can't go on|don't want to exist)\b",
    "loneliness_isolation": r"\b(i(?:'m| am) (?:so )?(lonely|alone|isolated)|nobody (cares|loves me)|no one to talk to|feel invisible|no support system)\b",
    "family_conflict":      r"\b(my (?:mom|dad|parents|family) (?:hate me|don't understand|abusive|arguing)|fight with (?:mom|dad|family)|toxic family)\b",
    "family_loss":          r"\b(i miss my (?:mom|dad|parent|family)|grew up without (?:a|my) (?:dad|mom)|orphan|parent passed away|lost (?:my )?(?:dad|mom|guardian))\b",
}
COMPILED = {k: re.compile(v, re.I) for k, v in BUCKET_PATTERNS.items()}


def tag_bucket(text: str) -> str:
    if not isinstance(text, str):
        return "other"
    for name, pat in COMPILED.items():
        if pat.search(text):
            return name
    return "other"

# ── sidebar ────────────────────────────────────────────────────
st.sidebar.header("📊 Choose Data Source")
MODE = st.sidebar.radio("Select mode", ("Upload Excel", "Live Reddit Pull"), index=0)
end_d = dt.date.today()
start_d = end_d - dt.timedelta(days=30)
start_d, end_d = st.sidebar.date_input("Select Date Range", (start_d, end_d))

# Utility components

def show_top_subreddits(df: pd.DataFrame):
    st.subheader("🧠 Top subreddits")
    if "Subreddit" in df.columns:
        red = df[df.get("Platform") == "reddit"] if "Platform" in df.columns else df
        if red.empty:
            st.info("No Reddit data available.")
        else:
            st.bar_chart(red["Subreddit"].fillna("Unknown").value_counts().head(10))
    else:
        st.info("Subreddit column not present.")


def show_content_sample(df: pd.DataFrame):
    st.subheader("📄 Content sample")
    cols = [c for c in ("Post_dt","Bucket","Subreddit","Platform","Post Content") if c in df.columns]
    st.dataframe(df[cols].head(50), height=300)

# ──────────────────────────────────────────────────────────────
#  Upload Excel Mode
# ──────────────────────────────────────────────────────────────
if MODE == "Upload Excel":
    file = st.sidebar.file_uploader("Drag & drop Excel", type=["xlsx"])
    if not file:
        st.stop()
    with pd.ExcelFile(file) as xl:
        sheets = xl.sheet_names
    choice = st.sidebar.selectbox("Sheet", ["ALL"] + sheets)

    frames: List[pd.DataFrame] = []
    with pd.ExcelFile(file) as xl:
        for sh in (sheets if choice == "ALL" else [choice]):
            df_s = xl.parse(sh, skiprows=2)
            if {"Post Date","Post Content"}.issubset(df_s.columns):
                df_s["Post_dt"] = df_s["Post Date"].map(parse_post_date)
                frames.append(df_s)
            else:
                st.warning(f"Sheet '{sh}' missing columns → skipped")

    if not frames:
        st.error("No valid sheets.")
        st.stop()
    df = pd.concat(frames, ignore_index=True)
    df["Bucket"] = df["Post Content"].apply(tag_bucket)

    # Allow users to select from all buckets before date filtering
    buckets = sorted(df["Bucket"].unique())
    sel = st.sidebar.multiselect("Select buckets", buckets, default=buckets)
    df = df[df["Bucket"].isin(sel)]

    df = df.dropna(subset=["Post_dt"])
    df = df[(df["Post_dt"].dt.date >= start_d) & (df["Post_dt"].dt.date <= end_d)]
    if df.empty:
        st.info("No posts in range.")
        st.stop()

    buckets = sorted(df["Bucket"].unique())
    sel = st.sidebar.multiselect("Select buckets", buckets, default=buckets)
    df = df[df["Bucket"].isin(sel)]
    st.success(f"✅ {len(df)} posts after filtering")

    st.subheader("📊 Post volume by bucket")
    st.bar_chart(df["Bucket"].value_counts())

    st.subheader("📈 Post trend over time")
    trend = (
        df.set_index("Post_dt")
          .assign(day=lambda d: d.index.date)
          .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count").fillna(0)
    )
    st.line_chart(trend)

    show_top_subreddits(df)
    show_content_sample(df)

else:
    phrase    = st.sidebar.text_input("Search phrase (OR-supported)", "lonely OR therapy")
    subreddit = st.sidebar.text_input("Subreddit (e.g. depression)", "depression")
    max_p     = st.sidebar.slider("Max posts to fetch", 10, 300, 50)

    if st.sidebar.button("🔍 Fetch live posts"):
        reddit = st.session_state.get("reddit_api")
        if not reddit:
            st.error("Reddit API not set.")
            st.stop()
        st.info(f"Fetching from r/{subreddit}... ")
        posts = [
            {"Post_dt": dt.datetime.fromtimestamp(p.created_utc),
             "Post Content": p.title + "\n\n" + (p.selftext or ""),
             "Subreddit": p.subreddit.display_name,
             "Platform": "reddit"}
            for p in reddit.subreddit(subreddit).search(phrase, limit=max_p)
        ]
        if not posts:
            st.warning("No posts returned.")
            st.stop()
        df = pd.DataFrame(posts)
        df["Bucket"] = df["Post Content"].apply(tag_bucket)
        df = df.dropna(subset=["Post_dt"])
        st.success(f"✅ {len(df)} posts fetched")

        st.subheader("📊 Post volume by bucket")
        st.bar_chart(df["Bucket"].value_counts())

        st.subheader("📈 Post trend over time")
        trend = (
            df.set_index("Post_dt")
              .assign(day=lambda d: d.index.date)
              .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count").fillna(0)
        )
        st.line_chart(trend)

        show_top_subreddits(df)
        show_content_sample(df)
