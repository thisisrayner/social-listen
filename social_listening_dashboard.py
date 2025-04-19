# Shadee.Care – Social Listening Dashboard (v9 k10 - Fix SyntaxError)
# ---------------------------------------------------------------
# • Implemented session state for fetched data to prevent reload on widget changes.
# • Excel path unchanged (ALL + date + bucket filters).
# • Live Reddit Pull restored: keywords, subreddit, max‑posts, fetch button.
# • Live YouTube Pull added: search phrase, max videos, max comments (using API).
# • Fixed NameError by ensuring df_loaded is defined and not empty before classification.
# • Fixed SyntaxError: 'break' outside loop in YouTube fetch by using a flag.
# • Bucket tagging improved (tight regex); clearer subreddit/channel labeling.
# • Bucket-level trend lines and top sources (Subreddit/Video Title).
# • Upload Excel now extracts **Subreddit** from Post URL when missing.
# • Content sample table now loads 100 rows but initially shows ~20 rows, indexed from 1.
# ---------------------------------------------------------------

import re
import datetime as dt
from pathlib import Path
from typing import Dict, List # Make sure this import is present!

import pandas as pd
import streamlit as st
import praw
import googleapiclient.discovery

# ───────────────────────────────────────────────────────────────
#  Helpers
# ───────────────────────────────────────────────────────────────
DATE_RE = re.compile(r"(\d{1,2}:\d{2})\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")
MON = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun",
      "Jul","Aug","Sep","Oct","Nov","Dec"], 1)} # Typo fixed here


def parse_post_date(txt: str):
    """Parses a specific date/time format from Excel data."""
    if not isinstance(txt, str):
        return pd.NaT
    m = DATE_RE.search(txt)
    if not m:
        return pd.NaT
    time_s, day, mon_s, year = m.groups()
    hh, mm = map(int, time_s.split(':'))
    try:
        return dt.datetime(int(year), MON[mon_s], int(day), hh, mm)
    except ValueError:
        return pd.NaT
    except KeyError: # Handle cases where month abbreviation is not recognized
         return pd.NaT


# Helper to show top sources (generalized for Subreddit or Video Title)
def show_top_sources(df: pd.DataFrame, source_col: str):
    """Displays a bar chart of the top sources (Subreddits or Video Titles)."""
    st.subheader(f"🧠 Top sources ({source_col})")
    # Use df_filtered_buckets here
    if source_col in df.columns and df[source_col].notna().any():
        # Fillna is important in case some entries are missing
        top_sources = df[source_col].fillna("Unknown").value_counts().head(10)
        if not top_sources.empty:
             st.bar_chart(top_sources)
        else:
             st.info(f"No valid data in '{source_col}' column after filtering.")
    else:
        st.info(f"'{source_col}' column not present or empty in the filtered dataset.")


# ───────────────────────────────────────────────────────────────
#  Config
# ───────────────────────────────────────────────────────────────
st.set_page_config("Shadee Live Listening", layout="wide", initial_sidebar_state="expanded")

# Initialize Reddit API client
if "reddit_api" not in st.session_state and "reddit" in st.secrets:
    try:
        creds = st.secrets["reddit"]
        st.session_state.reddit_api = praw.Reddit(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
            user_agent=creds["user_agent"],
            check_for_async=False,
        )
        st.sidebar.markdown(f"🔍 **Reddit client**: `{creds['client_id']}` – anon script scope")
    except Exception as e:
        st.sidebar.error(f"Failed to initialize Reddit API: {e}")


# Initialize YouTube API client
if "youtube_api" not in st.session_state and "youtube" in st.secrets:
    try:
        api_key = st.secrets["youtube"].get("api_key")
        if api_key:
             # Building the service requires specifying version
            st.session_state.youtube_api = googleapiclient.discovery.build(
                "youtube", "v3", developerKey=api_key, cache_discovery=False
            )
            st.sidebar.markdown("📺 **YouTube client**: Initialized (using API Key)")
        else:
             st.sidebar.warning("YouTube API key not found in secrets.")
    except Exception as e:
        st.sidebar.error(f"Failed to initialize YouTube API: {e}")


# Initialize session state for fetched data and current mode
if 'fetched_data' not in st.session_state:
    st.session_state['fetched_data'] = None
