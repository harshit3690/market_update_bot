import tweepy
from pycoingecko import CoinGeckoAPI
import requests
import sys
import os
import time
from datetime import datetime
import pytz
import logging
import re

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
    for attempt in range(2):
        try:
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
        except Exception as e:
            logger.error(f"Market fetch failed (attempt {attempt + 1}): {e}")
            time.sleep(5)
    logger.error("Market update failed after retries.")
    return "📊 Market Update: Data unavailable—check back soon!"

def get_crypto_news():
    logger.info("Fetching news from CryptoPanic API...")
    url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}&filter=crypto&kind=news&public=true"
    for attempt in range(2):
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
                    return {"title": headline}
            logger.info("No new news found.")
            return None
        except requests.RequestException as e:
            logger.error(f"News fetch failed (attempt {attempt + 1}): {e}")
            time.sleep(5)
    logger.error("News fetch failed after retries.")
    return None

def ai_write_tweet(headline):
    logger.info(f"Generating AI tweet for: {headline}")
    for attempt in range(3):
        try:
            hf_url = "https://api-inference.huggingface.co/models/distilgpt2"
            headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
            prompt = (
                f"Tweet: '🚨 {headline}! 📈\\n\\n[info]. [hook?]\\n\\n#[tag1] #[tag2]'. "
                f"Under 280 chars, bold, engaging, no code."
            )
            payload = {"inputs": prompt, "parameters": {"max_length": 100, "temperature": 0.7}}
            response = requests.post(hf_url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            tweet = response.json()[0]['generated_text'].strip()
            logger.info(f"AI raw output: {tweet}")
            
            # Clean prompt echo
            if tweet.startswith("Tweet:"):
                tweet = tweet.split('\n', 1)[1] if '\n' in tweet else tweet[6:].strip()
            
            # Truncate early
            if len(tweet) > 280:
                tweet = tweet[:280]
            
            # Smarter code check: >2 instances
            code_count = sum(tweet.lower().count(kw) for kw in ['var', 'http', '.js'])
            if code_count > 2:
                logger.warning("AI output has too many code terms; using fallback.")
                return generate_fallback(headline), None
            
            # Split if needed
            if len(tweet) > 280:  # Double-check after cleaning
                sentences = tweet.split('. ')
                tweet1 = ""
                tweet2 = None
                for i, sent in enumerate(sentences):
                    if len(tweet1 + sent + (". " if i < len(sentences) - 1 else "")) <= 230:
                        tweet1 += sent + (". " if i < len(sentences) - 1 else "")
                    else:
                        tweet2 = ". ".join(sentences[i:]).strip()
                        break
                if not tweet2:
                    tweet1 = tweet[:280]
            else:
                tweet1 = tweet
                tweet2 = None
            
            # Extract and apply tags
            tags = get_relevant_tags(tweet1 if tweet2 else headline)
            tweet1_clean = tweet1.split('\n\n')[:-1]  # Remove AI tags
            tweet1 = "\n\n".join(tweet1_clean)
            if len(tweet1 + "\n\n" + " ".join(tags)) <= 280:
                tweet1 += "\n\n" + " ".join(tags)
            if tweet2:
                tweet2_clean = tweet2.split('\n\n')[:-1]
                tweet2 = "\n\n".join(tweet2_clean)
                if len(tweet2 + "\n\n" + " ".join(tags)) <= 280:
                    tweet2 += "\n\n" + " ".join(tags)
            
            return tweet1, tweet2
        except (requests.RequestException, KeyError, IndexError) as e:
            logger.error(f"AI tweet failed (attempt {attempt + 1}): {e}")
            time.sleep(5)
    logger.error("AI tweet generation failed after retries.")
    return generate_fallback(headline), None

def generate_fallback(headline):
    logger.info("Generating fallback tweet...")
    clean_headline = re.sub(r'\s*\([^)]+\)', '', headline).lower()
    words = re.findall(r'\b\w+\b', clean_headline)
    stop_words = {'the', 'and', 'for', 'with', 'will', 'to', 'in', 'of', 'a', 'on', 'is', 'as'}
    terms = [w.capitalize() for w in words if w not in stop_words and len(w) > 2]
    term1 = terms[0] if terms else "Crypto"
    term2 = next((w.capitalize() for w in terms if w.lower() == "price"), terms[1] if len(terms) > 1 else "Price")
    tags = get_relevant_tags(headline)
    return f"🚨 {headline}! 📈\n\n{term1} flips {term2}—bullish or bust?\n\n{' '.join(tags)}"

def get_relevant_tags(text):
    logger.info("Generating relevant tags...")
    words = re.findall(r'\b\w+\b', text.lower())
    stop_words = {'the', 'and', 'for', 'with', 'will', 'to', 'in', 'of', 'a', 'on', 'is', 'as'}
    tags = []
    # Extract ticker from parens
    ticker = re.search(r'\(([^)]+)\)', text)
    if ticker:
        tags.append(ticker.group(1).upper())  # e.g., #XLM
    # Add up to 2 more unique tags
    extra_tags = [word.upper() for word in words if word not in stop_words and len(word) > 2 and (not tags or word.lower() != tags[0].lower())][:2]
    tags.extend(extra_tags)
    if len(tags) < 2:
        tags.extend(["PRICE", "CRYPTO"][len(tags):2])  # Fill with defaults
    return [f"#{tag}" for tag in tags[:2]]  # Limit to 2 tags

def format_news_tweet(post):
    if not post:
        return None, None
    headline = post['title']
    tweet1, tweet2 = ai_write_tweet(headline)
    
    # Readability check
    if len(re.findall(r'\b\w+\b', tweet1)) < 5:
        logger.warning("Tweet 1 too short or unclear; using fallback.")
        tweet1 = generate_fallback(headline)
        tweet2 = None
    
    logger.info(f"News tweet 1: {tweet1}")
    if tweet2:
        logger.info(f"News tweet 2: {tweet2}")
    else:
        logger.info("Tweet 2 skipped—no extra content.")
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
