# Shadee.Care – Social Listening Dashboard
# -----------------------------------------------------
# Streamlit app that visualises post activity scraped
# from Reddit & YouTube (Excel export with one sheet
# per search‑phrase). The dashboard highlights spikes
# in emotionally acute keywords such as "crying" or
# "hate me" and surfaces top sub‑communities.
# -----------------------------------------------------
# HOW TO RUN LOCALLY
#   1.  pip install streamlit pandas matplotlib
#   2.  streamlit run social_listening_dashboard.py
#   3.  Upload the Excel file when prompted.
# -----------------------------------------------------

import re
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------- Helper functions ---------- #

def parse_post_date(date_str: str):
    """Convert date like 'Posted 05:59 15 Apr 2025' → datetime."""
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
    """Return dates where value > rolling_mean + sigma*rolling_std."""
    roll_mean = series.rolling(window).mean()
    roll_std = series.rolling(window).std().fillna(0)
    spikes = series[series > roll_mean + sigma * roll_std]
    return spikes


# ---------- Streamlit UI ---------- #

st.set_page_config(page_title="Shadee Social Listening", layout="wide")
st.title("🩺 Shadee.Care – Social Listening Dashboard")

uploaded = st.sidebar.file_uploader("Upload the Excel export (one sheet per search phrase)", type=["xlsx"])

if uploaded is None:
    st.info("⬅️ Upload an Excel file to begin.")
    st.stop()

# Load all sheets into a dict of DataFrames
xls = pd.ExcelFile(uploaded)
raw_dfs = {name: pd.read_excel(uploaded, sheet_name=name, header=2) for name in xls.sheet_names}

# Sidebar phrase selector
phrase = st.sidebar.selectbox("Choose a search phrase / sheet", list(raw_dfs.keys()))
df = raw_dfs[phrase].copy()

# Clean / parse columns
if "Post Date" in df.columns:
    df["Post_dt"] = df["Post Date"].apply(parse_post_date)
else:
    df["Post_dt"] = pd.NaT

if "Post URL" in df.columns:
    df["Subreddit"] = df.apply(lambda r: extract_subreddit(r.get("Post URL")), axis=1)

# --- Metrics row --- #
col1, col2, col3 = st.columns(3)
col1.metric("Posts scraped", len(df))
col2.metric("% Reddit", f"{(df['Platform']=='Reddit').mean()*100:.1f}%")
col3.metric("Timespan", f"{(df['Post_dt'].max() - df['Post_dt'].min()).days} days" if df['Post_dt'].notna().any() else "n/a")

# --- Time‑series chart --- #

if df["Post_dt"].notna().any():
    ts = df.set_index("Post_dt").resample("D").size()
    st.subheader("Post frequency over time")
    st.line_chart(ts)

    # Spike detection
    spikes = detect_spikes(ts)
    if not spikes.empty:
        with st.expander("⚠️ Spikes detected – click to view"):
            st.write(spikes)
else:
    st.warning("No date information found in this sheet.")

# --- Top subreddits / channels --- #

st.subheader("Top communities")
if df["Platform"].str.contains("Reddit").any():
    top_subs = df["Subreddit"].value_counts().head(10)
    st.write("### Reddit")
    st.bar_chart(top_subs)

if df["Platform"].str.contains("Youtube", case=False).any():
    # Extract YouTube channels from URL path segment after /channel/ or /user/
    def yt_channel(url):
        if not isinstance(url, str):
            return None
        m = re.search(r"youtube\.com/(?:channel|user)/([^/?]+)", url)
        return m.group(1) if m else None
    df["YT_channel"] = df.apply(lambda r: yt_channel(r.get("User URL")), axis=1)
    top_channels = df["YT_channel"].value_counts().head(10)
    st.write("### YouTube channels")
    st.bar_chart(top_channels)

# --- Keyword quick‑filter & sample viewer --- #

st.subheader("Quick content sample")
keyword = st.text_input("Filter posts that contain this keyword (case insensitive)")

sample_df = df.copy()
if keyword:
    sample_df = sample_df[sample_df["Post Content"].str.contains(keyword, case=False, na=False)]

st.dataframe(sample_df[["Platform", "Post Date", "Username", "Post Content"]].head(200))

# --- Footer --- #
st.caption("© 2025 Shadee.Care social listening • Prototype dashboard • Built with Streamlit")