if 'current_mode' not in st.session_state:
    st.session_state['current_mode'] = None
if 'uploaded_excel_name' not in st.session_state: # To track which Excel file is loaded
     st.session_state['uploaded_excel_name'] = None
if 'sheet_names' not in st.session_state: # To store sheet names for the selectbox
     st.session_state['sheet_names'] = ["ALL"]


# ───────────────────────────────────────────────────────────────
#  Bucket Logic (remains unchanged)
# ───────────────────────────────────────────────────────────────
BUCKET_PATTERNS: Dict[str, str] = {
    'self_blame': r"\b(hate(?:s|d)? (?:myself|me)|everyone hate(?:s|d)? me|worthless|i (?:don't|do not) deserve to live|i'?m a failure|blame myself|all my fault)\b",
    'cost_concern': r"\b(can'?t afford|too expensive|cost of therapy|insurance won't|no money for help)\b",
    'work_burnout': r"\b(burnt out|burned out|toxic work|overworked|study burnout|no work life balance|exhausted from work)\b",
    'self_harm': r"\b(kill myself|end my life|suicid(?:e|al)|self[- ]?harm|cutting myself|hurting myself)\b",
    'relationship_breakup': r"\b(break[- ]?up|dump(?:ed)?|heart ?broken|lost my (?:partner|girlfriend|boyfriend)|she left me|he left me)\b",
    'friendship_drama': r"\b(friend(?:ship)? (?:ignore(?:d)?|ghost(?:ed)?|lost)|no friends?|friends don't care)\b",
    'crying_distress': r"\b(can'?t stop crying|keep on crying|crying every night|cry myself to sleep)\b",
    'depression_misery': r"\b(i['’]?m (?:so )?(?:depressed|miserable|numb|empty)|i feel dead inside|life is meaningless|hopeless|no reason to live|can't go on|don't want to exist|done with life)\b",
    'loneliness_isolation': r"\b(i['’]?m (?:so )?(?:lonely|alone|isolated)|nobody (?:cares|loves me)|no one to talk to|feel invisible|no support system|abandoned)\b",
    'family_conflict': r"\b(my (?:mom|dad|parents|family) (?:hate me|don't understand|abusive|arguing|don't care)|fight with (?:mom|dad|family)|toxic family|family pressure|neglect)\b",
    'family_loss_or_absence': r"\b(i miss my (?:mom|dad|parent|family)|grew up without (?:a|my) (?:dad|mom)|orphan|parent passed away|lost (?:my )?(?:dad|mom|guardian))\b"
}
COMPILED = {name: re.compile(pat, re.I) for name, pat in BUCKET_PATTERNS.items()}

def tag_bucket(text: str):
    """Classifies text content into predefined buckets based on regex patterns."""
    if not isinstance(text, str):
        return "other"
    for name, pat in COMPILED.items():
        if pat.search(text):
            return name
    return "other"

# ───────────────────────────────────────────────────────────────
#  Sidebar
# ───────────────────────────────────────────────────────────────
st.sidebar.header("📊 Choose Data Source")

# Define mode options
mode_options = ("Upload Excel", "Live Reddit Pull", "Live YouTube Pull")

# Determine initial mode index based on session state
initial_mode_index = 0
if st.session_state['current_mode'] in mode_options:
     initial_mode_index = mode_options.index(st.session_state['current_mode'])


MODE = st.sidebar.radio("Select mode", mode_options, index=initial_mode_index)

# Clear fetched data from state if mode changes
# Use a unique key for the radio to ensure it triggers a rerun consistently if the index changes programmatically
if MODE != st.session_state['current_mode']:
    st.session_state['fetched_data'] = None
    st.session_state['current_mode'] = MODE
    st.session_state['uploaded_excel_name'] = None # Clear excel state too if mode changes
    st.session_state['sheet_names'] = ["ALL"] # Reset sheet names
    st.rerun() # Trigger a rerun to show the correct sidebar controls


end_d = dt.date.today()
start_d = end_d - dt.timedelta(days=30)
start_d, end_d = st.sidebar.date_input("Select Date Range", (start_d, end_d))


