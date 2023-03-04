import requests, re, json, os
from urllib.parse import urlparse
from pymongo import MongoClient
from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from langdetect import detect
import logging
import sys
import time, random

from colargulog import ColorizedArgsFormatter
from colargulog import BraceFormatStyleFormatter

def init_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    logging.getLogger("requests").propagate = False

    console_level = "INFO"
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(console_level)
    console_format = "%(asctime)s :: %(levelname)-4s :: %(message)s"
    colored_formatter = ColorizedArgsFormatter(console_format)
    console_handler.setFormatter(colored_formatter)
    root_logger.addHandler(console_handler)

init_logging()
logger = logging.getLogger(__name__)
load_dotenv()

def get_urls_from_openphish():
    url = "https://openphish.com/"
    response = requests.get(url)

    if response.status_code != 200:
        return Exception('API Error'), None
    
    urls = re.findall(r'(?m)class="url_entry">(.*?)</td>', response.text)
    return urls

if __name__ == "__main__":
    urls = get_urls_from_openphish()
    CLIENT = MongoClient(os.getenv("MONGO_CONNECTION_STRING"))
    DB = CLIENT['hunter']
    URL_COLLECTIONS = DB["urls"]

    # insert to db if not exists
    for url in urls:
        if URL_COLLECTIONS.find_one({"url": url}) is None:
            URL_COLLECTIONS.insert_one({
                "url": url,
                "status": "queued",
                "source_url": "https://openphish.com/",
                "source_name": "OpenPhish",
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "deleted_at": None,
            })
            logger.info(f"Inserted {url} to DB")