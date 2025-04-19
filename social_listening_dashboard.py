# Shadee.Care – Social Listening Dashboard (v9 k8 - Adding YouTube Comments)
# ---------------------------------------------------------------
# • Excel path unchanged (ALL + date + bucket filters).
# • Live Reddit Pull restored: keywords, subreddit, max‑posts, fetch button.
# • Live YouTube Pull added: search phrase, max videos, max comments (using API).
# • Bucket tagging improved (tight regex); clearer subreddit/channel labeling.
# • Bucket-level trend lines and top sources (Subreddit/Video Title).
# • Upload Excel now extracts **Subreddit** from Post URL when missing.
# • Content sample table now loads 100 rows but initially shows ~20 rows, indexed from 1.
# ---------------------------------------------------------------

import re
import datetime as dt
from pathlib import Path # This one was in the original code, let's make sure it's there too
from typing import Dict, List # <--- ADD THIS LINE

import pandas as pd
import streamlit as st
import praw
import googleapiclient.discovery # Added for YouTube API


# ───────────────────────────────────────────────────────────────
#  Helpers
# ───────────────────────────────────────────────────────────────
DATE_RE = re.compile(r"(\d{1,2}:\d{2})\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")
MON = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun",
     "Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

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
def show_top_sources(df: pd.DataFrame, source_col: str = "Subreddit"):
    """Displays a bar chart of the top sources (Subreddits or Video Titles)."""
    st.subheader(f"🧠 Top sources ({source_col})")
    if source_col in df.columns and df[source_col].notna().any():
        # Fillna is important in case some entries are missing
        top_sources = df[source_col].fillna("Unknown").value_counts().head(10)
        if not top_sources.empty:
             st.bar_chart(top_sources)
        else:
             st.info(f"No valid data in '{source_col}' column.")
    else:
        st.info(f"'{source_col}' column not present or empty in this dataset.")


# ───────────────────────────────────────────────────────────────
#  Config
# ───────────────────────────────────────────────────────────────
st.set_page_config("Shadee Live Listening", layout="wide", initial_sidebar_state="expanded")

# Initialize Reddit API client
# ... (Reddit API initialization remains the same) ...

# Initialize YouTube API client
# ... (YouTube API initialization remains the same) ...

# Initialize session state for fetched data
if 'fetched_data' not in st.session_state:
    st.session_state['fetched_data'] = None
if 'current_mode' not in st.session_state:
    st.session_state['current_mode'] = None # To know which data source is in state


# ───────────────────────────────────────────────────────────────
#  Bucket Logic (remains unchanged)
# ... (BUCKET_PATTERNS, COMPILED, tag_bucket remain the same) ...


# ───────────────────────────────────────────────────────────────
#  Sidebar
# ───────────────────────────────────────────────────────────────
st.sidebar.header("📊 Choose Data Source")
# Set initial mode based on session state if data exists, otherwise default to Excel
initial_mode_index = 0
if st.session_state['fetched_data'] is not None:
     # Find the index of the current mode in the radio options
     mode_options = ("Upload Excel", "Live Reddit Pull", "Live YouTube Pull")
     try:
          initial_mode_index = mode_options.index(st.session_state['current_mode'])
     except ValueError:
          # Fallback if current_mode is somehow invalid
          initial_mode_index = 0


MODE = st.sidebar.radio("Select mode", ("Upload Excel", "Live Reddit Pull", "Live YouTube Pull"), index=initial_mode_index)

# Clear fetched data from state if mode changes
if MODE != st.session_state['current_mode']:
    st.session_state['fetched_data'] = None
    st.session_state['current_mode'] = MODE
    # This will cause a rerun, resetting the main content


end_d = dt.date.today()
start_d = end_d - dt.timedelta(days=30)
start_d, end_d = st.sidebar.date_input("Select Date Range", (start_d, end_d))


