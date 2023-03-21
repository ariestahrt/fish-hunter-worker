import requests, re, json, os
from urllib.parse import urlparse
from pymongo import MongoClient
from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from langdetect import detect
from bs4 import BeautifulSoup
import logging
import sys
import time, random

import WebPageClone
from utils.s3 import compress_and_upload, upload_image
from utils.lookup_tools import whoisxmlapi, ipwhois
from FishHunterUtil.features_extractor import get_dataset_features
from FishHunterUtil.selenium_ss import screenshot

from colargulog import ColorizedArgsFormatter
from colargulog import BraceFormatStyleFormatter
from worker import save_dataset

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

    file_handler = logging.FileHandler("app.log")
    file_level = "DEBUG"
    file_handler.setLevel(file_level)
    file_format = "%(asctime)s - %(name)s (%(lineno)s) - %(levelname)-8s - %(threadName)-12s - %(message)s"
    file_handler.setFormatter(BraceFormatStyleFormatter(file_format))
    root_logger.addHandler(file_handler)

init_logging()
logger = logging.getLogger(__name__)
load_dotenv()

# CLIENT = MongoClient('localhost', 27017)
# Connect to mongodb atlas
CLIENT = MongoClient(os.getenv("MONGO_CONNECTION_STRING"))
DB = CLIENT['hunter']
URL_COLLECTIONS = DB["urls"]
DATASETS = DB["datasets"]
ALLOW_LIST = DB["allow_list"]
HASH_COLLECTION = DB["uuid_by_hash"]

CURRENT_PROXY = None

def read_file(filename):
	try:
		with open(filename, 'r', errors='ignore') as f:
			data = f.read()
		return data

	except Exception as ex:
		logging.error("Error opening or reading input file: {}", ex)
		exit()

# LOAD BLACKLIST.TXT
BLACKLIST = read_file(os.getenv("BLACKLIST_PATH")).splitlines()

def get_proxy():
    global CURRENT_PROXY
    if CURRENT_PROXY != None: return CURRENT_PROXY

    proxy_list = read_file(os.getenv("PROXY_PATH")).splitlines()
    proxy_random = random.choice(proxy_list)
    
    CURRENT_PROXY = {"http": f"http://{proxy_random}", "https": f"http://{proxy_random}"}
    return CURRENT_PROXY

def request_helper(url):
    global CURRENT_PROXY
    print("REQUEST HELPER:: ", url)
    if os.getenv("IS_PROXY_ENABLED") == "False":
        try:
            req = requests.get(url, timeout=10)
            return req
        except Exception as ex:
            print("> error: ", ex)
            return None

    while True:
        try:
            proxy = get_proxy()
            print("> using proxy: ", proxy)
            req = requests.get(url, proxies=proxy, timeout=3)
            return req
        except Exception as ex:
            print("> error: ", ex)
            CURRENT_PROXY = None

def urlscan_search(hash_id, search_after=None):
    endpoint = f"https://urlscan.io/api/v1/search/?q=hash:{hash_id}"
    if search_after != None:
        endpoint += f"&search_after={search_after}"
    
    req = request_helper(endpoint)
    # save to file
    
    try:
        with open("urlscan.json", "w") as f:
            f.write(req.text)
    except: None

    try:
        res = json.loads(req.text)
    except:
        return []

    uuids = []    
    for result in res["results"]:
        apex_domain = result["page"]["apexDomain"]

        if ALLOW_LIST.find_one({"domain": apex_domain}) == None:
            uuids.append(result["_id"])

            insert_data = {
                "domain": result["page"]["domain"],
                "apex_domain": apex_domain,
                "hash": hash_id,
                "uuid": result["_id"],
                "url": result["page"]["url"],
                "status":"queued",
                "created_at": datetime.now()
            }

            if HASH_COLLECTION.find_one({"$or": [{"uuid": result["_id"]}, {"domain": result["page"]["domain"]}]}) == None:
                HASH_COLLECTION.insert_one(insert_data)
                print("INSERTED: ", json.dumps(insert_data, indent=4, default=str))

    if res["has_more"]:
        print("HAS MORE")
        search_after = str(res["results"][-1]["sort"][0])+","+str(res["results"][-1]["sort"][1])
        uuids += urlscan_search(hash_id, search_after)

    return uuids

if __name__ == "__main__":
    # fish_id = input("Enter fish id: ")
    # fish = DATASETS.find_one({"_id": fish_id})
    # uuid = fish["urlscan_uuid"]
    uuid = "d9d681c3-661f-4f22-8728-9805ce1a7338"
    # get urlscan indicator
    url = f"https://urlscan.io/result/{uuid}/"
    req = request_helper(url)

    if req == None:
        print("Request failed")
        exit()
    
    # get html
    html = req.text

    # parse html
    soup = BeautifulSoup(html, "html.parser")
    indicators_a = soup.find("div", {"id": "indicators"}).find_all("a")
    
    hashs = []
    for ia in indicators_a:
        # print("INDICATOR: ", ia)
        # print("\thref=", ia.get("href"))
        href = ia.get("href")
        
        if href.startswith("/search/#hash:"):
             hashs.append(href.split("/search/#hash:")[1])

    for h in hashs:
        uuids = urlscan_search(h)

        for i in range(len(uuids)):
             print(i, uuids[i])
        exit()