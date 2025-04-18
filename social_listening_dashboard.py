# Shadee.Care – Social Listening Dashboard (v2 – keyword buckets)
# ------------------------------------------------------------------
# Streamlit app that visualises post activity scraped from Reddit &
# YouTube (Excel export with one sheet per search‑phrase).  v2 adds:
#   • keyword buckets (self‑blame, cost‑concern, work‑burnout)
#   • per‑bucket daily counts + spike detection
#   • sidebar filter to focus on specific buckets
# ------------------------------------------------------------------
# HOW TO RUN LOCALLY
#   1.  pip install streamlit pandas matplotlib openpyxl
#   2.  streamlit run social_listening_dashboard.py
#   3.  Upload the Excel file when prompted.
# ------------------------------------------------------------------

import re
import datetime as dt
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

# ---------- Keyword buckets ---------- #
# Buckets map to lists of lowercase substrings.  Keep them short for
# simple O(N·K) matching; upgrade to regex or spaCy later if needed.
BUCKETS: Dict[str, List[str]] = {
    "self_blame": [
        "hate myself",
        "everyone hate me",
        "worthless",
        "i'm a failure",
        "no one cares",
        "what's wrong with me",
        "deserve to suffer",
    ],
    "cost_concern": [
        "can't afford",
        "too expensive",
        "cost of therapy",
        "insurance won't",
        "money for help",
        "cheap therapy",
        "budget",
    ],
    "work_burnout": [
        "burnt out",
        "burned out",
        "exhausted by work",
        "quit my job",
        "toxic workplace",
        "overworked",
        "deadlines",
        "study burnout",
    ],
}

BUCKET_COLOURS = {
    "self_blame": "🟥",
    "cost_concern": "🟨",
    "work_burnout": "🟩",
    "other": "⬜️",
}

# ---------- Helper functions ---------- #

def parse_post_date(date_str: str):
    """Convert 'Posted 05:59 15 Apr 2025' → datetime or None."""
    if not isinstance(date_str, str):
        return None
    m = re.search(r"Posted (\d{2}):(\d{2}) (\d{1,2}) (\w{3}) (\d{4})", date_str)
    if not m:
        return None
    hour, minute, day, month_abbr, year = m.groups()
    try:
        month_num = dt.datetime.strptime(month_abbr, "%b").month
        return dt.datetime(int(year), month_num, int(day), int(hour), int(minute))
    except ValueError:
        return None


def extract_subreddit(url: str):
    if not isinstance(url, str):
        return None
    m = re.search(r"reddit\.com/r/([^/]+)/", url)
    return m.group(1) if m else None


def detect_spikes(series: pd.Series, window: int = 7, sigma: float = 2.5):
    """Return subset where value > rolling_mean + sigma*std."""
    roll_mean = series.rolling(window).mean()
    roll_std = series.rolling(window).std().fillna(0)
    return series[series > roll_mean + sigma * roll_std]


# @st.cache_data ensures the bucket test runs only once per unique text
@st.cache_data(show_spinner=False)
def tag_bucket(text: str) -> str:
    text_low = text.lower()
    for bucket, kw_list in BUCKETS.items():
        if any(k in text_low for k in kw_list):
            return bucket
    return "other"


# ---------- Streamlit UI ---------- #

st.set_page_config(page_title="Shadee Social Listening", layout="wide")
st.title("🩺 Shadee.Care – Social Listening Dashboard")

uploaded = st.sidebar.file_uploader("Upload the Excel scrape (one sheet per search phrase)", type=["xlsx"])

if uploaded is None:
    st.info("⬅️ Upload an Excel file to begin.")
    st.stop()

xls = pd.ExcelFile(uploaded)
raw_dfs = {
    name: pd.read_excel(uploaded, sheet_name=name, header=2)
    for name in xls.sheet_names
}

phrase = st.sidebar.selectbox("Choose a sheet / search phrase", list(raw_dfs.keys()))
df = raw_dfs[phrase].copy()

# ---------- Data cleaning ---------- #

df["Post_dt"] = df.get("Post Date", pd.Series(dtype=str)).apply(parse_post_date)

df["Subreddit"] = df.apply(lambda r: extract_subreddit(r.get("Post URL")), axis=1)

# Tag each post into a bucket
if "Post Content" not in df:
    df["Post Content"] = ""
df["Bucket"] = df["Post Content"].fillna("").apply(tag_bucket)

# Bucket filter
selected_buckets = st.sidebar.multiselect(
    "Filter keyword buckets",
    options=list(BUCKETS.keys()) + ["other"],
    default=list(BUCKETS.keys()),
)
if selected_buckets:
    df = df[df["Bucket"].isin(selected_buckets)]

# ---------- Metrics ---------- #
col1, col2, col3 = st.columns(3)
col1.metric("Posts", len(df))
col2.metric("% Reddit", f"{(df['Platform']=='Reddit').mean()*100:.1f}%")
col3.metric(
    "Timespan",
    f"{(df['Post_dt'].max() - df['Post_dt'].min()).days} days"
    if df["Post_dt"].notna().any() else "n/a",
)

st.markdown(
    "**Bucket legend:** " + "  ".join(f"{BUCKET_COLOURS.get(b, '⬜️')} {b}" for b in BUCKETS.keys())
)

# ---------- Time‑series by bucket ---------- #

if df["Post_dt"].notna().any():
    pivot = (
        df.set_index("Post_dt")
        .groupby("Bucket")
        .resample("D")
        .size()
        .unstack(fill_value=0)
        .T  # index = date
    )
    st.subheader("Daily post volume by bucket")
    st.line_chart(pivot)

    # Spike detection per bucket
    alerts = []
    for bucket in pivot.columns:
        spikes = detect_spikes(pivot[bucket])
        for date, count in spikes.items():
            alerts.append({
                "date": date.date(),
                "bucket": bucket,
                "count": int(count),
            })
    if alerts:
        st.subheader("⚠️ Spike alerts")
        st.dataframe(pd.DataFrame(alerts))
else:
    st.warning("No date information in this sheet.")

# ---------- Top communities ---------- #

st.subheader("Top communities")
if (df["Platform"] == "Reddit").any():
    top_subs = df["Subreddit"].value_counts().head(10)
    st.write("### Reddit")
    st.bar_chart(top_subs)

if df["Platform"].str.contains("Youtube", case=False).any():
    def yt_channel(url):
        if not isinstance(url, str):
            return None
        m = re.search(r"youtube\.com/(?:channel|user)/([^/?]+)", url)
        return m.group(1) if m else None

    df["YT_channel"] = df.apply(lambda r: yt_channel(r.get("User URL")), axis=1)
    top_yt = df["YT_channel"].value_counts().head(10)
    st.write("### YouTube channels")
    st.bar_chart(top_yt)

# ---------- Content sample ---------- #

st.subheader("Quick content sample (click row to copy text)")
kw = st.text_input("Filter posts containing… (leave blank for all)")
filtered = df if kw == "" else df[df["Post Content"].str.contains(kw, case=False, na=False)]

st.dataframe(
    filtered[["Platform", "Post_dt", "Bucket", "Post Content"]].head(250),
    height=300,
)

st.caption("© 2025 Shadee.Care • Prototype dashboard v2 – keyword buckets")
