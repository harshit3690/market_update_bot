import tweepy
from pycoingecko import CoinGeckoAPI
import feedparser
import sys
import os
import time
from datetime import datetime
import pytz
import logging
from html.parser import HTMLParser
from transformers import pipeline

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

# Initialize BART LLM
try:
    llm = pipeline("summarization", model="facebook/bart-large-cnn")
    logger.info("BART LLM initialized.")
except Exception as e:
    logger.error(f"Failed to initialize BART LLM: {e}")
    llm = None

# Timezone
ist = pytz.timezone('Asia/Kolkata')

# Track news duplicates
posted_headlines = []

# Predefined SEO hashtag pool
SEO_TAGS = ["#Crypto", "#CryptoNews", "#CryptoUpdate", "#BullRun", "#BearMarket", "#Scams", "#Exploits", 
            "#BTC", "#ETH", "#XRP", "#SOL", "#Regulation", "#Security", "#Hacks"]

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
    tweet += f"🌟 #{trending['symbol'].upper()} {trending['price_change_percentage_24h']:.2f}% {arrow} ${trending['current_price']:.2f}\n"
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
    headline = post['title']
    summary = post['summary'] if post['summary'] else post['title']
    input_text = f"{headline}. {summary}"
    
    # Use BART if available
    if llm:
        try:
            # Tweet 1: Generate with BART
            tweet1_prompt = (
                f"Summarize this crypto news into a tweet under 280 characters with 3 parts: "
                f"headline (up to 60 chars), key info (up to 70 chars), context (up to 80 chars), "
                f"followed by 3 SEO hashtags from this list: {', '.join(SEO_TAGS)}. "
                f"Use line breaks: {input_text}"
            )
            tweet1_result = llm(tweet1_prompt, max_length=150, min_length=50, do_sample=False)[0]['summary_text']
            tweet1_lines = tweet1_result.split('\n')
            if len(tweet1_lines) >= 4:  # Expecting headline, key info, context, tags
                headline = tweet1_lines[0][:60]
                key_info = tweet1_lines[1][:70]
                context = tweet1_lines[2][:80]
                tags = tweet1_lines[3].strip()
                tweet1 = f"🚨 {headline}! 📈\n\n{key_info}\n\n{context}\n\n{tags}"
            else:
                tweet1 = f"🚨 {headline[:60]}! 📈\n\n{summary[:70]}\n\nMay sway crypto trends.\n\n#Crypto #CryptoNews #Scams"
            
            # Tweet 2: Only if enough unique info
            remaining_summary = summary[len(key_info):].strip()
            if len(remaining_summary) > 100:
                tweet2_prompt = (
                    f"From this crypto news, generate a reply tweet under 280 characters with 3 parts: "
                    f"insights (up to 80 chars), reaction (up to 80 chars), impact (up to 80 chars), "
                    f"followed by 1 hashtag from {', '.join(SEO_TAGS)}: {input_text}"
                )
                tweet2_result = llm(tweet2_prompt, max_length=150, min_length=50, do_sample=False)[0]['summary_text']
                tweet2_lines = tweet2_result.split('\n')
                if len(tweet2_lines) >= 4:
                    insights = tweet2_lines[0][:80]
                    reaction = tweet2_lines[1][:80]
                    impact = tweet2_lines[2][:80]
                    tag = tweet2_lines[3].strip()
                    tweet2 = f"{insights}\n{reaction}\n{impact}\n{tag}"
                else:
                    tweet2 = None
            else:
                tweet2 = None
        except Exception as e:
            logger.error(f"BART processing failed: {e}")
            tweet1 = f"🚨 {headline[:60]}! 📈\n\n{summary[:70]}\n\nMay sway crypto trends.\n\n#Crypto #CryptoNews #Scams"
            tweet2 = None
    else:  # Fallback without BART
        key_info = summary[:70] if len(summary) > 70 else summary
        context = "Signals rising threats." if "scams" in headline.lower() else "May shift policy."
        tags = ["#Crypto", "#CryptoNews", "#Scams"]
        tweet1 = f"🚨 {headline[:60]}! 📈\n\n{key_info}\n\n{context}\n\n{' '.join(tags)}"
        tweet2 = None if len(summary) < 100 else f"{summary[70:130]}\nMarkets eye impact.\nFuture TBD.\n#CryptoUpdate"

    logger.info(f"News tweet 1: {tweet1}")
    if tweet2:
        logger.info(f"News tweet 2: {tweet2}")
    else:
        logger.info("Tweet 2 skipped—insufficient unique info.")
    return tweet1, tweet2

# Tweet Function
def tweet_content(content, reply_to=None):
    if not test_x_auth():
        logger.error("Skipping tweet due to auth failure.")
        return None
    try:
        if reply_to:
            tweet = client.create_tweet(text=content, in_reply_to_tweet_id=reply_to)
            time.sleep(5)
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
            if tweet1:
                tweet1_id = tweet_content(tweet1)
                if tweet2 and tweet1_id:
                    tweet_content(tweet2, tweet1_id)
