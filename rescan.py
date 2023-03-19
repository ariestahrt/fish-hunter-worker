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
from bson import ObjectId

import WebPageClone
from utils.s3 import compress_and_upload, upload_image
from utils.lookup_tools import whoisxmlapi, ipwhois
from FishHunterUtil.features_extractor import get_dataset_features
from FishHunterUtil.selenium_ss import screenshot

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
SOURCES = DB["sources"]
JOBS = DB["jobs"]
DATASETS = DB["datasets"]
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

def remove_dir(directory):
    try:
        directory = Path(directory)
        for item in directory.iterdir():
            if item.is_dir():
                remove_dir(item)
            else:
                item.unlink()
        directory.rmdir()
    except:
        None

def create_dir(parrent_dir, new_dir):
    # Dirname can be more deeper like "static/script/js"
    # Setting the path for folder creation
    path = os.path.join(parrent_dir, new_dir)

    try:
        os.makedirs(path, exist_ok = True)
    except OSError as error:
        logging.error("Failed creating dir {}", path)

def urlscan_search(url):
    netloc = urlparse(url).netloc
    endpoint = f"https://urlscan.io/api/v1/search/?q={netloc}"


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
    
    try:
        if res["total"] < 1 : return []
    except:
        return []

    # Filter > 5 weeks
    min_date = datetime.today() - timedelta(days=5*7)
    filter_res = list(filter(lambda x: x["task"]["time"] >= str(min_date), res["results"]))

    sorted_res = sorted(filter_res, key= lambda x: (x["stats"]["dataLength"], x["task"]["time"]), reverse=True)

    uuids = []
    try:
        for result in sorted_res:
            uuid = result["task"]["uuid"]
            uuids.append(uuid)
    except Exception as ex:
        return []

    return uuids

def urlscan_uuid(uuid):
    while True:
        try:
            response = request_helper(f"https://urlscan.io/api/v1/result/{uuid}")
            urlscan_res = response.json()
            return urlscan_res
        except:
            logger.error("Error getting urlscan uuid: {}", uuid)
            logger.error("Error: {}", response.text)

def save_dataset(uuid, fish_id):
    '''
        Download dataset and save to db

        @param uuid: urlscan uuid
        @param fish_id: fish id

        @return: Exception, Datset Info, URLScan Info
    '''
    urlscan_data = urlscan_uuid(uuid)
    # Prepare json obj to save
    
    dataset_info = {
        "urlscan_uuid": uuid,
        "http_status_code": None,
        "reject_details": "",
        "assets_downloaded": None,
        "content_length": None,
        "dataset_path": "",
        "htmldom_path": ""
    }

    if urlscan_data.get("page") != None:
        logging.info(">>>> Domain {}", urlscan_data["page"]["domain"])
        logging.info(">>>> URL {}", urlscan_data["page"]["url"])
        logging.info(">>>> Brands {}", urlscan_data["verdicts"]["overall"]["brands"])
    else:
        logger.error(">>>> URLScan data not found")
        return Exception("URLScan data not found"), dataset_info, urlscan_data
    
    # check is url already in db
    # if DATASETS.count_documents({"url": urlscan_data["page"]["url"]}) > 0:
    #     logging.error(">>>> URL already in db")
    #     dataset_info["reject_details"] = "URL already in db"
    #     return Exception("URL already in db"), dataset_info, urlscan_data

    # check is categories in blacklist
    for category in urlscan_data["verdicts"]["overall"]["brands"]:
        if category in BLACKLIST:
            dataset_info["reject_details"] = "Categories blacklisted"
            return Exception("Categories blacklisted"), dataset_info, urlscan_data
    
    # check is brands valid
    if len(urlscan_data["verdicts"]["overall"]["brands"]) < 1:
        logging.error(">>>> Brands invalid")
        dataset_info["reject_details"] = "Not a phishing (by urlscan)"
        return Exception("Not phishing"), dataset_info, urlscan_data

    # get dom html
    dom_req = request_helper(f"https://urlscan.io/dom/{uuid}/")
    if dom_req == None:
        return Exception("Error getting dom html"), dataset_info, urlscan_data
    dom_req.encoding = 'utf-8'

    if len(dom_req.text) < int(os.getenv("MIN_CONTENT_LENGTH")):
        logging.error("Page content too short")
        dataset_info["reject_details"] = "Page content too short"
        return Exception("Page content too short"), dataset_info, urlscan_data
    
    dataset_info["content_length"] = len(dom_req.text)

    # Clear temp dir
    temp_dir = uuid
    remove_dir(f"datasets/{temp_dir}")
    create_dir("", f"datasets/{temp_dir}")

    # Check is url is alive
    is_alive = False
    try:
        reqx = requests.get(urlscan_data["page"]["url"], allow_redirects=False, verify=False)
        dataset_info["http_status_code"] = reqx.status_code
        if reqx.status_code < 500:
            is_alive = True
    except Exception as ex: None
        
    # if not is_alive:
    #     logging.error(">>>> Scampage is {}", "DEAD")
    #     remove_dir(f"datasets/{temp_dir}")
    #     dataset_info["reject_details"] = "Can't reach scampage"
        
    #     return Exception("Can't reach scampage"), dataset_info, urlscan_data

    # logging.info(">>>> Scampage is {} [{}]", "ALIVE", reqx.status_code)
    
    dataset_info["assets_downloaded"] = WebPageClone.save_webpage(urlscan_data["page"]["url"], html_content=dom_req.text, saved_path=f"datasets/{temp_dir}")

    # dataset_path = f"datasets/{dataset_brand}-{dataset_index}"
    dataset_path = f"datasets/{fish_id}"
    os.rename(f"datasets/{temp_dir}", dataset_path)
    dataset_info["dataset_path"] = dataset_path
    dataset_info["htmldom_path"] = f"{dataset_path}/index.html"

    logging.info(">>>> Download complete, saved to {}", dataset_path)
    return None, dataset_info, urlscan_data

