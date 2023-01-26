import requests, re, json, os
from urllib.parse import urlparse
from pymongo import MongoClient
from datetime import date, datetime, timedelta
from webpage_saver import save_webpage
from s3uploader import compress_and_upload
from pathlib import Path
from dotenv import load_dotenv

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

def read_file(filename):
	try:
		with open(filename, 'r', encoding="utf8") as f:
			data = f.read()
		return data

	except Exception as ex:
		logging.error("Error opening or reading input file: {}", ex)
		exit()

def get_proxy():
    proxy_list = read_file(os.getenv("PROXY_PATH")).splitlines()
    proxy_random = random.choice(proxy_list)
    
    return {"http": f"http://{proxy_random}", "https": f"http://{proxy_random}"}

def request_with_proxy(url):
    while True:
        try:
            proxy = get_proxy()
            print("> using proxy: ", proxy)
            req = requests.get(url, proxies=proxy, timeout=2)
            return req
        except Exception as ex:
            print("> error: ", ex)
            None

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

def get_urlscan_result(url):
    netloc = urlparse(url).netloc
    endpoint = f"https://urlscan.io/api/v1/search/?q={netloc}"

    req = request_with_proxy(endpoint)
    res = json.loads(req.text)

    try:
        if res["total"] < 1 : return []
    except:
        return []

    # Filter > 5 minggu
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

def save_dataset(uuid, fish_id):
    # Get URL, VERDICT
    while True:
        try:
            req_result = request_with_proxy(f"https://urlscan.io/api/v1/result/{uuid}")
            json_obj = json.loads(req_result.text)

            domain = json_obj["page"]["domain"]
            scam_url = json_obj["page"]["url"]
            categories = json_obj["verdicts"]["overall"]["categories"]
            brands = json_obj["verdicts"]["overall"]["brands"]
            break
        except: None

    logging.info(">>>> Domain {}", domain)
    logging.info(">>>> URL {}", scam_url)
    logging.info(">>>> Brands {}", brands)
    # Prepare json obj to save
    json_dataset = {
        "date_scrapped": datetime.today().replace(microsecond=0),
        "http_status":None,
        "reject_details": "",
        "domain": domain,
        "assets_downloaded":None,
        "content_length":None,
        "url": scam_url,
        "categories": categories,
        "brands": brands,
        "dataset_path": "",
        "htmldom_path": "",
        "scrapped_from": "urlscan.io",
        "urlscan_uuid": uuid
    }

    if "ntagojp" in categories:
        json_dataset["reject_details"] = "Brands blacklisted"
        return False, json_dataset

    if len(brands) < 1:
        logging.error(">>>> Brands invalid")
        json_dataset["reject_details"] = "Not a phishing (by urlscan)"
        return False, json_dataset

    dom_req = request_with_proxy(f"https://urlscan.io/dom/{uuid}/")
    dom_req.encoding = 'utf-8'

    if len(dom_req.text) < 30:
        logging.error("Can't save content because the len is less than 30")
        json_dataset["reject_details"] = "Can't save content because the len is less than 30"
        return False, json_dataset
    
    json_dataset["content_length"] = len(dom_req.text)

    # Clear temp dir
    temp_dir = uuid
    remove_dir(f"datasets/{temp_dir}")
    create_dir("", f"datasets/{temp_dir}")

    # Check is url is alive
    is_alive = False
    try:
        reqx = requests.get(scam_url, allow_redirects=False, verify=False)
        json_dataset["http_status"] = reqx.status_code
        if reqx.status_code < 500:
            is_alive = True
    except Exception as ex: json_dataset["http_status"] = -1
        
    if not is_alive:
        logging.error(">>>> Scampage is {}", "DEAD")
        remove_dir(f"datasets/{temp_dir}")
        json_dataset["reject_details"] = "Can't reach scampage"
        return False, json_dataset

    logging.info(">>>> Scampage is {} [{}]", "ALIVE", reqx.status_code)
    
    json_dataset["assets_downloaded"] = save_webpage(scam_url, html_content=dom_req.text, saved_path=f"datasets/{temp_dir}")

    # Prepare to move temp folder to actualy dataset
    # dataset_brand = "-".join(brands)
    # dataset_index = 1
    # while(os.path.exists(f"datasets/{dataset_brand}-{dataset_index}")):
    #     dataset_index+=1

    # dataset_path = f"datasets/{dataset_brand}-{dataset_index}"
    dataset_path = f"datasets/{fish_id}"
    os.rename(f"datasets/{temp_dir}", dataset_path)
    json_dataset["dataset_path"] = dataset_path
    json_dataset["htmldom_path"] = f"{dataset_path}/index.html"

    # with open("datasets/info.json", "a") as outfile:
    #     json.dump(json_dataset, outfile)
    #     outfile.write("\n")

    logging.info(">>>> Download complete, saved to {}", dataset_path)
    return True, json_dataset