# ──────────────────────────────────────────────────────────────
#  Upload Excel Mode
# ──────────────────────────────────────────────────────────────
if MODE == "Upload Excel":
    st.sidebar.header("📁 Excel Settings")
    xl_file = st.sidebar.file_uploader("Drag and drop Excel", type="xlsx")

    # If a new file is uploaded or it's the first load and a file is present, process it
    if xl_file is not None and (st.session_state['fetched_data'] is None or st.session_state['uploaded_excel_name'] != xl_file.name or st.session_state['current_mode'] != "Upload Excel"):
        st.session_state['fetched_data'] = None # Clear any previous data immediately
        st.session_state['uploaded_excel_name'] = xl_file.name
        st.session_state['current_mode'] = "Upload Excel" # Set mode explicitly
        st.session_state['sheet_names'] = ["ALL"] # Reset sheet names placeholder

        with st.spinner("Reading and processing Excel file..."):
            dfs: List[pd.DataFrame] = []
            try:
                with pd.ExcelFile(xl_file) as xl:
                    sheets = xl.sheet_names
                    st.session_state['sheet_names'] = ["ALL"] + sheets # Store actual sheet names

                # Load all sheets for now, filtering will happen later using the selectbox value
                with pd.ExcelFile(xl_file) as xl:
                    for sh in sheets:
                        try:
                            df_s = xl.parse(sh, skiprows=2)
                            if {"Post Date", "Post Content"}.issubset(df_s.columns):
                                # Ensure necessary columns exist with default values if not present
                                if "Platform" not in df_s.columns: df_s["Platform"] = "Excel"
                                if "Subreddit" not in df_s.columns:
                                    if "Post URL" in df_s.columns:
                                        df_s["Subreddit"] = ( df_s["Post URL"].astype(str).str.extract(r"reddit\.com/r/([^/]+)/")[0].fillna("Unknown") )
                                    else:
                                         df_s["Subreddit"] = "Unknown" # Default if URL also missing

                                df_s["Post_dt"] = df_s["Post Date"].map(parse_post_date)
                                # Add original sheet name for filtering later
                                df_s['_OriginalSheet'] = sh
                                dfs.append(df_s)
                            else:
                                st.warning(f"Sheet ‘{sh}’ missing required columns ('Post Date', 'Post Content') → skipped")
                        except Exception as parse_error:
                             st.warning(f"Error parsing sheet ‘{sh}’: {parse_error} → skipped")

            except Exception as e:
                st.error(f"Error reading Excel file: {e}")
                st.session_state['fetched_data'] = None
                st.session_state['uploaded_excel_name'] = None
                st.session_state['sheet_names'] = ["ALL"]
                st.stop()

            if not dfs:
                st.error("No valid sheets or data found in the Excel file.")
                st.session_state['fetched_data'] = None
                st.session_state['uploaded_excel_name'] = None
                st.session_state['sheet_names'] = ["ALL"]
                st.stop()

            df_loaded = pd.concat(dfs, ignore_index=True)

            # Classify content immediately after loading
            if not df_loaded.empty and "Post Content" in df_loaded.columns:
                 with st.spinner("Classifying content..."):
                      df_loaded["Bucket"] = df_loaded["Post Content"].apply(tag_bucket)
            else:
                 st.warning("No content column found or empty DataFrame to classify.")
                 df_loaded["Bucket"] = "other" # Add bucket column even if empty

            # Store the base loaded and classified data in session state
            st.session_state['fetched_data'] = df_loaded.copy()
            # Trigger rerun to apply filters and display
            st.rerun()


    # --- Display Visualizations if data exists in session state for Excel mode ---
    # Data processing and visualization logic runs if data is in state AND mode matches
    if st.session_state['fetched_data'] is not None and st.session_state['current_mode'] == "Upload Excel":

        # Retrieve data from state
        df = st.session_state['fetched_data']

        # Apply sheet selection filter (uses stored sheet names)
        sheet_choice = st.sidebar.selectbox("Sheet", st.session_state['sheet_names'], index=0)
        if sheet_choice.upper() != "ALL" and '_OriginalSheet' in df.columns:
             df_filtered_sheet = df[df['_OriginalSheet'] == sheet_choice].copy()
        else:
             df_filtered_sheet = df.copy() # Use all data if ALL or sheet column missing


        # Apply date filtering (always happens on rerun to df_filtered_sheet)
        df_filtered_date = df_filtered_sheet.dropna(subset=["Post_dt"]).copy() # Ensure valid dates before date filter
        df_filtered_date = df_filtered_date[(df_filtered_date["Post_dt"].dt.date >= start_d) & (df_filtered_date["Post_dt"].dt.date <= end_d)].copy()

        if df_filtered_date.empty:
            st.info("No posts in selected sheet and date window.")
            # Don't clear fetched_data here, as changing date/sheet might find data again
            st.stop()

        # Bucket selection (always happens on rerun to df_filtered_date)
        # Get unique buckets from the date-filtered data to ensure options are relevant
        unique_buckets_in_date_range = sorted(df_filtered_date["Bucket"].unique())
        sel_buckets = st.sidebar.multiselect(
            "Select buckets", unique_buckets_in_date_range, default=unique_buckets_in_date_range
        )
        df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()


        st.success(f"✅ {len(df_filtered_buckets)} posts after filtering")

        # --- Display Visualizations (use df_filtered_buckets unless trend) ---
        st.subheader("📊 Post volume by bucket")
        if not df_filtered_buckets.empty:
            st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
        else:
            st.info("No data to display for selected buckets.")

        st.subheader("📈 Post trend over time")
        if not df_filtered_date.empty: # Trend uses date-filtered data before bucket filter
            trend_df = df_filtered_date
            trend = (
                trend_df.set_index("Post_dt")
                .assign(day=lambda _d: _d.index.date)
                .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
                .fillna(0)
            )
            # Filter trend columns to show only selected buckets, ensure they exist
            cols_to_show = [b for b in sel_buckets if b in trend.columns]
            if cols_to_show:
                st.line_chart(trend[cols_to_show])
            else:
                st.info("No data for selected buckets in trend.")
        else:
             st.info("No data to display trend.")

        # Show top sources (Subreddits for Excel)
        show_top_sources(df_filtered_buckets, source_col="Subreddit") # Use bucket-filtered data for top sources

        st.subheader("📄 Content sample")
        if not df_filtered_buckets.empty:
            # Ensure columns exist before trying to show them
            show_cols = [c for c in ["Post_dt", "Bucket", "Subreddit", "Platform", "Post Content", "_OriginalSheet"] if c in df_filtered_buckets.columns]
            sample = df_filtered_buckets[show_cols].head(100).copy()
            sample.index = range(1, len(sample) + 1)
            st.dataframe(sample, height=600)
        else:
            st.info("No data sample to display.")

    # If no file uploaded or no data in state for Excel, show file uploader message
    elif st.session_state['fetched_data'] is None and xl_file is None:
         st.info("Please upload an Excel file to get started.")
         st.stop() # Stop execution if no data and no file


