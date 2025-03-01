import tweepy
from pycoingecko import CoinGeckoAPI
import feedparser
import sys
import os
from datetime import datetime
import pytz
import logging
from html.parser import HTMLParser

# HTML stripper
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_data(self):
        return ''.join(self.text)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# X API credentials
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

# Check credentials
logger.info("Checking credentials...")
for cred, value in {"API_KEY": API_KEY, "API_SECRET": API_SECRET, "ACCESS_TOKEN": ACCESS_TOKEN, "ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET}.items():
    if not value:
        logger.error(f"{cred} is not set or empty!")
    else:
        logger.info(f"{cred} is loaded successfully.")

# Initialize Tweepy Client (v2)
try:
    client = tweepy.Client(consumer_key=API_KEY, consumer_secret=API_SECRET, access_token=ACCESS_TOKEN, access_token_secret=ACCESS_TOKEN_SECRET)
    logger.info("Tweepy client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Tweepy client: {e}")
    raise

# Test X auth
def test_x_auth():
    try:
        user = client.get_me()
        logger.info(f"X API auth successful. Logged in as: {user.data.username}")
        return True
    except tweepy.TweepyException as e:
        logger.error(f"X API auth failed: {e}")
        return False

# Initialize CoinGecko
cg = CoinGeckoAPI()
logger.info("CoinGecko API initialized.")

# Timezone
ist = pytz.timezone('Asia/Kolkata')

# Track news duplicates
posted_headlines = []

# Market Update Function
def get_market_update():
    logger.info("Fetching market update...")
    coins = cg.get_coins_markets(vs_currency='usd', order='market_cap_desc', per_page=10, page=1)
    trending = max(coins, key=lambda x: abs(x['price_change_percentage_24h'] or 0))
    btc = next(c for c in coins if c['symbol'] == 'btc')
    eth = next(c for c in coins if c['symbol'] == 'eth')
    others = [c for c in coins if c['id'] not in [trending['id'], btc['id'], eth['id']]][:2]
    
    tweet = "📊 Market Update:\n"
    arrow = "⬆️" if trending['price_change_percentage_24h'] > 0 else "⬇️"
    tweet += f"🌟 #{trending['symbol'].upper()} (Trending) {trending['price_change_percentage_24h']:.2f}% {arrow} ${trending['current_price']:.2f}\n"
    for coin in [btc, eth] + others:
        arrow = "⬆️" if coin['price_change_percentage_24h'] > 0 else "⬇️"
        tweet += f"#{coin['symbol'].upper()} {coin['price_change_percentage_24h']:.2f}% {arrow} ${coin['current_price']:.2f}\n"
    logger.info(f"Market tweet: {tweet}")
    return tweet.strip()

# News Functions
def get_crypto_news():
    logger.info("Fetching news from CoinTelegraph...")
    feed = feedparser.parse("https://cointelegraph.com/rss")
    for entry in feed.entries:
        headline = entry.title
        if headline not in posted_headlines:
            posted_headlines.append(headline)
            if len(posted_headlines) > 20:
                posted_headlines.pop(0)
            logger.info(f"Selected news: {headline}")
            return {"title": headline, "summary": strip_tags(entry.summary), "published": entry.published}
    logger.info("No new news found.")
    return None

def format_news_tweet(post):
    if not post:
        return None, None
    headline = post['title'][:60]
    summary = post['summary'] if post['summary'] else post['title']  # Cleaned summary
    pub_date = post['published'][:10]  # e.g., "2025-03-01"
    
    # Tweet 1: Main News Summary with spacing
    key_info = summary[:50] if len(summary) > 50 else f"Reported on {pub_date}."
    context = (
        "This move could rally the crypto community and push for "
        "greater regulatory clarity in the sector." if "advocate" in headline.lower()
        else "This development might influence crypto markets and regulatory talks."
    )
    tags = ["#Crypto", "#CryptoNews"]  # SEO base
    for word in headline.split():
        if word.lower() in ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'xrp']:
            tags.append(f"#{word.upper()}")
        elif word.lower() in ['etf', 'regulation', 'partnership', 'futures']:
            tags.append(f"#{word.capitalize()}")
    if "Vitalik" in headline:
        tags.append("#EthereumCommunity")
    tags = tags[:3]  # Limit for space
    
    tweet1 = f"🚨 {headline}! 📈\n\n{key_info}\n\n{context}\n\n{' '.join(tags)}"
    
    # Tweet 2: Deeper reply
    extra_insights = f"CoinTelegraph details: {summary[50:100] if len(summary) > 50 else summary}."
    market_reaction = (
        f"ETH holders and devs are vocal—{summary[100:150] if len(summary) > 100 else 'calls echo widely'}."
        if "Vitalik" in headline else f"Markets await {summary[100:130] if len(summary) > 100 else 'next moves'}."
    )
    future_impact = (
        f"Could spark a push for crypto freedom and impact ETH’s role in policy debates."
        if "advocate" in headline.lower() else "Might set a precedent for future crypto regulations."
    )
    tweet2 = f"{extra_insights}\n{market_reaction}\n{future_impact}"
    
    logger.info(f"News tweet 1: {tweet1}")
    logger.info(f"News tweet 2: {tweet2}")
    return tweet1[:280], tweet2[:280]

# Tweet Function
def tweet_content(content, reply_to=None):
    if not test_x_auth():
        logger.error("Skipping tweet due to auth failure.")
        return None
    try:
        if reply_to:
            tweet = client.create_tweet(text=content, in_reply_to_tweet_id=reply_to)
        else:
            tweet = client.create_tweet(text=content)
        logger.info(f"Tweeted at {datetime.now(ist)}: {tweet.data['id']}")
        return tweet.data['id']
    except tweepy.TweepyException as e:
        logger.error(f"Error tweeting: {e}")
        return None

# Main Logic
if __name__ == "__main__":
    logger.info("Starting bot...")
    cron_time = sys.argv[1] if len(sys.argv) > 1 else "manual"
    logger.info(f"Running for cron: {cron_time}")
    market_times = ["0 8 * * *", "0 15 * * *"]  # 13:30, 20:30 IST
    if cron_time in market_times:
        content = get_market_update()
        tweet_content(content)
    else:
        post = get_crypto_news()
        if post:
            tweet1, tweet2 = format_news_tweet(post)
            if tweet1 and tweet2:
                tweet1_id = tweet_content(tweet1)
                if tweet1_id:
                    tweet_content(tweet2, tweet1_id)
