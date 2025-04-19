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
MODE = st.sidebar.radio("Select mode", ("Upload Excel", "Live Reddit Pull", "Live YouTube Pull"), index=0)
end_d = dt.date.today()
start_d = end_d - dt.timedelta(days=30)
# Date picker is shown for all modes, but filtering is applied later based on mode
start_d, end_d = st.sidebar.date_input("Select Date Range", (start_d, end_d))


# ──────────────────────────────────────────────────────────────
#  Upload Excel Mode
# ──────────────────────────────────────────────────────────────
if MODE == "Upload Excel":
    st.sidebar.header("📁 Excel Settings")
    xl_file = st.sidebar.file_uploader("Drag and drop Excel", type="xlsx")
    if xl_file is None:
        st.stop()

    with st.spinner("Reading Excel file..."):
        dfs: List[pd.DataFrame] = []
        try:
            with pd.ExcelFile(xl_file) as xl:
                sheets = xl.sheet_names
            sheet_choice = st.sidebar.selectbox("Sheet", ["ALL"] + sheets, index=0)

            with pd.ExcelFile(xl_file) as xl:
                for sh in (sheets if sheet_choice.upper() == "ALL" else [sheet_choice]):
                    try:
                        # Read sheet, skipping potential header/intro rows
                        df_s = xl.parse(sh, skiprows=2)
                        # Ensure required columns exist before processing
                        if {"Post Date", "Post Content"}.issubset(df_s.columns):
                            # Add Platform column if missing (assume Excel is 'other')
                            if "Platform" not in df_s.columns:
                                df_s["Platform"] = "Excel"
                            # Ensure Subreddit column exists, extract from URL if needed
                            if "Subreddit" not in df_s.columns and "Post URL" in df_s.columns:
                                st.info(f"Extracting Subreddit from Post URL for sheet '{sh}'...")
                                df_s["Subreddit"] = (
                                    df_s["Post URL"].astype(str)
                                      .str.extract(r"reddit\.com/r/([^/]+)/")[0]
                                      .fillna("Unknown")
                                )
                            elif "Subreddit" not in df_s.columns:
                                # Add a placeholder if Subreddit column is completely missing
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

    df = pd.concat(dfs, ignore_index=True)

    with st.spinner("Classifying content..."):
         df["Bucket"] = df["Post Content"].apply(tag_bucket)

    # Apply date filtering
    df = df.dropna(subset=["Post_dt"]).copy() # Ensure valid dates
    df_filtered_date = df[(df["Post_dt"].dt.date >= start_d) & (df["Post_dt"].dt.date <= end_d)].copy()

    if df_filtered_date.empty:
        st.info("No posts in selected date window.")
        st.stop()

    sel_buckets = st.sidebar.multiselect(
        "Select buckets", sorted(df_filtered_date["Bucket"].unique()), default=sorted(df_filtered_date["Bucket"].unique())
    )
    df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()


    st.success(f"✅ {len(df_filtered_buckets)} posts after filtering")

    # --- Display Visualizations ---
    st.subheader("📊 Post volume by bucket")
    if not df_filtered_buckets.empty:
        st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
    else:
        st.info("No data to display for selected buckets.")


    st.subheader("📈 Post trend over time")
    if not df_filtered_buckets.empty:
        # Use the date-filtered data before bucket filtering for trend to show context
        # But color the trend by selected buckets
        trend_df = df_filtered_date # Use df_filtered_date to show trend over entire date range
        trend = (
            trend_df.set_index("Post_dt")
              .assign(day=lambda _d: _d.index.date)
              .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
              .fillna(0)
        )
        # Filter trend columns to show only selected buckets
        trend_selected = trend[sel_buckets]
        st.line_chart(trend_selected)
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
#  Live Reddit Pull Mode
# ──────────────────────────────────────────────────────────────
elif MODE == "Live Reddit Pull":
    st.sidebar.header("📡 Reddit Settings")
    reddit = st.session_state.get("reddit_api")
    if reddit is None:
        st.error("Reddit API not configured or failed to initialize. Check secrets.")
        st.stop()

    phrase = st.sidebar.text_input(
        "Search phrase (OR‑supported)", "lonely OR therapy",
        help="Use OR between keywords for broad match, e.g. 'lonely OR therapy'"
    )
    raw_sub = st.sidebar.text_input(
        "Subreddit (e.g. depression)", "depression",
        help="Enter one subreddit or multiple separated by '+', e.g. depression+mentalhealth+anxiety. Popular: depression, mentalhealth, anxiety, teenmentalhealth. Boolean OR not supported."
    )
    if ' OR ' in raw_sub:
        st.sidebar.warning("Boolean OR not supported for subreddits; converting to '+'")
        subreddit = '+'.join([s.strip() for s in raw_sub.split(' OR ')])
    else:
        subreddit = raw_sub

    max_posts = st.sidebar.slider("Max posts to fetch", 10, 500, 100) # Increased max slightly

    if st.sidebar.button("🔍 Fetch live posts"):
        with st.spinner(f"Fetching from r/{subreddit} with phrase '{phrase}'..."):
            posts = []
            try:
                # Reddit search via PRAW doesn't have easy date filtering in this context
                # Fetch posts and then filter by date if needed later
                results = reddit.subreddit(subreddit).search(phrase, limit=max_posts)
                for p in results:
                     # Use p.selftext or p.body for comments, p.title for submissions
                     # This search gets submissions, so selftext is correct
                    posts.append({
                        "Post_dt": dt.datetime.fromtimestamp(p.created_utc),
                        "Post Content": p.title + "\n\n" + (p.selftext or ""), # Combine title and body
                        "Subreddit": p.subreddit.display_name,
                        "Platform": "reddit",
                        "Post URL": f"https://www.reddit.com{p.permalink}", # Add permalink for context
                        # Add other relevant fields if desired, e.g., score, num_comments
                    })

            except Exception as e:
                st.error(f"Error fetching from Reddit: {e}")
                st.stop()


        if not posts:
            st.warning("No posts returned for the given criteria.")
            st.stop()

        df = pd.DataFrame(posts)

        with st.spinner("Classifying content..."):
            df["Bucket"] = df["Post Content"].apply(tag_bucket)

        # Apply date filtering based on sidebar selection
        df = df.dropna(subset=["Post_dt"]).copy() # Ensure valid dates
        df_filtered_date = df[(df["Post_dt"].dt.date >= start_d) & (df["Post_dt"].dt.date <= end_d)].copy()

        if df_filtered_date.empty:
            st.info("No posts in selected date window after fetching.")
            st.stop()

        # Allow bucket filtering after fetch and date filter
        sel_buckets = st.sidebar.multiselect(
            "Select buckets", sorted(df_filtered_date["Bucket"].unique()), default=sorted(df_filtered_date["Bucket"].unique())
        )
        df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()


        st.success(f"✅ {len(df_filtered_buckets)} posts fetched and filtered")

        # --- Display Visualizations ---
        st.subheader("📊 Post volume by bucket")
        if not df_filtered_buckets.empty:
             st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
        else:
             st.info("No data to display for selected buckets.")

        st.subheader("📈 Post trend over time")
        if not df_filtered_buckets.empty:
            # Use the date-filtered data before bucket filtering for trend
            trend_df = df_filtered_date
            trend = (
                trend_df.set_index("Post_dt")
                .assign(day=lambda _d: _d.index.date)
                .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
                .fillna(0)
            )
            # Filter trend columns to show only selected buckets
            trend_selected = trend[sel_buckets]
            st.line_chart(trend_selected)
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