# ──────────────────────────────────────────────────────────────
#  Live Reddit Pull Mode
# ──────────────────────────────────────────────────────────────
elif MODE == "Live Reddit Pull":
    st.sidebar.header("📡 Reddit Settings")
    reddit = st.session_state.get("reddit_api")
    if reddit is None:
        st.error("Reddit API not configured or failed to initialize. Check secrets.")
        # Clear fetched data if API fails and this was the active mode
        if st.session_state.get('current_mode') == "Live Reddit Pull":
             st.session_state['fetched_data'] = None
        st.stop()

    # Sidebar controls remain the same, their values persist across reruns
    phrase = st.sidebar.text_input(
        "Search phrase (OR‑supported)", st.session_state.get('reddit_phrase', 'lonely OR therapy'),
        help="Use OR between keywords for broad match, e.g. 'lonely OR therapy'",
        key='reddit_phrase_input' # Use a key to maintain value in state
    )
    raw_sub = st.sidebar.text_input(
        "Subreddit (e.g. depression)", st.session_state.get('reddit_subreddit', 'depression'),
        help="Enter one subreddit or multiple separated by '+', e.g. depression+mentalhealth+anxiety. Popular: depression, mentalhealth, anxiety, teenmentalhealth. Boolean OR not supported.",
        key='reddit_subreddit_input' # Use a key
    )
    subreddit = '+'.join([s.strip() for s in raw_sub.split(' OR ')]) if ' OR ' in raw_sub else raw_sub

    max_posts = st.sidebar.slider("Max posts to fetch", 10, 500, st.session_state.get('reddit_max_posts', 100),
                                   key='reddit_max_posts_input') # Use a key


    # The fetch button *always* clears existing state and fetches new data
    if st.sidebar.button("🔍 Fetch live posts"):
        st.session_state['fetched_data'] = None # Clear previous data on button click
        st.session_state['current_mode'] = "Live Reddit Pull" # Ensure mode is set
        # Store current inputs in state triggered by button click, if needed for persistence after rerun
        st.session_state['reddit_phrase'] = phrase
        st.session_state['reddit_subreddit'] = raw_sub # Store raw sub for input display
        st.session_state['reddit_max_posts'] = max_posts


        # Initialize df_loaded *before* potential error paths or no results
        df_loaded = pd.DataFrame()

        with st.spinner(f"Fetching from r/{subreddit} with phrase '{phrase}'..."):
            posts = []
            try:
                results = reddit.subreddit(subreddit).search(phrase, limit=max_posts)
                for p in results:
                    posts.append({
                        "Post_dt": dt.datetime.fromtimestamp(p.created_utc),
                        "Post Content": p.title + "\n\n" + (p.selftext or ""), # Combine title and body
                        "Subreddit": p.subreddit.display_name,
                        "Platform": "reddit",
                        "Post URL": f"https://www.reddit.com{p.permalink}", # Add permalink for context
                    })
                # If fetch was successful and posts were found, create the DataFrame
                if posts:
                     df_loaded = pd.DataFrame(posts).copy() # Use .copy() immediately

            except Exception as e:
                st.error(f"Error fetching from Reddit: {e}")
                st.session_state['fetched_data'] = None # Clear data state on error
                st.stop() # Stop execution on fetch error


        # --- Check data *after* fetching and before classification ---
        if df_loaded.empty: # Check if df_loaded is still empty (either no posts or error before df creation)
            st.warning("No posts returned or DataFrame is empty after fetch.")
            st.session_state['fetched_data'] = None # Ensure state is clear
            st.stop() # Stop processing if no data


        # --- Classification happens here if df_loaded is NOT empty ---
        # Ensure 'Post Content' column exists before applying tag_bucket
        if "Post Content" in df_loaded.columns:
             with st.spinner("Classifying content..."):
                 df_loaded["Bucket"] = df_loaded["Post Content"].apply(tag_bucket)
        else:
             st.warning("No 'Post Content' column found after fetching to classify.")
             df_loaded["Bucket"] = "other" # Add bucket column even if classification fails


        # Store the loaded and classified data in session state
        st.session_state['fetched_data'] = df_loaded.copy()
        st.session_state['current_mode'] = "Live Reddit Pull"

        # Rerun the app to display results
        st.rerun()


    # --- Display Visualizations if data exists in session state for this mode ---
    # Data processing and visualization logic runs if data is in state AND mode matches
    if st.session_state['fetched_data'] is not None and st.session_state['current_mode'] == "Live Reddit Pull":
        # Retrieve data from state
        df = st.session_state['fetched_data']

        # Apply date filtering (always happens on rerun)
        df_filtered_date = df.dropna(subset=["Post_dt"]).copy() # Ensure valid dates
        df_filtered_date = df_filtered_date[(df_filtered_date["Post_dt"].dt.date >= start_d) & (df_filtered_date["Post_dt"].dt.date <= end_d)].copy()

        if df_filtered_date.empty:
            st.info("No posts in selected date window after fetching.")
            # Don't clear fetched_data here, as changing date range might find data again
            st.stop() # Stop displaying if date filter removes all data

        # Bucket selection (always happens on rerun)
        # Get unique buckets from the date-filtered data to ensure options are relevant
        unique_buckets_in_date_range = sorted(df_filtered_date["Bucket"].unique())
        sel_buckets = st.sidebar.multiselect(
            "Select buckets", unique_buckets_in_date_range, default=unique_buckets_in_date_range
        )
        df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()


        st.success(f"✅ {len(df_filtered_buckets)} posts fetched and filtered")

        # --- Display Visualizations (use df_filtered_buckets unless trend) ---
        st.subheader("📊 Post volume by bucket")
        if not df_filtered_buckets.empty:
             st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
        else:
             st.info("No data to display for selected buckets.")

        st.subheader("📈 Post trend over time")
        if not df_filtered_date.empty: # Trend uses date-filtered data before bucket filter
            trend_df = df_filtered_date
            trend = (
                trend_df.set_index("Post_dt")
                .assign(day=lambda _d: _d.index.date)
                .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
                .fillna(0)
            )
            # Filter trend columns to show only selected buckets, ensure they exist
            cols_to_show = [b for b in sel_buckets if b in trend.columns]
            if cols_to_show:
                 st.line_chart(trend[cols_to_show])
            else:
                 st.info("No data for selected buckets in trend.")

        else:
            st.info("No data to display trend.")

        # Show top sources (Subreddits for Reddit)
        show_top_sources(df_filtered_buckets, source_col="Subreddit") # Use bucket-filtered data for top sources

        st.subheader("📄 Content sample")
        if not df_filtered_buckets.empty:
            # Ensure columns exist
            show_cols = [c for c in ["Post_dt", "Bucket", "Subreddit", "Platform", "Post Content", "Post URL"] if c in df_filtered_buckets.columns]
            sample = df_filtered_buckets[show_cols].head(100).copy()
            sample.index = range(1, len(sample) + 1)
            st.dataframe(sample, height=600)
        else:
            st.info("No data sample to display.")

    else:
        # Display initial message if no data is in state for this mode
        st.info("Enter search criteria and click 'Fetch live posts'.")
        # The sidebar controls are already rendered above