# ──────────────────────────────────────────────────────────────
#  Upload Excel Mode (Logic slightly adjusted to match new flow)
# ──────────────────────────────────────────────────────────────
if MODE == "Upload Excel":
    st.sidebar.header("📁 Excel Settings")
    xl_file = st.sidebar.file_uploader("Drag and drop Excel", type="xlsx")
    # When a new file is uploaded, clear previous fetched data
    if xl_file is not None:
         # Add a state variable to track the current file, clear data if different file uploaded
         if 'uploaded_excel_name' not in st.session_state or st.session_state['uploaded_excel_name'] != xl_file.name:
              st.session_state['fetched_data'] = None
              st.session_state['uploaded_excel_name'] = xl_file.name

    # If no file is currently processed and no data is in state for Excel mode, stop
    if st.session_state['fetched_data'] is None:
        if xl_file is None:
             st.stop() # Stop if no file and no data loaded yet


    # If data is not in session state for Excel mode, process the file
    if st.session_state['fetched_data'] is None or st.session_state['current_mode'] != "Upload Excel":
        # Process Excel file (same logic as before)
        with st.spinner("Reading and processing Excel file..."):
            dfs: List[pd.DataFrame] = []
            try:
                with pd.ExcelFile(xl_file) as xl:
                    sheets = xl.sheet_names
                sheet_choice = st.sidebar.selectbox("Sheet", ["ALL"] + sheets, index=0)

                # IMPORTANT: To avoid re-parsing on every bucket select,
                # store the loaded data *before* date/bucket filtering in session state
                # and re-select sheet only if file or sheet choice changes.
                # However, for simplicity matching the original code flow triggered by file/sheet,
                # we'll keep the parsing here, but cache it if possible (Streamlit handles some caching).
                # A more robust approach might store parsed sheets in session state.
                # For now, let's just make sure the final df is stored after all base processing.

                with pd.ExcelFile(xl_file) as xl:
                    for sh in (sheets if sheet_choice.upper() == "ALL" else [sheet_choice]):
                        try:
                            df_s = xl.parse(sh, skiprows=2)
                            if {"Post Date", "Post Content"}.issubset(df_s.columns):
                                if "Platform" not in df_s.columns: df_s["Platform"] = "Excel"
                                if "Subreddit" not in df_s.columns and "Post URL" in df_s.columns:
                                    #st.info(f"Extracting Subreddit from Post URL for sheet '{sh}'...") # Optional info
                                    df_s["Subreddit"] = ( df_s["Post URL"].astype(str).str.extract(r"reddit\.com/r/([^/]+)/")[0].fillna("Unknown") )
                                elif "Subreddit" not in df_s.columns:
                                     df_s["Subreddit"] = "Unknown"

                                df_s["Post_dt"] = df_s["Post Date"].map(parse_post_date)
                                dfs.append(df_s)
                            else:
                                st.warning(f"Sheet ‘{sh}’ missing required columns ('Post Date', 'Post Content') → skipped")
                        except Exception as parse_error:
                             st.warning(f"Error parsing sheet ‘{sh}’: {parse_error} → skipped")

            except Exception as e:
                st.error(f"Error reading Excel file: {e}")
                st.stop()

            if not dfs:
                st.error("No valid sheets or data found in the Excel file.")
                st.stop()

            df_loaded = pd.concat(dfs, ignore_index=True)

            # Classify content immediately after loading
            df_loaded["Bucket"] = df_loaded["Post Content"].apply(tag_bucket)

            # Store the base loaded and classified data in session state BEFORE date filtering
            st.session_state['fetched_data'] = df_loaded.copy()
            st.session_state['current_mode'] = "Upload Excel"


    # --- Data is now in st.session_state['fetched_data'] ---
    # Retrieve data from state
    df = st.session_state['fetched_data']

    # Apply date filtering (always happens on rerun)
    df_filtered_date = df.dropna(subset=["Post_dt"]).copy() # Ensure valid dates before date filter
    df_filtered_date = df_filtered_date[(df_filtered_date["Post_dt"].dt.date >= start_d) & (df_filtered_date["Post_dt"].dt.date <= end_d)].copy()

    if df_filtered_date.empty:
        st.info("No posts in selected date window.")
        st.session_state['fetched_data'] = None # Clear data if date filter results in empty
        st.stop()

    # Bucket selection (always happens on rerun)
    sel_buckets = st.sidebar.multiselect(
        "Select buckets", sorted(df_filtered_date["Bucket"].unique()), default=sorted(df_filtered_date["Bucket"].unique())
    )
    df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()


    st.success(f"✅ {len(df_filtered_buckets)} posts after filtering")

    # --- Display Visualizations (use df_filtered_buckets) ---
    st.subheader("📊 Post volume by bucket")
    if not df_filtered_buckets.empty:
        st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
    else:
        st.info("No data to display for selected buckets.")

    st.subheader("📈 Post trend over time")
    if not df_filtered_buckets.empty:
        # Use the date-filtered data (df_filtered_date) for trend before bucket filtering
        trend_df = df_filtered_date
        trend = (
            trend_df.set_index("Post_dt")
              .assign(day=lambda _d: _d.index.date)
              .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
              .fillna(0)
        )
        # Filter trend columns to show only selected buckets
        # Ensure sel_buckets exist as columns in trend before selecting
        cols_to_show = [b for b in sel_buckets if b in trend.columns]
        st.line_chart(trend[cols_to_show])
    else:
         st.info("No data to display trend.")

    # Show top sources (Subreddits for Excel)
    show_top_sources(df_filtered_buckets, source_col="Subreddit")

    st.subheader("📄 Content sample")
    if not df_filtered_buckets.empty:
        # Ensure columns exist before trying to show them
        show_cols = [c for c in ["Post_dt", "Bucket", "Subreddit", "Platform", "Post Content"] if c in df_filtered_buckets.columns]
        sample = df_filtered_buckets[show_cols].head(100).copy()
        sample.index = range(1, len(sample) + 1)
        st.dataframe(sample, height=600)
    else:
        st.info("No data sample to display.")


