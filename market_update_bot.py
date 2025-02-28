import tweepy
from pycoingecko import CoinGeckoAPI
from datetime import datetime
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# X API credentials (loaded from environment variables for GitHub Actions)
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

# Debugging: Check if credentials are loaded
logger.info("Checking credentials...")
for cred, value in {"API_KEY": API_KEY, "API_SECRET": API_SECRET, "ACCESS_TOKEN": ACCESS_TOKEN, "ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET}.items():
    if not value:
        logger.error(f"{cred} is not set or empty!")
    else:
        logger.info(f"{cred} is loaded successfully.")

# Initialize Tweepy client for X API v2
try:
    client = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
    logger.info("Tweepy client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Tweepy client: {e}")
    raise

# Test authentication with X API
def test_x_auth():
    try:
        user = client.get_me()
        logger.info(f"X API authentication successful. Logged in as: {user.data.username}")
        return True
    except tweepy.TweepyException as e:
        logger.error(f"X API authentication failed: {e} - Response: {e.response.text if e.response else 'No response'}")
        return False

# Initialize CoinGecko API
cg = CoinGeckoAPI()
logger.info("CoinGecko API initialized.")

# List of coins to track (CoinGecko IDs)
COINS = {
    "bitcoin": "BITCOIN",
    "dogecoin": "DOGECOIN",
    "ethereum": "ETHEREUM",
    "pepe": "PEPE",
    "shiba-inu": "SHIBA-INU",
    "solana": "SOLANA"
}

def get_market_data():
    """Fetch real-time price and 24h change from CoinGecko."""
    logger.info("Fetching market data from CoinGecko...")
    try:
        data = cg.get_price(
            ids=",".join(COINS.keys()),
            vs_currencies="usd",
            include_24hr_change=True
        )
        logger.info("Market data fetched successfully.")
        return data
    except Exception as e:
        logger.error(f"Error fetching CoinGecko data: {e}")
        return None

def format_tweet():
    """Format the market update tweet."""
    logger.info("Formatting tweet...")
    market_data = get_market_data()
    if not market_data:
        logger.error("No market data to format.")
        return "Error: Could not fetch market data."

    tweet = "📊 Crypto Market Update:\n"
    for coin_id, coin_name in COINS.items():
        price = market_data[coin_id]["usd"]
        change_24h = market_data[coin_id]["usd_24h_change"]
        
        arrow = "⬆️" if change_24h >= 0 else "⬇️"
        price_str = f"${price:.2f}" if price > 0.001 else f"${price:.5f}"
        
        tweet += f"#{coin_name} {change_24h:.2f}% {arrow}\n{price_str}\n\n"

    tweet = tweet.strip()
    if len(tweet) > 280:
        logger.warning("Tweet exceeds 280 characters, truncating...")
        tweet = tweet[:277] + "..."
    logger.info("Tweet formatted successfully.")
    return tweet

def post_tweet():
    """Post the market update to X."""
    logger.info("Starting tweet posting process...")
    if not test_x_auth():
        logger.error("Skipping tweet due to authentication failure.")
        return
    
    tweet_text = format_tweet()
    logger.info(f"Generated tweet: {tweet_text}")
    try:
        response = client.create_tweet(text=tweet_text)
        logger.info(f"Tweet posted successfully at {datetime.utcnow()}: {response.data['id']}")
    except tweepy.TweepyException as e:
        logger.error(f"Error posting tweet: {e} - Response: {e.response.text if e.response else 'No response'}")
        raise

if __name__ == "__main__":
    logger.info("Starting market update bot...")
    post_tweet()