# ──────────────────────────────────────────────────────────────
#  Live YouTube Pull Mode
# ──────────────────────────────────────────────────────────────
elif MODE == "Live YouTube Pull":
    st.sidebar.header("▶️ YouTube Settings")
    youtube = st.session_state.get("youtube_api")
    if youtube is None:
        st.error("YouTube API not configured or failed to initialize. Check secrets and API key.")
        # Clear fetched data if API fails and this was the active mode
        if st.session_state.get('current_mode') == "Live YouTube Pull":
             st.session_state['fetched_data'] = None
        st.stop()


    # Sidebar controls remain the same, their values persist across reruns
    yt_phrase = st.sidebar.text_input(
        "Search phrase for videos", st.session_state.get('youtube_phrase', 'youth mental health Singapore'),
        help="Search terms to find relevant YouTube videos.",
        key='youtube_phrase_input' # Use a key
    )
    max_videos_to_search = st.sidebar.slider("Max videos to get comments from", 5, 50, st.session_state.get('youtube_max_videos', 10),
                                             key='youtube_max_videos_input') # Use a key
    max_comments_per_video = st.sidebar.slider("Max comments per video (approx.)", 50, 500, st.session_state.get('youtube_max_comments', 100),
                                              help="Higher values use more quota units.",
                                              key='youtube_max_comments_input') # Use a key

    st.sidebar.markdown("---")
    st.sidebar.info(f"**Quota Note:** Fetching comments uses significant API quota (approx. 50 units per page of comments). You have 10,000 units/day free.")

    # The fetch button *always* clears existing state and fetches new data
    if st.sidebar.button("▶️ Fetch YouTube Comments"):
        st.session_state['fetched_data'] = None # Clear previous data on button click
        st.session_state['current_mode'] = "Live YouTube Pull" # Ensure mode is set
         # Store current inputs in state triggered by button click
        st.session_state['youtube_phrase'] = yt_phrase
        st.session_state['youtube_max_videos'] = max_videos_to_search
        st.session_state['youtube_max_comments'] = max_comments_per_video


        comments_list = []
        video_count = 0
        # Initialize df_loaded *before* potential error paths or no results
        df_loaded = pd.DataFrame()
        quota_hit = False # Flag to signal if quota was hit during processing


        with st.spinner(f"Searching YouTube for videos matching '{yt_phrase}' and fetching comments..."):
            try:
                # 1. Search for relevant videos
                video_search_response = youtube.search().list(
                    q=yt_phrase,
                    part="id,snippet",
                    type="video",
                    maxResults=max_videos_to_search,
                ).execute()

                video_ids = [item['id']['videoId'] for item in video_search_response.get('items', [])]
                if not video_ids:
                    st.warning(f"No videos found for phrase '{yt_phrase}'.")
                    st.session_state['fetched_data'] = None
                    st.stop() # Stop processing if no videos found


                st.info(f"Found {len(video_ids)} videos. Fetching comments (max ~{max_comments_per_video} per video)...")

                # 2. Fetch comments for each video
                for video_id in video_ids:
                    if quota_hit: # Check flag before processing the next video
                         break # Exit the outer video_id loop if quota was hit

                    video_count += 1
                    try:
                        # Get video title for source context
                        video_response = youtube.videos().list( id=video_id, part="snippet" ).execute()
                        video_title = video_response['items'][0]['snippet']['title'] if video_response.get('items') else f"Video ID: {video_id}"
                        video_url = f"https://www.youtube.com/watch?v={video_id}"

                        # Fetch comments using pagination
                        next_page_token = None
                        comments_fetched_count = 0

                        # Use a temporary spinner for each video fetch
                        with st.spinner(f"Fetching comments for video {video_count}/{len(video_ids)}: '{video_title}' ({comments_fetched_count}/{max_comments_per_video} comments fetched)..."):
                            while True: # Loop for comment pagination
                                comments_response = youtube.commentThreads().list(
                                    part="snippet",
                                    videoId=video_id,
                                    textFormat="plainText",
                                    maxResults=100, # API max results per page is 100
                                    pageToken=next_page_token
                                ).execute()

                                for item in comments_response.get('items', []):
                                    comment = item['snippet']['topLevelComment']['snippet']
                                    comments_list.append({
                                        "Post_dt": dt.datetime.strptime(comment['publishedAt'], "%Y-%m-%dT%H:%M:%SZ"),
                                        "Post Content": comment['textDisplay'],
                                        "Platform": "youtube",
                                        "Source": video_title, # Use video title as source
                                        "Video Title": video_title, # Keep video title explicitly
                                        "Video URL": video_url,
                                        "Comment Author": comment.get('authorDisplayName', 'Anonymous'),
                                    })
                                    comments_fetched_count += 1
                                    # Update spinner text using the spinner object
                                    # Check if _spinner exists before updating
                                    if '_spinner' in st.session_state and st.session_state._spinner:
                                        st.session_state._spinner.update(text=f"Fetching comments for video {video_count}/{len(video_ids)}: '{video_title}' ({comments_fetched_count}/{max_comments_per_video} comments fetched)...")


                                    if comments_fetched_count >= max_comments_per_video:
                                        break # Break the inner While True loop for comments if limit reached

                                next_page_token = comments_response.get('nextPageToken')
                                if not next_page_token or comments_fetched_count >= max_comments_per_video:
                                    break # Break the inner While True loop if no more pages or limit reached

                        if comments_fetched_count == 0:
                             st.info(f"No public comments found for video: '{video_title}'")


                    except googleapiclient.errors.GoogleJsonResponseError as e:
                         if e.resp.status in [403, 404]:
                             st.warning(f"Could not fetch comments for video ID {video_id} ('{video_title}'): Comments disabled, video private/deleted, or permission issue.")
                         elif e.resp.status == 429:
                              st.error("YouTube API Quota Exceeded. Please try again tomorrow.")
                              st.session_state['fetched_data'] = None # Clear data state on quota error
                              quota_hit = True # Set the flag
                              break # Break the INNER while True loop for comments
                         else:
                             st.error(f"API error fetching comments for video ID {video_id} ('{video_title}'): {e}")
                    except Exception as e:
                        st.error(f"An unexpected error occurred fetching comments for video ID {video_id} ('{video_title}'): {e}")

            # This exception block catches errors from the video search or the outer for loop logic
            except googleapiclient.errors.GoogleJsonResponseError as e:
                if e.resp.status == 429:
                    st.error("YouTube API Quota Exceeded during video search. Please try again tomorrow.")
                    st.session_state['fetched_data'] = None
                else:
                    st.error(f"API error during video search: {e}")
                # No need for quota_hit = True here as the outer loop logic is handled above
                # and the error is displayed. st.stop() might be considered here, but letting
                # the code flow to the empty check might be fine.
            except Exception as e:
                st.error(f"An unexpected error occurred during video search: {e}")
                st.session_state['fetched_data'] = None
            finally:
                 # Ensure spinner is cleared
                 if '_spinner' in st.session_state and st.session_state._spinner:
                    st.session_state._spinner.empty()


        # --- Check data *after* fetching and before classification ---
        # Create df_loaded only if comments were found
        if comments_list:
            df_loaded = pd.DataFrame(comments_list).copy()
        # Check if df_loaded is still empty (either no comments or error before df creation)
        if df_loaded.empty:
            st.warning("No comments returned or DataFrame is empty after fetch.")
            st.session_state['fetched_data'] = None # Ensure state is clear
            st.stop() # Stop processing if no data


        # --- Classification happens here if df_loaded is NOT empty ---
        # Ensure 'Post Content' column exists before applying tag_bucket
        if "Post Content" in df_loaded.columns:
             with st.spinner("Classifying content..."):
                  df_loaded["Bucket"] = df_loaded["Post Content"].apply(tag_bucket)
        else:
             st.warning("No 'Post Content' column found after fetching to classify.")
             df_loaded["Bucket"] = "other" # Add bucket column even if classification fails


        # Store the loaded and classified data in session state
        st.session_state['fetched_data'] = df_loaded.copy()
        st.session_state['current_mode'] = "Live YouTube Pull"

        # Rerun the app to display results
        st.rerun()


    # --- Display Visualizations if data exists in session state for this mode ---
    # Data processing and visualization logic runs if data is in state AND mode matches
    if st.session_state['fetched_data'] is not None and st.session_state['current_mode'] == "Live YouTube Pull":
        # Retrieve data from state
        df = st.session_state['fetched_data']

        # Apply date filtering (always happens on rerun)
        df_filtered_date = df.dropna(subset=["Post_dt"]).copy() # Ensure valid dates
        df_filtered_date = df_filtered_date[(df_filtered_date["Post_dt"].dt.date >= start_d) & (df_filtered_date["Post_dt"].dt.date <= end_d)].copy()

        if df_filtered_date.empty:
            st.info("No comments in selected date window after fetching.")
            # Don't clear fetched_data here, as changing date range might find data again
            st.stop() # Stop displaying if date filter removes all data

        # Bucket selection (always happens on rerun)
        # Get unique buckets from the date-filtered data to ensure options are relevant
        unique_buckets_in_date_range = sorted(df_filtered_date["Bucket"].unique())
        sel_buckets = st.sidebar.multiselect(
            "Select buckets", unique_buckets_in_date_range, default=unique_buckets_in_date_range
        )
        df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()

        st.success(f"✅ {len(df_filtered_buckets)} comments fetched and filtered")

        # --- Display Visualizations (use df_filtered_buckets unless trend) ---
        st.subheader("📊 Post volume by bucket")
        if not df_filtered_buckets.empty:
             st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
        else:
             st.info("No data to display for selected buckets.")


        st.subheader("📈 Post trend over time")
        if not df_filtered_date.empty: # Trend uses date-filtered data before bucket filter
            trend_df = df_filtered_date
            trend = (
                trend_df.set_index("Post_dt")
                .assign(day=lambda _d: _d.index.date)
                .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
                .fillna(0)
            )
             # Filter trend columns to show only selected buckets, ensure they exist
            cols_to_show = [b for b in sel_buckets if b in trend.columns]
            if cols_to_show:
                 st.line_chart(trend[cols_to_show])
            else:
                 st.info("No data for selected buckets in trend.")
        else:
             st.info("No data to display trend.")

        # Show top sources (Video Titles for YouTube)
        show_top_sources(df_filtered_buckets, source_col="Video Title") # Use bucket-filtered data for top sources

        st.subheader("📄 Content sample")
        if not df_filtered_buckets.empty:
            # Ensure columns exist
            show_cols = [c for c in ["Post_dt", "Bucket", "Source", "Platform", "Post Content", "Video URL", "Comment Author"] if c in df_filtered_buckets.columns]
            sample = df_filtered_buckets[show_cols].head(100).copy()
            sample.index = range(1, len(sample) + 1)
            st.dataframe(sample, height=600)
        else:
            st.info("No data sample to display.")

    else:
        # Display initial message if no data is in state for this mode
        st.info("Enter search criteria and click 'Fetch YouTube Comments'.")
        # The sidebar controls are already rendered above
