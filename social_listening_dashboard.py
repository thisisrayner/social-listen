# Shadee.Care – Social Listening Dashboard (v8 – date‑range selector)
# ------------------------------------------------------------------
# New feature: a sidebar **date‑range picker** lets analysts limit the
# visualisation to posts between chosen start & end dates (inclusive).
# ------------------------------------------------------------------

import re
import datetime as dt
from typing import Dict, Tuple

import pandas as pd
import streamlit as st

# ---------- Keyword bucket regexes ---------- #
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

# ---------- Helper functions ---------- #

def parse_post_date(s: str):
    if not isinstance(s, str):
        return None
    m = re.search(r"Posted (\d{2}):(\d{2}) (\d{1,2}) (\w{3}) (\d{4})", s)
    if not m:
        return None
    h, mi, d, mon, y = m.groups()
    try:
        return dt.datetime(int(y), dt.datetime.strptime(mon, "%b").month, int(d), int(h), int(mi))
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
    t = text.lower()
    for b, pat in COMPILED.items():
        if pat.search(t):
            return b
    return "other"

# ---------- Streamlit UI ---------- #

st.set_page_config(page_title="Shadee Social Listening", layout="wide")
st.title("🩺 Shadee.Care – Social Listening Dashboard (v8)")

uploaded = st.sidebar.file_uploader("Upload the Excel scrape (one sheet per search phrase)", type=["xlsx"])
if uploaded is None:
    st.info("⬅️ Upload an Excel file to begin.")
    st.stop()

# --- Load sheets & build combined DF ---

xls = pd.ExcelFile(uploaded)
raw_dfs: Dict[str, pd.DataFrame] = {}
for sheet in xls.sheet_names:
    df_tmp = pd.read_excel(uploaded, sheet_name=sheet, header=2)
    df_tmp["Sheet"] = sheet
    raw_dfs[sheet] = df_tmp
combined_df = pd.concat(raw_dfs.values(), ignore_index=True)
raw_dfs["All (combined)"] = combined_df

options = ["All (combined)"] + xls.sheet_names
phrase = st.sidebar.selectbox("Choose a sheet / search phrase", options, index=0)

df = raw_dfs[phrase].copy()

# ---------- Clean + bucket ---------- #

df["Post_dt"] = df.get("Post Date", pd.Series(dtype=str)).apply(parse_post_date)
if "Post Content" not in df:
    df["Post Content"] = ""
df["Subreddit"] = df.apply(lambda r: extract_subreddit(r.get("Post URL")), axis=1)
df["Bucket"] = df["Post Content"].fillna("*").apply(tag_bucket)

# ---------- Date‑range selector ---------- #
if df["Post_dt"].notna().any():
    min_d = df["Post_dt"].min().date()
    max_d = df["Post_dt"].max().date()
    start_d, end_d = st.sidebar.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    if isinstance(start_d, dt.date):
        # ensure end_d is not None for single‑date pick
        if not isinstance(end_d, dt.date):
            end_d = start_d
        mask = (df["Post_dt"] >= pd.Timestamp(start_d)) & (df["Post_dt"] <= pd.Timestamp(end_d) + pd.Timedelta(days=1))
        df = df[mask]
else:
    st.sidebar.warning("No date info in this sheet")

# ---------- Bucket filter ---------- #
selected_buckets = st.sidebar.multiselect(
    "Filter keyword buckets", options=list(BUCKET_PATTERNS) + ["other"], default=list(BUCKET_PATTERNS)
)
if selected_buckets:
    df = df[df["Bucket"].isin(selected_buckets)]

# ---------- Metrics ---------- #
col1, col2, col3 = st.columns(3)
col1.metric("Posts", len(df))
col2.metric("% Reddit", f"{(df['Platform']=='Reddit').mean()*100:.1f}%")
col3.metric("Timespan", (
    f"{(df['Post_dt'].max() - df['Post_dt'].min()).days} d" if df["Post_dt"].notna().any() else "n/a"
))

st.markdown("**Bucket legend:** " + "  ".join(f"{BUCKET_COLOURS.get(b, '⬜️')} {b}" for b in BUCKET_PATTERNS))

# ---------- Time‑series ---------- #
if df["Post_dt"].notna().any():
    pivot = df.set_index("Post_dt").groupby("Bucket").resample("D").size().unstack(fill_value=0).T
    st.subheader("Daily post volume by bucket")
    st.line_chart(pivot)
    alerts = [
        {"date": d.date(), "bucket": b, "count": int(c)}
        for b in pivot.columns
        for d, c in detect_spikes(pivot[b]).items()
    ]
    if alerts:
        st.subheader("⚠️ Spike alerts")
        st.dataframe(pd.DataFrame(alerts))
else:
    st.warning("No date information after filters.")

# ---------- Top communities ---------- #
st.subheader("Top communities")
if (df["Platform"] == "Reddit").any():
    st.write("### Reddit")
    st.bar_chart(df["Subreddit"].value_counts().head(10))

if df["Platform"].str.contains("Youtube", case=False).any():
    def yt_channel(u):
        if not isinstance(u, str):
            return None
        m = re.search(r"youtube\.com/(?:channel|user)/([^/?]+)", u)
        return m.group(1) if m else None

    df["YT_channel"] = df.apply(lambda r: yt_channel(r.get("User URL")), axis=1)
    st.write("### YouTube channels")
    st.bar_chart(df["YT_channel"].value_counts().head(10))

# ---------- Content sample ---------- #

st.subheader("Quick content sample (click row to copy text)")
kw = st.text_input("Filter posts containing…")
filtered = df if kw == "" else df[df["Post Content"].str.contains(kw, case=False, na=False)]
show_cols = ["Platform", "Post_dt", "Bucket", "Post Content"]
if "Sheet" in df.columns:
    show_cols.insert(0, "Sheet")

st.dataframe(filtered[show_cols].head(250), height=300)

# ---------- Diagnostic: what's in 'other'? ---------- #
if "other" in df["Bucket"].unique():
    with st.expander("🔍 Explore 'other' bucket (top 50 words)"):
        top = (
            df[df["Bucket"] == "other"]["Post Content"]
            .fillna("")
            .str.lower()
            .str.findall(r"[a-z']{4,}")
            .explode()
            .value_counts()
            .head(50)
            .reset_index()
            .rename(columns={"index": "word", 0: "freq"})
        )
        st.dataframe(top, height=300)

st.caption("© 2025 Shadee.Care • Dashboard v8 – date‑range selector")