# ──────────────────────────────────────────────────────────────
#  Live Reddit Pull Mode (Logic adjusted to use session state)
# ──────────────────────────────────────────────────────────────
elif MODE == "Live Reddit Pull":
    st.sidebar.header("📡 Reddit Settings")
    reddit = st.session_state.get("reddit_api")
    if reddit is None:
        st.error("Reddit API not configured or failed to initialize. Check secrets.")
        # Clear fetched data if API fails
        if st.session_state['current_mode'] == "Live Reddit Pull":
             st.session_state['fetched_data'] = None
        st.stop()

    # Sidebar controls remain the same, but their values persist across reruns
    phrase = st.sidebar.text_input(
        "Search phrase (OR‑supported)", "lonely OR therapy",
        help="Use OR between keywords for broad match, e.g. 'lonely OR therapy'"
    )
    raw_sub = st.sidebar.text_input(
        "Subreddit (e.g. depression)", "depression",
        help="Enter one subreddit or multiple separated by '+', e.g. depression+mentalhealth+anxiety. Popular: depression, mentalhealth, anxiety, teenmentalhealth. Boolean OR not supported."
    )
    subreddit = '+'.join([s.strip() for s in raw_sub.split(' OR ')]) if ' OR ' in raw_sub else raw_sub

    max_posts = st.sidebar.slider("Max posts to fetch", 10, 500, 100)

    # The fetch button *always* clears existing state and fetches new data
    if st.sidebar.button("🔍 Fetch live posts"):
        st.session_state['fetched_data'] = None # Clear previous data on button click
        st.session_state['current_mode'] = "Live Reddit Pull" # Ensure mode is set

        with st.spinner(f"Fetching from r/{subreddit} with phrase '{phrase}'..."):
            posts = []
            try:
                results = reddit.subreddit(subreddit).search(phrase, limit=max_posts)
                for p in results:
                    posts.append({
                        "Post_dt": dt.datetime.fromtimestamp(p.created_utc),
                        "Post Content": p.title + "\n\n" + (p.selftext or ""),
                        "Subreddit": p.subreddit.display_name,
                        "Platform": "reddit",
                        "Post URL": f"https://www.reddit.com{p.permalink}",
                    })
            except Exception as e:
                st.error(f"Error fetching from Reddit: {e}")
                st.session_state['fetched_data'] = None # Clear data state on error
                st.stop()

        if not posts:
            st.warning("No posts returned for the given criteria.")
            st.session_state['fetched_data'] = None # Clear data state if empty
            st.stop()

        df_loaded = pd.DataFrame(posts)

        with st.spinner("Classifying content..."):
            df_loaded["Bucket"] = df_loaded["Post Content"].apply(tag_bucket)

        # Store the loaded and classified data in session state BEFORE date filtering
        st.session_state['fetched_data'] = df_loaded.copy()

        # Rerun the app to display results using the data from session state
        st.rerun()


    # --- Display Visualizations if data exists in session state for this mode ---
    if st.session_state['fetched_data'] is not None and st.session_state['current_mode'] == "Live Reddit Pull":
        # Retrieve data from state
        df = st.session_state['fetched_data']

        # Apply date filtering (always happens on rerun)
        df_filtered_date = df.dropna(subset=["Post_dt"]).copy() # Ensure valid dates
        df_filtered_date = df_filtered_date[(df_filtered_date["Post_dt"].dt.date >= start_d) & (df_filtered_date["Post_dt"].dt.date <= end_d)].copy()

        if df_filtered_date.empty:
            st.info("No posts in selected date window after fetching.")
            st.session_state['fetched_data'] = None # Clear data if date filter results in empty
            st.stop() # Stop displaying if date filter removes all data

        # Bucket selection (always happens on rerun)
        sel_buckets = st.sidebar.multiselect(
            "Select buckets", sorted(df_filtered_date["Bucket"].unique()), default=sorted(df_filtered_date["Bucket"].unique())
        )
        df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()


        st.success(f"✅ {len(df_filtered_buckets)} posts fetched and filtered")

        # --- Display Visualizations (use df_filtered_buckets) ---
        st.subheader("📊 Post volume by bucket")
        if not df_filtered_buckets.empty:
             st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
        else:
             st.info("No data to display for selected buckets.")

        st.subheader("📈 Post trend over time")
        if not df_filtered_buckets.empty:
            # Use the date-filtered data (df_filtered_date) for trend before bucket filtering
            trend_df = df_filtered_date
            trend = (
                trend_df.set_index("Post_dt")
                .assign(day=lambda _d: _d.index.date)
                .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
                .fillna(0)
            )
            # Filter trend columns to show only selected buckets
            cols_to_show = [b for b in sel_buckets if b in trend.columns]
            st.line_chart(trend[cols_to_show])
        else:
            st.info("No data to display trend.")

        # Show top sources (Subreddits for Reddit)
        show_top_sources(df_filtered_buckets, source_col="Subreddit")

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
        # Display initial fetch controls if no data is in state for this mode
        pass # Controls are already rendered above the button


