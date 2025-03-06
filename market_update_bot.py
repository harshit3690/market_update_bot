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
for cred, value in {"API_KEY": API_KEY, "API_SECRET": API_SECRET, "ACCESS_TOKEN": ACCESS_TOKEN, 
                    "ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET}.items():
    if not value:
        logger.error(f"{cred} is not set or empty!")
    else:
        logger.info(f"{cred} is loaded successfully.")

# Initialize Tweepy Client (v2)
try:
    client = tweepy.Client(consumer_key=API_KEY, consumer_secret=API_SECRET, 
                           access_token=ACCESS_TOKEN, access_token_secret=ACCESS_TOKEN_SECRET)
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

# Predefined SEO hashtag pool
SEO_TAGS = ["#Crypto", "#CryptoNews", "#CryptoUpdate", "#BullRun", "#BearMarket", "#Scams", "#Exploits", 
            "#BTC", "#ETH", "#XRP", "#SOL", "#Regulation", "#Security", "#Hacks", "#CongressCrypto", 
            "#CryptoRegulation", "#DeFi"]

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
    logger.info("Fetching news from Reuters Crypto RSS...")
    feed = feedparser.parse("https://www.reuters.com/technology/cryptocurrency/rss.xml")
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
    summary = post['summary'] if post['summary'] else ""
    input_text = f"{headline}. {summary}" if summary else headline
    
    # Smart slicing for Tweet 1
    tweet1_parts = [f"🚨 {headline}! 📈"]
    tags = []
    for tag in SEO_TAGS:
        if tag[1:].lower() in input_text.lower() and len(tags) < 3:
            tags.append(tag)
    if not tags:
        tags = ["#Crypto", "#CryptoNews", "#BTC" if "bitcoin" in headline.lower() else "#DeFi"]
    
    if summary:
        key_info = summary[:60]
        if len(key_info) == 60 and key_info[-1] not in '.!?':
            last_space = key_info.rfind(' ')
            key_info = key_info[:last_space] + "..." if last_space > 0 else key_info
        tweet1_parts.append(key_info)
        
        remaining_summary = summary[len(key_info):].strip()
        if len(remaining_summary) > 20 and remaining_summary not in key_info:  # Useful context check
            context = remaining_summary[:60]
            if len(context) == 60 and context[-1] not in '.!?':
                last_space = context.rfind(' ')
                context = context[:last_space] + "..." if last_space > 0 else context
            tweet1_parts.append(context)
    
    tweet1 = "\n\n".join(tweet1_parts) + "\n\n" + " ".join(tags)
    if len(tweet1) > 280:  # Trim headline if over limit
        excess = len(tweet1) - 280
        headline_cut = headline[:-(excess + 5)] + "..."  # Leave room for ellipsis
        tweet1 = f"🚨 {headline_cut}! 📈\n\n" + "\n\n".join(tweet1_parts[1:]) + "\n\n" + " ".join(tags[:2])  # Drop 1 tag
    
    # Tweet 2: Optional
    tweet2 = None
    if summary and len(remaining_summary) > 80:
        insights = remaining_summary[60:120]
        if len(insights) == 60 and insights[-1] not in '.!?':
            last_space = insights.rfind(' ')
            insights = insights[:last_space] + "..." if last_space > 0 else insights
        tweet2 = f"{insights}\nMarkets watch closely.\nFuture TBD.\n#CryptoUpdate"
        if len(tweet2) > 280:  # Rare, but trim if needed
            tweet2 = f"{insights[:50]}...\nMarkets watch.\nFuture TBD.\n#CryptoUpdate"
    
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
    run_market = "--market" in sys.argv
    if cron_time in market_times or run_market:
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
