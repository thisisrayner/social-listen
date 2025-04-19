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

# ── bucket logic ─────────────────────────────────────────────────
BUCKET_PATTERNS: Dict[str, str] = {
    'self_blame': r"\b(hate(?:s|d)? (?:myself|me)|everyone hate(?:s|d)? me|worthless|i (?:don\'t|do not) deserve to live|i\'?m a failure|blame myself|all my fault)\b",
    'cost_concern': r"\b(can\'?t afford|too expensive|cost of therapy|insurance won\'?t|no money for help)\b",
    'work_burnout': r"\b(burnt out|burned out|toxic work|overworked|study burnout|no work life balance|exhausted from work)\b",
    'self_harm': r"\b(kill myself|end my life|suicid(?:e|al)|self[- ]?harm|cutting myself|hurting myself)\b",
    'relationship_breakup': r"\b(break[- ]?up|dump(?:ed)?|heart ?broken|lost my (?:partner|girlfriend|boyfriend)|she left me|he left me)\b",
    'friendship_drama': r"\b(friend(?:ship)? (?:ignore(?:d)?|ghost(?:ed)?|lost)|no friends\?|friends don\'?t care)\b",
    'crying_distress': r"\b(can\'?t stop crying|keep on crying|crying every night|cry myself to sleep)\b",
    'depression_misery': r"\b(i[\'’\"]?m (so )?(depressed|miserable|numb|empty)|i feel dead inside|life is meaningless|hopeless|no reason to live|can\'t go on|don[\'’\"]?t want to exist|done with life)\b",
    'loneliness_isolation': r"\b(i[\'’\"]?m (so )?(lonely|alone|isolated)|nobody (cares|loves me)|no one to talk to|feel invisible|no support system|abandoned)\b",
    'family_conflict': r"\b(my (mom|dad|parents|family) (hate me|don[\'’\"]?t understand|abusive|arguing|don[\'’\"]?t care)|fight with (mom|dad|family)|toxic family|family pressure|neglect)\b",
    'family_loss_or_absence': r"\b(i miss my (mom|dad|parent|family)|grew up without (a|my) (dad|mom)|orphan|parent passed away|lost (my )?(dad|mom|guardian))\b"
}
COMPILED = {name: re.compile(pat, re.I) for name, pat in BUCKET_PATTERNS.items()}

def tag_bucket(text: str):
    if not isinstance(text, str): return "other"
    for name, pat in COMPILED.items():
        if pat.search(text): return name
    return "other"

# ── sidebar ─────────────────────────────────────────────────────
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

# … rest of code unchanged …
