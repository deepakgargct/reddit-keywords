import streamlit as st
import praw
import pandas as pd
from datetime import datetime, timedelta
import altair as alt
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import re
from textblob import TextBlob

# === Reddit API Setup ===
reddit = praw.Reddit(
    client_id=st.secrets["client_id"],
    client_secret=st.secrets["client_secret"],
    user_agent=st.secrets["user_agent"]
)
reddit.read_only = True

# === Timeframe Mapping ===
time_mapping = {
    "1 Month": 30,
    "3 Months": 90,
    "6 Months": 180,
    "12 Months": 365
}

# === Helper Functions ===
def is_internal_link(post):
    return (not post.is_self and 'reddit.com' in post.url) or post.is_self

def analyze_sentiment(text):
    analysis = TextBlob(text)
    polarity = analysis.sentiment.polarity
    if polarity > 0.05:
        return "Positive"
    elif polarity < -0.05:
        return "Negative"
    else:
        return "Neutral"

def get_reddit_posts(keyword, days, subreddits=None):
    posts = []
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    subreddits = subreddits or ["all"]
    for sub in subreddits:
        query = f'title:"{keyword}"'
        try:
            search_results = reddit.subreddit(sub).search(query, sort="top", limit=200, time_filter="year")
            for submission in search_results:
                created = datetime.utcfromtimestamp(submission.created_utc)
                if start_date <= created <= end_date and is_internal_link(submission):
                    title_lower = submission.title.lower()
                    if keyword.lower() in title_lower:
                        posts.append({
                            "Title": submission.title,
                            "Score": submission.score,
                            "Upvote Ratio": submission.upvote_ratio,
                            "Comments": submission.num_comments,
                            "Subreddit": submission.subreddit.display_name,
                            "Permalink": f"https://reddit.com{submission.permalink}",
                            "Created": created.date(),
                            "Sentiment": analyze_sentiment(submission.title)
                        })
                if len(posts) >= 100:
                    break
        except Exception as e:
            st.warning(f"Error searching r/{sub}: {e}")
    return posts[:100]

def generate_wordcloud(titles):
    text = ' '.join(titles)
    text = re.sub(r"http\S+|[^A-Za-z\s]", "", text)
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)
    return wordcloud

# === Streamlit UI ===
st.set_page_config(page_title="Reddit Topic Explorer", layout="wide")
st.title("🔍 Reddit Topic Explorer")

col1, col2 = st.columns(2)
with col1:
    keyword = st.text_input("Enter a keyword to search Reddit")
with col2:
    timeframe = st.selectbox("Select timeframe", options=list(time_mapping.keys()))

subreddit_input = st.text_input("Optional: Enter up to 5 subreddits (comma-separated, e.g. gaming,technology)")
subreddits = [s.strip() for s in subreddit_input.split(",") if s.strip()]
if len(subreddits) > 5:
    st.warning("Please limit to 5 subreddits.")
    subreddits = subreddits[:5]

if st.button("Fetch Posts") and keyword:
    with st.spinner("Fetching top Reddit posts..."):
        posts_data = get_reddit_posts(keyword, time_mapping[timeframe], subreddits if subreddits else None)
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

            # === Download CSV ===
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", data=csv, file_name=f"{keyword}_reddit_posts.csv", mime='text/csv')

            # === Bar Chart ===
            st.markdown("### 📊 Post Activity Over Time")
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

            # === Sentiment Breakdown ===
            st.markdown("### 😊 Sentiment Analysis")
            sentiment_counts = df["Sentiment"].value_counts().reset_index()
            sentiment_chart = (
                alt.Chart(sentiment_counts)
                .mark_bar()
                .encode(
                    x=alt.X("index:N", title="Sentiment"),
                    y=alt.Y("Sentiment:Q", title="Number of Posts"),
                    tooltip=["index", "Sentiment"]
                )
            )
            st.altair_chart(sentiment_chart, use_container_width=True)

            # === Word Cloud ===
            st.markdown("### ☁️ Word Cloud from Post Titles")
            wordcloud = generate_wordcloud(df["Title"].tolist())
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.imshow(wordcloud, interpolation='bilinear')
            ax.axis("off")
            st.pyplot(fig)
        else:
            st.warning("No posts found. Try a different keyword or timeframe.")