if __name__ == "__main__":
    ds_id_list = open("ds_id_list.txt", "r").read().splitlines()
    for ds_id in ds_id_list:
        # get fish
        ds = DATASETS.find_one({"_id": ObjectId(ds_id)})
        if ds == None:
            print("Fish not found")
            exit(1)
        
        # get urlscan uuid
        uuid = ds["urlscan_uuid"]
        fish_id = str(ds["ref_url"])

        logging.info(">> Downloading UUID {}", uuid)
        err, dataset_info, urlscan_data = save_dataset(uuid, fish_id)
        
        if err == None:
            logging.info(">> Downloading UUID {} : {}", uuid, "OK")
        else:
            logging.error(">> Downloading UUID {} : {}", uuid, "FAILED")
            logging.error(">> Error: {}", err)
            exit(1)
        
        # extract features
        f_text, f_html, f_css = get_dataset_features(dataset_info["dataset_path"])

        # detect language
        try:
            lang = detect(f_text)
        except Exception as ex:
            lang = None

        # screenshot
        ds_abs_path = os.path.abspath(dataset_info["dataset_path"])

        # index
        screenshot_path_index = dataset_info["dataset_path"]+"/screenshot_index.jpg"
        logger.info("Taking screenshot to {}", screenshot_path_index)
        screenshot("file://"+ds_abs_path+"/index.html", screenshot_path_index)
        
        # upload screenshot to s3
        upload_image(os.getenv('AWS_BUCKET_IMAGES'), local_file=screenshot_path_index, dest=f"screenshot/index/{str(fish_id)}.jpg")
        
        # clean
        screenshot_path_clean = dataset_info["dataset_path"]+"/screenshot_clean.jpg"
        logger.info("Taking screenshot to {}", screenshot_path_clean)
        screenshot("file://"+ds_abs_path+"/clean.html", screenshot_path_clean)
        
        # upload screenshot to s3
        upload_image(os.getenv('AWS_BUCKET_IMAGES'), local_file=screenshot_path_clean, dest=f"screenshot/clean/{str(fish_id)}.jpg")

        # original
        screenshot_path_original = dataset_info["dataset_path"]+"/screenshot_original.jpg"
        logger.info("Taking screenshot to {}", screenshot_path_original)
        screenshot("file://"+ds_abs_path+"/original.html", screenshot_path_original)
        
        # upload screenshot to s3
        upload_image(os.getenv('AWS_BUCKET_IMAGES'), local_file=screenshot_path_original, dest=f"screenshot/original/{str(fish_id)}.jpg")

        # UPDATE DATASET
        DATASETS.update_one({"_id": ObjectId(ds_id)}, {
            "$set": {
                "assets_downloaded": dataset_info["assets_downloaded"],
                "language": lang,
                "features": {
                    "text": f_text,
                    "html": f_html,
                    "css": f_css
                },
                "screenshot": {
                    "index": f"https://fh-ss-images.s3.ap-southeast-1.amazonaws.com/screenshot/index/"+str(fish_id)+".jpg",
                    "original": f"https://fh-ss-images.s3.ap-southeast-1.amazonaws.com/screenshot/original/"+str(fish_id)+".jpg",
                    "clean": f"https://fh-ss-images.s3.ap-southeast-1.amazonaws.com/screenshot/clean/"+str(fish_id)+".jpg"
                },
                "updated_at": datetime.today().replace(microsecond=0)
            }
        })

        # Compress and upload
        compress_and_upload(dataset_info["dataset_path"], f"{fish_id}.7z")

        print("Done")