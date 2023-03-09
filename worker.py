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

from utils.webpage_saver import save_webpage
from utils.s3 import compress_and_upload, upload_image
from utils.lookup_tools import whoisxmlapi, ipwhois
from utils.feature_extractor import get_dataset_features
from utils.selenium_ss import screenshot

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
		with open(filename, 'r', errors='ignore') as f:
			data = f.read()
		return data

	except Exception as ex:
		logging.error("Error opening or reading input file: {}", ex)
		exit()

# LOAD BLACKLIST.TXT
BLACKLIST = read_file(os.getenv("BLACKLIST_PATH")).splitlines()

def get_proxy():
    proxy_list = read_file(os.getenv("PROXY_PATH")).splitlines()
    proxy_random = random.choice(proxy_list)
    
    return {"http": f"http://{proxy_random}", "https": f"http://{proxy_random}"}

def request_helper(url):
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
        except: None

'''
    Download dataset and save to db

    @param uuid: urlscan uuid
    @param fish_id: fish id

    @return: Exception, Datset Info, URLScan Info
'''
def save_dataset(uuid, fish_id):
    urlscan_data = urlscan_uuid(uuid)

    logging.info(">>>> Domain {}", urlscan_data["page"]["domain"])
    logging.info(">>>> URL {}", urlscan_data["page"]["url"])
    logging.info(">>>> Brands {}", urlscan_data["verdicts"]["overall"]["brands"])

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

    # check is categories in blacklist
    for category in urlscan_data["verdicts"]["overall"]["categories"]:
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
        
    if not is_alive:
        logging.error(">>>> Scampage is {}", "DEAD")
        remove_dir(f"datasets/{temp_dir}")
        dataset_info["reject_details"] = "Can't reach scampage"
        return Exception("Can't reach scampage"), dataset_info, urlscan_data

    logging.info(">>>> Scampage is {} [{}]", "ALIVE", reqx.status_code)
    
    dataset_info["assets_downloaded"] = save_webpage(urlscan_data["page"]["url"], html_content=dom_req.text, saved_path=f"datasets/{temp_dir}")

    # dataset_path = f"datasets/{dataset_brand}-{dataset_index}"
    dataset_path = f"datasets/{fish_id}"
    os.rename(f"datasets/{temp_dir}", dataset_path)
    dataset_info["dataset_path"] = dataset_path
    dataset_info["htmldom_path"] = f"{dataset_path}/index.html"

    logging.info(">>>> Download complete, saved to {}", dataset_path)
    return None, dataset_info, urlscan_data

