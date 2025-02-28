import tweepy
from pycoingecko import CoinGeckoAPI
from datetime import datetime
import time

# X API credentials (replace with your own from developer.x.com)
API_KEY = "YOUR_API_KEY"
API_SECRET = "YOUR_API_SECRET"
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
ACCESS_TOKEN_SECRET = "YOUR_ACCESS_TOKEN_SECRET"

# Initialize Tweepy client for X API v2
client = tweepy.Client(
    consumer_key=API_KEY,
    consumer_secret=API_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

# Initialize CoinGecko API
cg = CoinGeckoAPI()

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
    try:
        data = cg.get_price(
            ids=",".join(COINS.keys()),
            vs_currencies="usd",
            include_24hr_change=True
        )
        return data
    except Exception as e:
        print(f"Error fetching CoinGecko data: {e}")
        return None

def format_tweet():
    """Format the market update tweet."""
    market_data = get_market_data()
    if not market_data:
        return "Error: Could not fetch market data."

    tweet = "📊 Crypto Market Update:\n"
    for coin_id, coin_name in COINS.items():
        price = market_data[coin_id]["usd"]
        change_24h = market_data[coin_id]["usd_24h_change"]
        
        # Determine arrow direction based on change
        arrow = "⬆️" if change_24h >= 0 else "⬇️"
        # Format price (handle small values like Pepe/Shiba)
        price_str = f"${price:.2f}" if price > 0.001 else f"${price:.5f}"
        
        tweet += f"#{coin_name} {change_24h:.2f}% {arrow}\n{price_str}\n\n"

    # Add timestamp or footer if desired
    tweet = tweet.strip()
    if len(tweet) > 280:  # X's character limit
        tweet = tweet[:277] + "..."  # Truncate with ellipsis
    return tweet

def post_tweet():
    """Post the market update to X."""
    tweet_text = format_tweet()
    try:
        response = client.create_tweet(text=tweet_text)
        print(f"Tweet posted at {datetime.utcnow()}: {response.data['id']}")
    except tweepy.TweepyException as e:
        print(f"Error posting tweet: {e}")

def main():
    """Main function to run the bot."""
    # Peak hours: 9 AM and 5 PM UTC (adjust as needed)
    peak_hours = [9, 17]  # 24-hour format
    while True:
        now = datetime.utcnow()
        current_hour = now.hour
        
        if current_hour in peak_hours and now.minute == 0:  # Run at start of hour
            post_tweet()
            time.sleep(60)  # Wait 1 minute to avoid duplicate posts
        time.sleep(30)  # Check every 30 seconds

if __name__ == "__main__":
    post_tweet()  # Test run immediately
    # Uncomment to run continuously with scheduling
    # main()