# ──────────────────────────────────────────────────────────────
#  Live YouTube Pull Mode (NEW)
# ──────────────────────────────────────────────────────────────
elif MODE == "Live YouTube Pull":
    st.sidebar.header("▶️ YouTube Settings")
    youtube = st.session_state.get("youtube_api")
    if youtube is None:
        st.error("YouTube API not configured or failed to initialize. Check secrets and API key.")
        st.stop()

    yt_phrase = st.sidebar.text_input(
        "Search phrase for videos", "youth mental health Singapore",
        help="Search terms to find relevant YouTube videos."
    )
    max_videos_to_search = st.sidebar.slider("Max videos to get comments from", 5, 50, 10) # Limit videos
    max_comments_per_video = st.sidebar.slider("Max comments per video (approx.)", 50, 500, 100, help="Higher values use more quota units.")


    st.sidebar.markdown("---")
    st.sidebar.info(f"**Quota Note:** Fetching comments uses significant API quota (approx. 50 units per page of comments). You have 10,000 units/day free.")


    if st.sidebar.button("▶️ Fetch YouTube Comments"):
        comments_list = []
        video_count = 0

        with st.spinner(f"Searching YouTube for videos matching '{yt_phrase}'..."):
            try:
                # 1. Search for relevant videos
                video_search_response = youtube.search().list(
                    q=yt_phrase,
                    part="id,snippet",
                    type="video",
                    maxResults=max_videos_to_search,
                    # You could add other filters here like regionCode='SG' if needed,
                    # but relevance often works well for mental health topics globally/regionally
                ).execute()

                video_ids = [item['id']['videoId'] for item in video_search_response.get('items', [])]
                if not video_ids:
                    st.warning(f"No videos found for phrase '{yt_phrase}'.")
                    st.stop()

                st.info(f"Found {len(video_ids)} videos. Fetching comments (max ~{max_comments_per_video} per video)...")

                # 2. Fetch comments for each video
                for video_id in video_ids:
                    video_count += 1
                    try:
                        # Get video title for source context
                        video_response = youtube.videos().list(
                            id=video_id,
                            part="snippet"
                        ).execute()
                        video_title = video_response['items'][0]['snippet']['title'] if video_response.get('items') else f"Video ID: {video_id}"
                        video_url = f"https://www.youtube.com/watch?v={video_id}"

                        # Fetch comments using pagination
                        next_page_token = None
                        comments_fetched_count = 0

                        with st.spinner(f"Fetching comments for video {video_count}/{len(video_ids)}: '{video_title}'..."):
                            while True:
                                comments_response = youtube.commentThreads().list(
                                    part="snippet",
                                    videoId=video_id,
                                    # order="relevance", # Or "time"
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
                                        "Comment Author": comment.get('authorDisplayName', 'Anonymous'), # Add author (consider anonymization)
                                        # Add other comment data if needed, e.g., likeCount
                                    })
                                    comments_fetched_count += 1
                                    if comments_fetched_count >= max_comments_per_video:
                                        break # Stop fetching comments for this video if limit reached

                                next_page_token = comments_response.get('nextPageToken')
                                if not next_page_token or comments_fetched_count >= max_comments_per_video:
                                    break # Stop pagination if no more pages or comment limit reached

                        if comments_fetched_count == 0:
                             st.info(f"No public comments found for video: '{video_title}'")


                    except googleapiclient.errors.GoogleJsonResponseError as e:
                         if e.resp.status in [403, 404]:
                             st.warning(f"Could not fetch comments for video ID {video_id} ('{video_title}'): Comments disabled, video private/deleted, or permission issue.")
                         elif e.resp.status == 429:
                              st.error("YouTube API Quota Exceeded. Please try again tomorrow.")
                              break # Stop processing further videos if quota hit
                         else:
                             st.error(f"API error fetching comments for video ID {video_id} ('{video_title}'): {e}")
                             # Decide whether to continue or stop on other errors
                    except Exception as e:
                        st.error(f"An unexpected error occurred fetching comments for video ID {video_id} ('{video_title}'): {e}")
                        # Decide whether to continue or stop on other errors


            except googleapiclient.errors.GoogleJsonResponseError as e:
                if e.resp.status == 429:
                    st.error("YouTube API Quota Exceeded during video search. Please try again tomorrow.")
                else:
                    st.error(f"API error during video search: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred during video search: {e}")
            finally:
                 # Clear the spinner here or handle it better within loops
                 pass # Spinner managed inside the loops

        if not comments_list:
            st.warning("No comments returned for the given criteria.")
            st.stop()

        df = pd.DataFrame(comments_list)

        with st.spinner("Classifying content..."):
            df["Bucket"] = df["Post Content"].apply(tag_bucket)

        # Apply date filtering based on sidebar selection
        df = df.dropna(subset=["Post_dt"]).copy() # Ensure valid dates
        df_filtered_date = df[(df["Post_dt"].dt.date >= start_d) & (df["Post_dt"].dt.date <= end_d)].copy()

        if df_filtered_date.empty:
            st.info("No comments in selected date window after fetching.")
            st.stop()

        # Allow bucket filtering after fetch and date filter
        sel_buckets = st.sidebar.multiselect(
            "Select buckets", sorted(df_filtered_date["Bucket"].unique()), default=sorted(df_filtered_date["Bucket"].unique())
        )
        df_filtered_buckets = df_filtered_date[df_filtered_date["Bucket"].isin(sel_buckets)].copy()


        st.success(f"✅ {len(df_filtered_buckets)} comments fetched and filtered")

        # --- Display Visualizations ---
        st.subheader("📊 Post volume by bucket")
        if not df_filtered_buckets.empty:
             st.bar_chart(df_filtered_buckets["Bucket"].value_counts())
        else:
             st.info("No data to display for selected buckets.")


        st.subheader("📈 Post trend over time")
        if not df_filtered_buckets.empty:
             # Use the date-filtered data before bucket filtering for trend
            trend_df = df_filtered_date
            trend = (
                trend_df.set_index("Post_dt")
                .assign(day=lambda _d: _d.index.date)
                .pivot_table(index="day", columns="Bucket", values="Post Content", aggfunc="count")
                .fillna(0)
            )
            # Filter trend columns to show only selected buckets
            trend_selected = trend[sel_buckets]
            st.line_chart(trend_selected)
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
