import streamlit as st
import pandas as pd
import praw
import re
from textblob import TextBlob
import altair as alt

# Initialize PRAW
reddit = praw.Reddit(
    client_id=st.secrets["REDDIT_CLIENT_ID"],
    client_secret=st.secrets["REDDIT_CLIENT_SECRET"],
    user_agent="reddit-scraper-app"
)

def clean_text(text):
    text = re.sub(r'http\S+', '', text)
    return text.strip()

def analyze_sentiment(text):
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    if polarity > 0.1:
        return "Positive"
    elif polarity < -0.1:
        return "Negative"
    else:
        return "Neutral"

def get_reddit_posts(keyword, time_filter="month", subreddits=None):
    posts = []
    search_subreddits = subreddits if subreddits else ["all"]
    for sub in search_subreddits:
        subreddit = reddit.subreddit(sub)
        for submission in subreddit.search(keyword, sort="top", limit=200, time_filter=time_filter):
            if not submission.is_self:
                continue  # Skip external links
            posts.append({
                "Title": submission.title,
                "Subreddit": submission.subreddit.display_name,
                "Score": submission.score,
                "Comments": submission.num_comments,
                "Created": pd.to_datetime(submission.created_utc, unit='s'),
                "Text": clean_text(submission.selftext),
                "Link": f"https://reddit.com{submission.permalink}"
            })
    return pd.DataFrame(posts)

# Streamlit UI
st.title("Reddit Keyword Scraper with Sentiment Analysis")

keyword = st.text_input("Enter a keyword to search:")
timeframe = st.selectbox("Select a time frame:", ["1 Month", "3 Months", "6 Months", "12 Months"])
subreddits_input = st.text_input("Optional: Enter up to 5 subreddits (comma-separated)")

# Map timeframe to praw-compatible strings
time_mapping = {
    "1 Month": "month",
    "3 Months": "year",
    "6 Months": "year",
    "12 Months": "year"
}

if st.button("Scrape Reddit Posts") and keyword:
    selected_subreddits = [s.strip() for s in subreddits_input.split(',') if s.strip()][:5] if subreddits_input else None
    with st.spinner("Scraping Reddit..."):
        df = get_reddit_posts(keyword, time_mapping[timeframe], selected_subreddits)

    if df.empty:
        st.warning("No posts found. Try different keywords or subreddits.")
    else:
        df["Sentiment"] = df["Title"].apply(analyze_sentiment)

        st.subheader("Top Posts")
        st.dataframe(df.sort_values(by="Score", ascending=False).reset_index(drop=True))

        st.subheader("Sentiment Analysis")
        sentiment_counts = df["Sentiment"].value_counts().reset_index()
        sentiment_counts.columns = ["Sentiment", "Count"]

        sentiment_chart = (
            alt.Chart(sentiment_counts)
            .mark_bar()
            .encode(
                x=alt.X("Sentiment:N", title="Sentiment"),
                y=alt.Y("Count:Q", title="Number of Posts"),
                tooltip=["Sentiment", "Count"]
            )
            .properties(width="container")
        )
        st.altair_chart(sentiment_chart, use_container_width=True)

        st.download_button("Download CSV", df.to_csv(index=False), "reddit_posts.csv", "text/csv")