# ──────────────────────────────────────────────────────────────
#  Live YouTube Pull Mode (Logic adjusted to use session state)
# ──────────────────────────────────────────────────────────────
elif MODE == "Live YouTube Pull":
    st.sidebar.header("▶️ YouTube Settings")
    youtube = st.session_state.get("youtube_api")
    if youtube is None:
        st.error("YouTube API not configured or failed to initialize. Check secrets and API key.")
         # Clear fetched data if API fails
        if st.session_state['current_mode'] == "Live YouTube Pull":
             st.session_state['fetched_data'] = None
        st.stop()


    # Sidebar controls remain the same
    yt_phrase = st.sidebar.text_input(
        "Search phrase for videos", "youth mental health Singapore",
        help="Search terms to find relevant YouTube videos."
    )
    max_videos_to_search = st.sidebar.slider("Max videos to get comments from", 5, 50, 10)
    max_comments_per_video = st.sidebar.slider("Max comments per video (approx.)", 50, 500, 100, help="Higher values use more quota units.")

    st.sidebar.markdown("---")
    st.sidebar.info(f"**Quota Note:** Fetching comments uses significant API quota (approx. 50 units per page of comments). You have 10,000 units/day free.")

    # The fetch button *always* clears existing state and fetches new data
    if st.sidebar.button("▶️ Fetch YouTube Comments"):
        st.session_state['fetched_data'] = None # Clear previous data on button click
        st.session_state['current_mode'] = "Live YouTube Pull" # Ensure mode is set

        comments_list = []
        video_count = 0

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
                    st.session_state['fetched_data'] = None # Clear data state if empty
                    st.stop()

                st.info(f"Found {len(video_ids)} videos. Fetching comments (max ~{max_comments_per_video} per video)...")

                # 2. Fetch comments for each video
                for video_id in video_ids:
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
                        with st.spinner(f"Fetching comments for video {video_count}/{len(video_ids)}: '{video_title}' ({comments_fetched_count}/{max_comments_per_video})..."):
                            while True:
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
                                    # Update spinner text
                                    st.session_state._spinner.update(text=f"Fetching comments for video {video_count}/{len(video_ids)}: '{video_title}' ({comments_fetched_count}/{max_comments_per_video})...")

                                    if comments_fetched_count >= max_comments_per_video:
                                        break

                                next_page_token = comments_response.get('nextPageToken')
                                if not next_page_token or comments_fetched_count >= max_comments_per_video:
                                    break

                        if comments_fetched_count == 0:
                             st.info(f"No public comments found for video: '{video_title}'")


                    except googleapiclient.errors.GoogleJsonResponseError as e:
                         if e.resp.status in [403, 404]:
                             st.warning(f"Could not fetch comments for video ID {video_id} ('{video_title}'): Comments disabled, video private/deleted, or permission issue.")
                         elif e.resp.status == 429:
                              st.error("YouTube API Quota Exceeded. Please try again tomorrow.")
                              st.session_state['fetched_data'] = None # Clear data state on quota error
                              break # Stop processing further videos if quota hit
                         else:
                             st.error(f"API error fetching comments for video ID {video_id} ('{video_title}'): {e}")
                    except Exception as e:
                        st.error(f"An unexpected error occurred fetching comments for video ID {video_id} ('{video_title}'): {e}")

                    if st.session_state['fetched_data'] is None and st.session_state['current_mode'] == "Live YouTube Pull":
                         break # Stop outer loop if quota was hit


            except googleapiclient.errors.GoogleJsonResponseError as e:
                if e.resp.status == 429:
                    st.error("YouTube API Quota Exceeded during video search. Please try again tomorrow.")
                else:
                    st.error(f"API error during video search: {e}")
                st.session_state['fetched_data'] = None # Clear data state on error
            except Exception as e:
                st.error(f"An unexpected error occurred during video search: {e}")
                st.session_state['fetched_data'] = None # Clear data state on error

            # Ensure spinner is cleared outside the inner loops
            # st.spinner context manager should handle this, but explicit check is good
            if st.session_state._spinner:
                st.session_state._spinner.empty() # Clear spinner explicitly


        if not comments_list:
            st.warning("No comments returned for the given criteria.")
            st.session_state['fetched_data'] = None # Clear data state if empty
            st.stop()

        df_loaded = pd.DataFrame(comments_list)

        with st.spinner("Classifying content..."):
            df_loaded["Bucket"] = df_loaded["Post Content"].apply(tag_bucket)

        # Store the loaded and classified data in session state BEFORE date filtering
        st.session_state['fetched_data'] = df_loaded.copy()

        # Rerun the app to display results using the data from session state
        st.rerun()


    # --- Display Visualizations if data exists in session state for this mode ---
    if st.session_state['fetched_data'] is not None and st.session_state['current_mode'] == "Live YouTube Pull":
        # Retrieve data from state
        df = st.session_state['fetched_data']

        # Apply date filtering (always happens on rerun)
        df_filtered_date = df.dropna(subset=["Post_dt"]).copy() # Ensure valid dates
        df_filtered_date = df_filtered_date[(df_filtered_date["Post_dt"].dt.date >= start_d) & (df_filtered_date["Post_dt"].dt.date <= end_d)].copy()

        if df_filtered_date.empty:
            st.info("No comments in selected date window after fetching.")
            st.session_state['fetched_data'] = None # Clear data if date filter results in empty
            st.stop() # Stop displaying if date filter removes all data

        # Bucket selection (always happens on rerun)
        sel_buckets = st.sidebar.multiselect(
            "Select buckets", sorted(df_filtered_date["Bucket"].unique()), default=sorted(df_filtered_date["Bucket"].unique())
        )
        df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()

        st.success(f"✅ {len(df_filtered_buckets)} comments fetched and filtered")

        # --- Display Visualizations (use df_filtered_buckets) ---
        st.subheader("📊 Post volume by bucket")
        if not df_filtered_buckets.empty:
             st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
        else:
             st.info("No data to display for selected buckets.")

        st.subheader("📈 Post trend over time")
        if not df_filtered_buckets.empty:
            # Use the date-filtered data (df_filtered_date) for trend before bucket filtering
            trend_df = df_filtered_date
            trend = (
                trend_df.set_index("Post_dt")
                .assign(day=lambda _d: _d.index.date)
                .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
                .fillna(0)
            )
             # Filter trend columns to show only selected buckets
            cols_to_show = [b for b in sel_buckets if b in trend.columns]
            st.line_chart(trend[cols_to_show])
        else:
             st.info("No data to display trend.")

        # Show top sources (Video Titles for YouTube)
        show_top_sources(df_filtered_buckets, source_col="Video Title")

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
         # Display initial fetch controls if no data is in state for this mode
         pass # Controls are already rendered above the button
