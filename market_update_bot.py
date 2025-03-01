import tweepy
from pycoingecko import CoinGeckoAPI
import requests
import schedule
import time
from datetime import datetime
import pytz

# X API Credentials (replace with yours)
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
ACCESS_TOKEN = "your_access_token"
ACCESS_TOKEN_SECRET = "your_access_token_secret"

# CryptoPanic API (free tier, get from cryptopanic.com)
CRYPTOPANIC_API_KEY = "your_cryptopanic_api_key"

# Authenticate X API
auth = tweepy.OAuthHandler(API_KEY, API_SECRET)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)

# Initialize CoinGecko
cg = CoinGeckoAPI()

# Timezone
ist = pytz.timezone('Asia/Kolkata')

# Track news to avoid duplicates
posted_headlines = []

# Market Update Function
def get_market_update():
    coins = cg.get_coins_markets(vs_currency='usd', order='market_cap_desc', per_page=10, page=1)
    # Sort by 24h % change for trending
    trending = max(coins, key=lambda x: abs(x['price_change_percentage_24h'] or 0))
    # Filter BTC, ETH, and 2 others from top 10
    btc = next(c for c in coins if c['symbol'] == 'btc')
    eth = next(c for c in coins if c['symbol'] == 'eth')
    others = [c for c in coins if c['id'] not in [trending['id'], btc['id'], eth['id'])][:2]
    
    tweet = "📊 Market Update:\n"
    arrow = "⬆️" if trending['price_change_percentage_24h'] > 0 else "⬇️"
    tweet += f"🌟 #{trending['symbol'].upper()} (Trending) +{trending['price_change_percentage_24h']:.2f}% {arrow} ${trending['current_price']:.2f}\n"
    for coin in [btc, eth] + others:
        arrow = "⬆️" if coin['price_change_percentage_24h'] > 0 else "⬇️"
        tweet += f"#{coin['symbol'].upper()} +{coin['price_change_percentage_24h']:.2f}% {arrow} ${coin['current_price']:.2f}\n"
    return tweet.strip()

# News Functions
def get_crypto_news():
    url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}&filter=hot"
    response = requests.get(url).json()
    posts = response.get('results', [])
    for post in posts:
        headline = post['title']
        if headline not in posted_headlines:
            posted_headlines.append(headline)
            if len(posted_headlines) > 20:  # Keep last 20 to avoid memory bloat
                posted_headlines.pop(0)
            return post
    return None

def format_news_tweet(post):
    if not post:
        return None, None
    headline = post['title'][:60]  # Shorten if needed
    # Extract coin/event from headline (basic)
    tags = ["#Crypto"]
    for word in headline.split():
        if word.lower() in ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol']:
            tags.append(f"#{word.upper()}")
        elif word.lower() in ['etf', 'regulation', 'partnership']:
            tags.append(f"#{word.capitalize()}")
    tags = tags[:3]  # Max 3 tags
    
    tweet1 = f"🚨 {headline}! 📈 / {post.get('description', '')[:50]} / Impact? / {' '.join(tags)}"
    tweet2 = f"Details: {post.get('description', '')[:100]} / Market reacts TBD / Future TBD"
    return tweet1[:280], tweet2[:280]

# Tweet Function
def tweet_content(content, reply_to=None):
    try:
        if reply_to:
            tweet = api.update_status(status=content, in_reply_to_status_id=reply_to)
        else:
            tweet = api.update_status(status=content)
        print(f"Tweeted at {datetime.now(ist)}: {content}")
        return tweet.id
    except tweepy.TweepyException as e:
        print(f"Error: {e}")
        return None

# Scheduled Jobs
def market_job():
    content = get_market_update()
    tweet_content(content)

def news_job():
    post = get_crypto_news()
    if post:
        tweet1, tweet2 = format_news_tweet(post)
        if tweet1 and tweet2:
            tweet1_id = tweet_content(tweet1)
            if tweet1_id:
                tweet_content(tweet2, tweet1_id)

# Schedule (IST)
schedule.every().day.at("13:30").do(market_job)  # Morning peak
schedule.every().day.at("20:30").do(market_job)  # Afternoon peak
schedule.every().day.at("02:00").do(news_job)    # Non-peak
schedule.every().day.at("07:00").do(news_job)    # Non-peak
schedule.every().day.at("11:30").do(news_job)    # Peak
schedule.every().day.at("13:00").do(news_job)    # Peak
schedule.every().day.at("15:00").do(news_job)    # Peak
schedule.every().day.at("18:30").do(news_job)    # Peak
schedule.every().day.at("20:00").do(news_job)    # Peak
schedule.every().day.at("22:00").do(news_job)    # Peak

# Run
while True:
    schedule.run_pending()
    time.sleep(60)