if __name__ == "__main__":
    while True:
        # fish = URL_COLLECTIONS.find_one({"status": "queued"})
        # find latest fish
        fish = URL_COLLECTIONS.find_one({"status": "queued"}, sort=[("created_at", -1)])
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
            "http_status_code": None,
            "save_status": None,
            "details": None,
            "worker": os.getenv("WORKER_NAME"),
            "created_at": datetime.today().replace(microsecond=0),
            "updated_at": datetime.today().replace(microsecond=0)
        }
        job_id = JOBS.insert_one(data).inserted_id

        # Update fish as processed
        URL_COLLECTIONS.update_one({"_id": fish_id}, { "$set": { "status": "processed", "updated_at": datetime.today().replace(microsecond=0)} })

        urlscan_uuids = urlscan_search(url)
        logging.info("FOUND {} scan from urlscan.io", len(urlscan_uuids))
        err = False
        dataset_info = None

        if len(urlscan_uuids) > 0:
            for uuid in urlscan_uuids:
                logging.info(">> Downloading UUID {}", uuid)
                err, dataset_info, urlscan_data = save_dataset(uuid, fish_id)

                if dataset_info["reject_details"] == "Brands blacklisted":
                    logging.info(">> Downloading UUID {} : {}", uuid, "STOPPED")
                    break
                
                if err == None:
                    logging.info(">> Downloading UUID {} : {}", uuid, "OK")
                    break
                else:
                    logging.error(">> Downloading UUID {} : {}", uuid, "FAILED")

            if err == None:
                JOBS.update_one({"_id": job_id}, { "$set": { "http_status_code": dataset_info["http_status_code"], "save_status": "success", "details": "OK", "updated_at": datetime.today().replace(microsecond=0)} })

                err, whois_data = whoisxmlapi(domain=urlscan_data["page"]["domain"])
                if err != None:
                    whois_data = {}
                err, ip_data = ipwhois(ip=urlscan_data["stats"]["ipStats"][0]["ip"])

                domain_age = None
                if whois_data.get("created_date", None) != None:
                    domain_age = (fish["created_at"] - whois_data["created_date"]).days

                # extract features
                f_text, f_html, f_css = get_dataset_features(dataset_info["dataset_path"])

                # detect language
                try:
                    lang = detect(f_text)
                except Exception as ex:
                    lang = None

                # screenshot
                ds_abs_path = os.path.abspath(dataset_info["dataset_path"])
                index_path = "file://"+ds_abs_path+"/index.html"

                screenshot_path = dataset_info["dataset_path"]+"/screenshot.jpg"
                logger.info("Taking screenshot to {}", screenshot_path)
                screenshot(index_path, screenshot_path)

                # upload screenshot to s3
                upload_image("fh-ss-images", local_file=dataset_info["dataset_path"]+"/screenshot.jpg", dest=f"dataset_images/{str(fish_id)}.jpg")
                screenshot_path = f"https://fh-ss-images.s3-ap-southeast-1.amazonaws.com/dataset_images/{str(fish_id)}.jpg"

                data = {
                    "ref_url": fish_id,
                    "ref_job": job_id,
                    "entry_date": datetime.today().replace(microsecond=0),
                    "url": urlscan_data["page"]["url"],
                    "folder_path": dataset_info["dataset_path"],
                    "htmldom_path": dataset_info["htmldom_path"],
                    "status": "new",
                    "http_status_code": dataset_info["http_status_code"],
                    "assets_downloaded": dataset_info["assets_downloaded"],
                    "brands": urlscan_data["verdicts"]["overall"]["brands"],
                    "urlscan_uuid": dataset_info["urlscan_uuid"],
                    "screenshot_path": screenshot_path,
                    "domain_name": urlscan_data["page"]["domain"],
                    "whois_lookup_text": whois_data.get("text", None),
                    "whois_registrar": whois_data.get("registrar", None),
                    "whois_registrar_url": whois_data.get("registrar_url", None),
                    "whois_registry_created_at": whois_data.get("created_date", None),
                    "whois_registry_expired_at": whois_data.get("expires_date", None),
                    "whois_registry_updated_at": whois_data.get("updated_date", None),
                    "whois_domain_age": domain_age,
                    "remote_ip_address": urlscan_data["stats"]["ipStats"][0]["ip"],
                    "remote_port": urlscan_data["data"]["requests"][0]["response"]["response"]["remotePort"],
                    "remote_ip_country_name": ip_data.get("country_name", None),
                    "remote_ip_isp": ip_data.get("isp", None),
                    "remote_ip_domain": ip_data.get("domain", None),
                    "remote_ip_asn": ip_data.get("asn", None),
                    "remote_ip_isp_org": ip_data.get("org", None),
                    "protocol": urlscan_data["data"]["requests"][0]["response"]["response"]["protocol"],
                    "security_state": urlscan_data["data"]["requests"][0]["response"]["response"]["securityState"],
                    "security_protocol": None,
                    "security_issuer": None,
                    "security_valid_from": None,
                    "security_valid_to": None,
                    "features": {
                        "text": f_text,
                        "html": f_html,
                        "css": f_css
                    },
                    "language": lang,
                    "created_at": datetime.today().replace(microsecond=0),
                    "updated_at": datetime.today().replace(microsecond=0),
                    "deleted_at": None
                }

                with open(f"{dataset_info['dataset_path']}/info.json", "a") as outfile:
                    json.dump(data, outfile, indent=4, default=str)
                    outfile.write("\n")

                if data["security_state"] == "secure":
                    data["security_protocol"] = urlscan_data["data"]["requests"][0]["response"]["response"]["securityDetails"]["protocol"]
                    data["security_issuer"] = urlscan_data["data"]["requests"][0]["response"]["response"]["securityDetails"]["issuer"]
                    data["security_valid_from"] = urlscan_data["data"]["requests"][0]["response"]["response"]["securityDetails"]["validFrom"]
                    data["security_valid_to"] = urlscan_data["data"]["requests"][0]["response"]["response"]["securityDetails"]["validTo"]

                    # convert to datetime
                    data["security_valid_from"] = datetime.fromtimestamp(data["security_valid_from"])
                    data["security_valid_to"] = datetime.fromtimestamp(data["security_valid_to"])
                DATASETS.insert_one(data)

                # Compress and encrypt
                compress_and_upload(dataset_info["dataset_path"], f"{fish_id}.7z")

            else:
                JOBS.update_one({"_id": job_id}, { "$set": { "http_status_code": dataset_info["http_status_code"], "save_status": "failed", "details": dataset_info["reject_details"], "updated_at": datetime.today().replace(microsecond=0)} })

        else:
            JOBS.update_one({"_id": job_id}, { "$set": { "http_status_code": None, "save_status": "failed", "details": "Domain not found in urlscan.io", "updated_at": datetime.today().replace(microsecond=0)} })

        # Update fish as executed
        URL_COLLECTIONS.update_one({"_id": fish_id}, { "$set": { "status": "done", "updated_at": datetime.today().replace(microsecond=0)} })
