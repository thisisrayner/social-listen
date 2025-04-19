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
COMPILED = {name: re.compile(pat, re.I) for name, pat in BUCKET_PATTERNS.items()}
