import tweepy
from pycoingecko import CoinGeckoAPI
import requests
import sys
import os
import time
from datetime import datetime
import pytz
import logging
from html.parser import HTMLParser
import re

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")

logger.info("Checking credentials...")
for cred, value in {"API_KEY": API_KEY, "API_SECRET": API_SECRET, "ACCESS_TOKEN": ACCESS_TOKEN, 
                    "ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET, "CRYPTOPANIC_API_KEY": CRYPTOPANIC_API_KEY, 
                    "HF_API_TOKEN": HF_API_TOKEN}.items():
    if not value:
        logger.error(f"{cred} is not set or empty!")
    else:
        logger.info(f"{cred} is loaded successfully.")

try:
    client = tweepy.Client(consumer_key=API_KEY, consumer_secret=API_SECRET, 
                           access_token=ACCESS_TOKEN, access_token_secret=ACCESS_TOKEN_SECRET)
    logger.info("Tweepy client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Tweepy client: {e}")
    raise

def test_x_auth():
    try:
        user = client.get_me()
        logger.info(f"X API auth successful. Logged in as: {user.data.username}")
        return True
    except tweepy.TweepyException as e:
        logger.error(f"X API auth failed: {e}")
        return False

cg = CoinGeckoAPI()
logger.info("CoinGecko API initialized.")

ist = pytz.timezone('Asia/Kolkata')
posted_headlines = []

def get_market_update():
    logger.info("Fetching market update...")
    coins = cg.get_coins_markets(vs_currency='usd', order='market_cap_desc', per_page=10, page=1)
    trending = max(coins, key=lambda x: x['price_change_percentage_24h'] or 0)
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

def get_crypto_news():
    logger.info("Fetching news from CryptoPanic API...")
    url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}&filter=crypto"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        posts = response.json().get('results', [])
        for post in posts:
            headline = post['title']
            if headline not in posted_headlines:
                posted_headlines.append(headline)
                if len(posted_headlines) > 20:
                    posted_headlines.pop(0)
                logger.info(f"Selected news: {headline}")
                return {"title": headline, "url": post['url'], "published": post['published_at']}
        logger.info("No new news found.")
        return None
    except requests.RequestException as e:
        logger.error(f"Error fetching CryptoPanic news: {e}")
        return None

def clean_text(text):
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if not any(keyword in line.lower() for keyword in ['@font-face', 'font-family', '.woff', '.eot', '.ttf', 'http'])]
    return ' '.join(cleaned_lines)

def enhance_with_ai(url):
    logger.info(f"Scraping and enhancing URL: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        text = strip_tags(response.text)
        text = clean_text(text)[:1000]
        if not text.strip() or len(text.split()) < 10:
            logger.warning("URL content too short or junk; skipping AI.")
            return ""
        hf_url = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        payload = {"inputs": text}
        hf_response = requests.post(hf_url, headers=headers, json=payload, timeout=10)
        hf_response.raise_for_status()
        summary = hf_response.json()[0]['summary_text']
        if any(keyword in summary.lower() for keyword in ['@font-face', '.eot', 'http']):
            logger.warning("AI summary contains junk; discarding.")
            return ""
        logger.info(f"AI summary: {summary}")
        return summary
    except (requests.RequestException, KeyError, IndexError) as e:
        logger.error(f"Error enhancing with AI: {e}")
        return ""

def get_ai_tags(text):
    logger.info("Generating AI tags...")
    words = re.findall(r'\b\w+\b', text.lower())
    stop_words = {'the', 'and', 'for', 'with', 'will', 'to', 'in', 'of', 'a', 'on', 'is', 'as'}
    tags = [f"#{word.capitalize()}" for word in words if word not in stop_words and len(word) > 2]
    unique_tags = list(dict.fromkeys(tags))[:3]
    if not unique_tags:
        unique_tags = ["#Crypto", "#CryptoNews"]
    logger.info(f"AI tags: {unique_tags}")
    return unique_tags

def find_last_period(text, max_length):
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_period = truncated.rfind('.')
    if last_period > 0:
        return truncated[:last_period + 1]
    return truncated + "..."

def format_news_tweet(post):
    if not post:
        return None, None
    headline = post['title']
    summary = enhance_with_ai(post['url']) if post['url'] else ""
    if summary and headline.lower() in summary.lower()[:len(headline) + 10]:
        summary = summary[len(headline):].strip()
    
    input_text = f"{headline}. {summary}" if summary else headline
    tags = get_ai_tags(input_text)
    
    tweet1_base = f"🚨 {headline}! 📈\n\n"
    info_length = 280 - len(tweet1_base) - len("\n\n" + " ".join(tags)) - 10
    info = find_last_period(summary, min(150, info_length)) if summary else ""
    tweet1 = tweet1_base + info
    if len(tweet1 + "\n\n" + " ".join(tags)) <= 280:
        tweet1 += "\n\n" + " ".join(tags)
    
    tweet2 = None
    if summary and len(summary) > len(info):
        remaining_summary = summary[len(info):].strip()
        if remaining_summary:
            more_info_length = 280 - len("\n\n" + " ".join(tags)) - 10
            more_info = find_last_period(remaining_summary, more_info_length)
            tweet2 = more_info
            if len(tweet2 + "\n\n" + " ".join(tags)) <= 280:
                tweet2 += "\n\n" + " ".join(tags)
    
    logger.info(f"News tweet 1: {tweet1}")
    if tweet2:
        logger.info(f"News tweet 2: {tweet2}")
    else:
        logger.info("Tweet 2 skipped—insufficient unique info.")
    return tweet1, tweet2

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

if __name__ == "__main__":
    logger.info("Starting bot...")
    cron_time = sys.argv[1] if len(sys.argv) > 1 else "manual"
    logger.info(f"Running for cron: {cron_time}")
    market_times = ["0 8 * * *", "0 15 * * *"]
    run_market = "--market" in sys.argv
    if cron_time in market_times or run_market:
        content = get_market_update()
        tweet_content(content)
    else:
        if not cron_time.startswith("0"):
            posted_headlines.clear()
            logger.info("Cleared posted_headlines for news run.")
        post = get_crypto_news()
        if post:
            tweet1, tweet2 = format_news_tweet(post)
            if tweet1:
                tweet1_id = tweet_content(tweet1)
                if tweet2 and tweet1_id:
                    tweet_content(tweet2, tweet1_id)