if __name__ == "__main__":
    while True:
        fish = URL_COLLECTIONS.find_one({"status": "queued"})
        print(fish)

        if fish is None:
            logging.info("No fish found, waiting 5 minutes")
            time.sleep(5*60)
            continue
        
        fish_id = fish["_id"]
        url = fish["url"]
        logging.info("FISH {}", fish["url"])

        # Create the jobs
        data = {
            "ref_url": fish_id,
            "http_status": None,
            "save_status": None,
            "details": None,
            "worker": os.getenv("WORKER_NAME"),
            "created_at": datetime.today().replace(microsecond=0),
            "updated_at": datetime.today().replace(microsecond=0)
        }
        job_id = JOBS.insert_one(data).inserted_id

        # Update fish as processed
        URL_COLLECTIONS.update_one({"_id": fish_id}, { "$set": { "status": "processed", "updated": datetime.today().replace(microsecond=0)} })

        urlscan_uuids = get_urlscan_result(url)
        logging.info("FOUND {} scan from urlscan.io", len(urlscan_uuids))
        save_ok = False
        save_result = None

        if len(urlscan_uuids) > 0:
            for uuid in urlscan_uuids:
                logging.info(">> Downloading UUID {}", uuid)
                save_ok, save_result = save_dataset(uuid, fish_id)

                if save_result["reject_details"] == "Brands blacklisted":
                    logging.info(">> Downloading UUID {} : {}", uuid, "STOPPED")
                    break
                
                if save_ok == True:
                    logging.info(">> Downloading UUID {} : {}", uuid, "OK")
                    break
                else:
                    logging.error(">> Downloading UUID {} : {}", uuid, "FAILED")

            if save_ok:
                JOBS.update_one({"_id": job_id}, { "$set": { "http_status": save_result["http_status"], "save_status": "success", "details": "OK", "updated": datetime.today().replace(microsecond=0)} })
                data = {
                    "ref_url": fish_id,
                    "ref_job": job_id,
                    "date_scrapped": save_result["date_scrapped"],
                    "http_status": save_result["http_status"],
                    "domain": save_result["domain"],
                    "assets_downloaded":save_result["assets_downloaded"],
                    "content_length":save_result["content_length"],
                    "url": save_result["url"],
                    "categories": save_result["categories"],
                    "brands": save_result["brands"],
                    "dataset_path": save_result["dataset_path"],
                    "htmldom_path": save_result["htmldom_path"],
                    "scrapped_from": save_result["scrapped_from"],
                    "urlscan_uuid": save_result["urlscan_uuid"],
                    "status": "new",
                    "created_at": datetime.today().replace(microsecond=0),
                    "updated_at": datetime.today().replace(microsecond=0),
                    "deleted_at": None
                }
                
                DATASETS.insert_one(data)

                # Compress and encrypt
                compress_and_upload(save_result["dataset_path"], f"{fish_id}.7z")

            else:
                JOBS.update_one({"_id": job_id}, { "$set": { "http_status": save_result["http_status"], "save_status": "failed", "details": save_result["reject_details"], "updated": datetime.today().replace(microsecond=0)} })

        else:
            JOBS.update_one({"_id": job_id}, { "$set": { "http_status": None, "save_status": "failed", "details": "Domain not found in urlscan.io", "updated": datetime.today().replace(microsecond=0)} })

        # Update fish as executed
        URL_COLLECTIONS.update_one({"_id": fish_id}, { "$set": { "status": "done", "updated": datetime.today().replace(microsecond=0)} })