# Shadee.Care – Social Listening Dashboard (v9h)
# ------------------------------------------------------------------------
# • Excel uploader now adds an **ALL** option – combines every sheet.
# • YouTube rows inside the Excel file are handled the same way as Reddit.
# ------------------------------------------------------------------------

import re
import datetime as dt
from typing import Dict

import pandas as pd
import streamlit as st
import praw

# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────
DATE_RE = re.compile(r"(\d{1,2}:\d{2})\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")
MON = {m: i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

def parse_post_date(txt: str):
    """Convert strings like 'Posted 05:44 13 Apr 2025' to a datetime.
    Returns pd.NaT if the string cannot be parsed."""
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
#  Page setup & Reddit client
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Shadee Live Listening", layout="wide")

if "reddit_api" not in st.session_state:
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
#  Bucket regexes
# ──────────────────────────────────────────────────────────────
BUCKET_PATTERNS: Dict[str, str] = {
    # strong self‑loathing or worthlessness
    "self_blame": r"(hate(?:s|d)? (?:myself|me|everybody|people)|everyone hate(?:s|d)? (?:me|people)|worthless|i (?:don'?t|do not) deserve to live|i'?m a failure|no one cares|what'?s wrong with me|deserve(?:s)? to suffer)",

    # cost / access worries
    "cost_concern": r"(can'?t afford|too expensive|cost of therapy|insurance won'?t|money for help|cheap therapy|on a budget)",

    # work & study burnout
    "work_burnout": r"(burnt out|burned out|exhausted by work|quit(?:ting)? my job|toxic work(?:place)?|overworked|deadlines|study burnout)",

    # self‑harm & suicide ideation
    "self_harm": r"(kill myself|end my life|suicid(?:e|al)|self[- ]?harm|jump off|take my life|die by suicide)",

    # romantic breakup / heartbreak
    "relationship_breakup": r"(break[- ]?up|dump(?:ed|ing)?|heart ?broken|ex[- ]?(?:bf|gf)|my ex|lost my (partner|girlfriend|boyfriend))",

    # friendship conflict / rejection
    "friendship_drama": r"(friend(?:ship)? (?:ignore(?:d)?|ghost(?:ed|ing)?|betray(?:ed)?|leave|leaving|lost)|lost my friends?|no friends?|cut off friends?|my (?:best )?friend(?:s)? (?:hate|left|stopped talking))",

    # acute crying / emotional overwhelm (YouTube shorts & vents)
    "crying_distress": r"(can'?t stop crying|keep (?:on )?crying|cry(?:ing)? every (?:night|day)|cry myself to sleep|sob(?:bing)? uncontrollably)",
}

# compile once
COMPILED = {name: re.compile(pat, re.I) for name, pat in BUCKET_PATTERNS.items()} = {name: re.compile(pat, re.I) for name, pat in BUCKET_PATTERNS.items()}

def tag_bucket(txt: str) -> str:
    low = txt.lower()
    for b, pat in COMPILED.items():
        if pat.search(low):
            return b
    return "other"

# ──────────────────────────────────────────────────────────────
#  UI
# ──────────────────────────────────────────────────────────────
st.title("🔴 Shadee.Care – Reddit Live + Excel Social Listening Dashboard")
side = st.sidebar
side.header("Choose Data Source")
mode = side.radio("Select mode", ["🔴 Live Reddit Pull", "📁 Upload Excel"])

df = None

# ──────────────────────────────────────────────────────────────
#  Fetch data
# ──────────────────────────────────────────────────────────────
if mode.startswith("🔴"):
    q = side.text_input("Search phrase", "lonely OR therapy")
    sub = side.text_input("Subreddit", "depression")
    lim = side.slider("Max posts", 10, 200, 50)
    if side.button("🔍 Fetch live posts"):
        terms = [t.strip().lower() for t in re.split(r"\bOR\b", q, flags=re.I)]
        subs = sub.split("+") if "+" in sub else [sub]
        rows = []
        with st.spinner("Contacting Reddit …"):
            for sr in subs:
                for p in st.session_state.reddit_api.subreddit(sr).new(limit=lim):
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
else:  # Excel branch
    up = side.file_uploader("Drag & drop Excel", type="xlsx")
    if up:
        xls = pd.ExcelFile(up)
        sheet_choices = ["ALL"] + xls.sheet_names
        chosen = side.selectbox("Sheet", sheet_choices)
        if chosen == "ALL":
            _d = pd.read_excel(up, sheet_name=None, header=2)
            df = pd.concat(_d.values(), ignore_index=True)
        else:
            df = pd.read_excel(up, sheet_name=chosen, header=2)

        # Harmonise columns
        if "Post Content" not in df.columns and len(df.columns) >= 5:
            df.rename(columns={df.columns[4]: "Post Content"}, inplace=True)
        if "Post_dt" not in df.columns:
            if "Post Date" in df.columns:
                df["Post_dt"] = df["Post Date"].apply(parse_post_date)
            else:
                df["Post_dt"] = pd.Timestamp.now()
        if "Subreddit" not in df.columns:
            df["Subreddit"] = "Unknown"

# ──────────────────────────────────────────────────────────────
#  Analyse / plot
# ──────────────────────────────────────────────────────────────
if df is not None and not df.empty:
    df["Post_dt"] = pd.to_datetime(df["Post_dt"], errors="coerce")
    df.dropna(subset=["Post_dt"], inplace=True)
    df["Post_date"] = df["Post_dt"].dt.date

    if "Bucket" not in df.columns:
        df["Bucket"] = df["Post Content"].fillna("*").apply(tag_bucket)

    sel_b = side.multiselect("Select buckets", sorted(df["Bucket"].unique()), default=sorted(df["Bucket"].unique()))
    df = df[df["Bucket"].isin(sel_b)]

    st.success(f"✅ {len(df)} posts after filtering")

    st.subheader("📊 Post volume by bucket")
    st.bar_chart(df["Bucket"].value_counts())

    st.subheader("📈 Post trend over time")
    st.line_chart(df.groupby("Post_date").size())

    st.subheader("🧠 Top subreddits")
    st.bar_chart(df["Subreddit"].value_counts().head(10))

    st.subheader("📄 Content sample")
    st.dataframe(
        df[[c for c in ["Post_dt", "Bucket", "Subreddit", "Post Content"] if c in df.columns]].head(30),
        height=260,
    )

st.caption("© 2025 Shadee.Care • Live Reddit & Excel dashboard (v9h)")
