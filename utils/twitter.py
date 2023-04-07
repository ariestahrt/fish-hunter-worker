import tweepy, os
from tweepy import API
from dotenv import load_dotenv

load_dotenv()

TWITTER_CONSUMER_KEY=os.getenv("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET=os.getenv("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN=os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_SECRET_TOKEN=os.getenv("TWITTER_SECRET_TOKEN")

def tweet(text, image_path):
    auth = tweepy.OAuth1UserHandler(
        TWITTER_CONSUMER_KEY,
        TWITTER_CONSUMER_SECRET,
        TWITTER_ACCESS_TOKEN,
        TWITTER_SECRET_TOKEN
    )

    client = tweepy.Client(
        consumer_key=TWITTER_CONSUMER_KEY,
        consumer_secret=TWITTER_CONSUMER_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_SECRET_TOKEN
    )

    api = tweepy.API(auth)

    media = api.media_upload(filename=image_path)

    response = client.create_tweet(
        text=text,
        media_ids=[media.media_id_string]
    )
    return response