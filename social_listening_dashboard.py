# Shadee.Care – Social Listening Dashboard (v3 – regex buckets)
# ------------------------------------------------------------------
# Streamlit app that visualises post activity scraped from Reddit &
# YouTube (Excel export with one sheet per search‑phrase).
# v3 upgrade: keyword buckets now use **regex** patterns so that close
# variations (e.g. "hated myself", "can't afford", "burned‑out") are
# captured without writing dozens of near‑duplicate phrases.
# ------------------------------------------------------------------
# HOW TO RUN LOCALLY
#   1. pip install streamlit pandas matplotlib openpyxl
#   2. streamlit run social_listening_dashboard.py
#   3. Upload the Excel file when prompted.
# ------------------------------------------------------------------

import re
import datetime as dt
from typing import Dict

import pandas as pd
import streamlit as st

# ---------- Keyword bucket regexes ---------- #
# Each bucket is a single **raw string regex** (ignore‑case).  Regex
# lets us match plurals, tense changes, or words near each other.
BUCKET_PATTERNS: Dict[str, str] = {
    "self_blame": r"\b(hate(?:d|s)? myself|everyone hate(?:s|d)? me|worthless|i'?m a failure|no one cares|what'?s wrong with me|deserve(?:s)? to suffer)\b",
    "cost_concern": r"\b(can'?t afford|too expensive|cost of therapy|insurance won'?t|money for help|cheap therapy|on a budget)\b",
    "work_burnout": r"\b(burnt out|burned out|exhausted by work|quit(?:ting)? my job|toxic work(?:place)?|overworked|deadlines|study burnout)\b",
}

BUCKET_COLOURS = {
    "self_blame": "🟥",
    "cost_concern": "🟨",
    "work_burnout": "🟩",
    "other": "⬜️",
}

# Pre‑compile for speed
COMPILED = {k: re.compile(pat, re.I) for k, pat in BUCKET_PATTERNS.items()}

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
    roll_mean = series.rolling(window).mean()
    roll_std = series.rolling(window).std().fillna(0)
    return series[series > roll_mean + sigma * roll_std]


@st.cache_data(show_spinner=False)
def tag_bucket(text: str) -> str:
    text_low = text.lower()
    for bucket, pat in COMPILED.items():
        if pat.search(text_low):
            return bucket
    return "other"


# ---------- Streamlit UI ---------- #

st.set_page_config(page_title="Shadee Social Listening", layout="wide")
st.title("🩺 Shadee.Care – Social Listening Dashboard (regex edition)")

uploaded = st.sidebar.file_uploader("Upload the Excel scrape (one sheet per search phrase)", type=["xlsx"])

if uploaded is None:
    st.info("⬅️ Upload an Excel file to begin.")
    st.stop()

# Load all sheets
xls = pd.ExcelFile(uploaded)
raw_dfs = {name: pd.read_excel(uploaded, sheet_name=name, header=2) for name in xls.sheet_names}

phrase = st.sidebar.selectbox("Choose a sheet / search phrase", list(raw_dfs.keys()))
df = raw_dfs[phrase].copy()

# ---------- Data cleaning ---------- #

df["Post_dt"] = df.get("Post Date", pd.Series(dtype=str)).apply(parse_post_date)
df["Subreddit"] = df.apply(lambda r: extract_subreddit(r.get("Post URL")), axis=1)

if "Post Content" not in df:
    df["Post Content"] = ""

# Tag buckets via regex
df["Bucket"] = df["Post Content"].fillna("").apply(tag_bucket)

# Bucket filter
selected = st.sidebar.multiselect(
    "Filter keyword buckets",
    options=list(BUCKET_PATTERNS.keys()) + ["other"],
    default=list(BUCKET_PATTERNS.keys()),
)
if selected:
    df = df[df["Bucket"].isin(selected)]

# ---------- Metrics ---------- #
col1, col2, col3 = st.columns(3)
col1.metric("Posts", len(df))
col2.metric("% Reddit", f"{(df['Platform']=='Reddit').mean()*100:.1f}%")
col3.metric("Timespan", f"{(df['Post_dt'].max() - df['Post_dt'].min()).days} d" if df["Post_dt"].notna().any() else "n/a")

st.markdown("**Bucket legend:** " + "  ".join(f"{BUCKET_COLOURS.get(b, '⬜️')} {b}" for b in BUCKET_PATTERNS))

# ---------- Time‑series by bucket ---------- #

if df["Post_dt"].notna().any():
    pivot = (
        df.set_index("Post_dt").groupby("Bucket").resample("D").size().unstack(fill_value=0).T
    )
    st.subheader("Daily post volume by bucket (regex matched)")
    st.line_chart(pivot)

    # Spike detection
    alerts = [
        {"date": d.date(), "bucket": b, "count": int(c)}
        for b in pivot.columns
        for d, c in detect_spikes(pivot[b]).items()
    ]
    if alerts:
        st.subheader("⚠️ Spike alerts")
        st.dataframe(pd.DataFrame(alerts))
else:
    st.warning("No date information.")

# ---------- Top communities ---------- #

st.subheader("Top communities")
if (df["Platform"] == "Reddit").any():
    st.write("### Reddit")
    st.bar_chart(df["Subreddit"].value_counts().head(10))

if df["Platform"].str.contains("Youtube", case=False).any():
    def yt_channel(url):
        if not isinstance(url, str):
            return None
        m = re.search(r"youtube\.com/(?:channel|user)/([^/?]+)", url)
        return m.group(1) if m else None

    df["YT_channel"] = df.apply(lambda r: yt_channel(r.get("User URL")), axis=1)
    st.write("### YouTube channels")
    st.bar_chart(df["YT_channel"].value_counts().head(10))

# ---------- Content sample ---------- #

st.subheader("Quick content sample (click row to copy text)")
kw = st.text_input("Filter posts containing…")
filtered = df if kw == "" else df[df["Post Content"].str.contains(kw, case=False, na=False)]

st.dataframe(filtered[["Platform", "Post_dt", "Bucket", "Post Content"]].head(250), height=300)

st.caption("© 2025 Shadee.Care • Dashboard v3 – regex buckets")
