import streamlit as st
import praw
import pandas as pd
from datetime import datetime, timedelta
import altair as alt
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import re

# === Reddit API Setup ===
reddit = praw.Reddit(
    client_id=st.secrets["client_id"],
    client_secret=st.secrets["client_secret"],
    user_agent=st.secrets["user_agent"]
)
reddit.read_only = True

# === Helper Functions ===
def is_internal_link(post):
    return (not post.is_self and 'reddit.com' in post.url) or post.is_self

def normalize_keyword(word):
    """Creates variations like plural, hyphenated, spaced"""
    variations = set()
    word = word.lower().strip()
    if not word:
        return variations
    variations.add(word)
    if " " in word:
        variations.add(word.replace(" ", "-"))
        variations.add(word.replace(" ", ""))
    elif "-" in word:
        variations.add(word.replace("-", " "))
        variations.add(word.replace("-", ""))
    else:
        variations.add(word + "s")
        variations.add(word + "es")
    return variations

def match_keyword_variants(text, keywords):
    text = text.lower()
    return any(kw in text for kw in keywords)

def get_reddit_posts(keywords, start_date, end_date, subreddits=None, comment_filter=None):
    posts = []
    normalized_keywords = set()
    for word in keywords:
        normalized_keywords.update(normalize_keyword(word))

    target_subreddits = subreddits if subreddits else ["all"]

    for sub in target_subreddits:
        try:
            search_results = reddit.subreddit(sub).search(" OR ".join([f'"{k}"' for k in keywords]), sort="top", limit=300, time_filter="year")
            for submission in search_results:
                created = datetime.utcfromtimestamp(submission.created_utc)
                if not (start_date <= created <= end_date):
                    continue
                if not is_internal_link(submission):
                    continue

                combined_text = (submission.title or "") + " " + (submission.selftext or "")
                if not match_keyword_variants(combined_text, normalized_keywords):
                    continue

                if comment_filter:
                    operator, value = comment_filter
                    num_comments = submission.num_comments
                    if operator == "=" and not (num_comments == value): continue
                    if operator == ">" and not (num_comments > value): continue
                    if operator == ">=" and not (num_comments >= value): continue
                    if operator == "<" and not (num_comments < value): continue
                    if operator == "<=" and not (num_comments <= value): continue

                posts.append({
                    "Title": submission.title,
                    "Body": submission.selftext if submission.is_self else "",
                    "Score": submission.score,
                    "Upvote Ratio": submission.upvote_ratio,
                    "Comments": submission.num_comments,
                    "Subreddit": submission.subreddit.display_name,
                    "Permalink": f"https://reddit.com{submission.permalink}",
                    "Created": created.date()
                })

                if len(posts) >= 100:
                    break
        except Exception as e:
            st.warning(f"Error fetching posts from r/{sub}: {e}")
    return posts

def generate_wordcloud(titles):
    text = ' '.join(titles)
    text = re.sub(r"http\S+|[^A-Za-z\s]", "", text)  # Clean links and special chars
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)
    return wordcloud

# === Streamlit UI ===
st.set_page_config(page_title="Reddit Topic Explorer", layout="wide")
st.title("🔍 Reddit Topic Explorer")

# === Inputs ===
col1, col2 = st.columns(2)
with col1:
    keyword_input = st.text_input("Enter one or more keywords (comma separated)", help="e.g. engagement ring, wedding ring")
with col2:
    sub_input = st.text_input("Optional: Add up to 5 subreddits (comma separated)", help="e.g. EngagementRings, Moissanite")

keywords = [kw.strip().lower() for kw in keyword_input.split(",") if kw.strip()]
selected_subreddits = [sub.strip() for sub in sub_input.split(",") if sub.strip()]
if len(selected_subreddits) > 5:
    st.error("You can specify a maximum of 5 subreddits.")
    selected_subreddits = selected_subreddits[:5]

# === Date Range Filter ===
st.subheader("📅 Filter by Date Range")
col3, col4 = st.columns(2)
with col3:
    start_date = st.date_input("Start date", datetime.today() - timedelta(days=30))
with col4:
    end_date = st.date_input("End date", datetime.today())

# === Comment Count Filter ===
st.subheader("💬 Filter by Number of Comments")
col5, col6 = st.columns(2)
with col5:
    comment_operator = st.selectbox("Operator", options=["", "=", ">", ">=", "<", "<="])
with col6:
    comment_value = st.number_input("Number of Comments", min_value=0, step=1, value=0)

comment_filter = None
if comment_operator in ["=", ">", ">=", "<", "<="]:
    comment_filter = (comment_operator, comment_value)

# === Fetch and Display ===
if st.button("Fetch Posts") and keywords:
    with st.spinner("Fetching top Reddit posts..."):
        posts_data = get_reddit_posts(
            keywords,
            start_date=datetime.combine(start_date, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.max.time()),
            subreddits=selected_subreddits,
            comment_filter=comment_filter
        )
        if posts_data:
            df = pd.DataFrame(posts_data)

            # === Subreddit Filter ===
            subreddits = df["Subreddit"].unique().tolist()
            selected_subs = st.multiselect("Filter by Subreddit", subreddits, default=subreddits)
            df = df[df["Subreddit"].isin(selected_subs)]

            # === Sorting ===
            sort_by = st.selectbox("Sort by", options=["Score", "Comments"])
            df = df.sort_values(by=sort_by, ascending=False)

            # === Display Data ===
            st.success(f"Found {len(df)} Reddit posts.")
            st.dataframe(df, use_container_width=True)

            # === CSV Download ===
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", data=csv, file_name=f"reddit_posts_{'_'.join(keywords)}.csv", mime='text/csv')

            # === Post Frequency Chart ===
            st.subheader("📊 Post Frequency Over Time")
            chart = (
                alt.Chart(df)
                .mark_bar()
                .encode(
                    x=alt.X("Created:T", title="Date"),
                    y=alt.Y("count()", title="Number of Posts"),
                    tooltip=["Created", "count()"]
                )
                .properties(width="container")
            )
            st.altair_chart(chart, use_container_width=True)

            # === Comment Distribution ===
            st.subheader("💬 Comment Distribution")
            hist = (
                alt.Chart(df)
                .mark_bar()
                .encode(
                    alt.X("Comments:Q", bin=alt.Bin(maxbins=30), title="Number of Comments"),
                    y='count()',
                    tooltip=["count()"]
                )
                .properties(width="container")
            )
            st.altair_chart(hist, use_container_width=True)

            # === Word Cloud ===
            st.subheader("☁️ Word Cloud from Post Titles")
            wordcloud = generate_wordcloud(df["Title"].tolist())
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.imshow(wordcloud, interpolation='bilinear')
            ax.axis("off")
            st.pyplot(fig)
        else:
            st.warning("No posts found. Try different keywords, subreddits, or time frame.")
