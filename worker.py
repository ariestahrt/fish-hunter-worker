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

import WebPageClone
from utils.s3 import compress_and_upload, upload_image
from utils.lookup_tools import whoisxmlapi, ipwhois
from FishHunterUtil.features_extractor import get_dataset_features
from FishHunterUtil.selenium_ss import screenshot

from colargulog import ColorizedArgsFormatter
from colargulog import BraceFormatStyleFormatter
from utils.similarity_calculator import calculate_similarity
from bson import ObjectId
from utils.twitter import tweet

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

# Connect to mongodb atlas
CLIENT = MongoClient(os.getenv("MONGO_CONNECTION_STRING"))
DB = CLIENT['hunter']
URL_COLLECTIONS = DB["urls"]
SOURCES = DB["sources"]
JOBS = DB["jobs"]
DATASETS = DB["datasets"]
CURRENT_PROXY = None
MINIMUM_SCORE = float(os.getenv("MINIMUM_SCORE"))

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
    min_date = datetime.today() - timedelta(days=17*7)
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
    global CURRENT_PROXY
    while True:
        try:
            response = request_helper(f"https://urlscan.io/api/v1/result/{uuid}")
            # save result to files
            urlscan_res = response.json()

            if response.status_code != 200:
                CURRENT_PROXY = None
                return urlscan_uuid(uuid)

            return urlscan_res
        except Exception as ex:
            logging.error("Error getting urlscan uuid: {}", uuid)
            with open(f"urlscan_error.txt", "a") as f:
                f.write(f"{uuid}\n")
                f.write(response.text)

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
        logging.error(">>>> URLScan data not found")
        return Exception("URLScan data not found"), dataset_info, urlscan_data
    
    # check is url already in db
    if DATASETS.count_documents({"url": urlscan_data["page"]["url"]}) > 0:
        logging.error(">>>> URL already in db")
        dataset_info["reject_details"] = "URL already in db"
        return Exception("URL already in db"), dataset_info, urlscan_data

    # check is categories in blacklist
    for category in urlscan_data["verdicts"]["overall"]["brands"]:
        if category in BLACKLIST:
            dataset_info["reject_details"] = "Brands blacklisted"
            return Exception("Brands blacklisted"), dataset_info, urlscan_data
    
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
    reqx_status_code = None
    try:
        reqx = requests.get(urlscan_data["page"]["url"], allow_redirects=False, verify=False)
        dataset_info["http_status_code"] = reqx.status_code
        reqx_status_code = reqx.status_code
        if reqx.status_code < 500:
            is_alive = True
    except Exception as ex: None
        
    if not is_alive:
        logging.error(">>>> Scampage is {}", "DEAD")
        # remove_dir(f"datasets/{temp_dir}")
        # dataset_info["reject_details"] = "Can't reach scampage"
        # return Exception("Can't reach scampage"), dataset_info, urlscan_data
    else:
        logging.info(">>>> Scampage is {} [{}]", "ALIVE", reqx_status_code)
    
    dataset_info["assets_downloaded"] = WebPageClone.save_webpage(urlscan_data["page"]["url"], html_content=dom_req.text, saved_path=f"datasets/{temp_dir}")

    # dataset_path = f"datasets/{dataset_brand}-{dataset_index}"
    dataset_path = f"datasets/{fish_id}"
    os.rename(f"datasets/{temp_dir}", dataset_path)
    dataset_info["dataset_path"] = dataset_path
    dataset_info["htmldom_path"] = f"{dataset_path}/index.html"

    logging.info(">>>> Download complete, saved to {}", dataset_path)
    return None, dataset_info, urlscan_data

def tweet_dataset(ds):
    logging.info("Tweeting dataset")
    # setup brands tag
    brands_tag = ""
    for brand in ds["brands"]: brands_tag += f"#{brand} "

    tweetText = "New phishing colected!\n\n"
    tweetText += f"🔗 /{ds['domain_name']}/\n"
    tweetText += f"🆔 Brands: {brands_tag}\n"
    if ds["whois_domain_age"] != None:
        tweetText += f"📅 Domain age: {ds['whois_domain_age']}"
        if ds["whois_domain_age"] > 1:
            tweetText += " days\n"
        else:
            tweetText += " day\n"
    tweetText += f"🌐 IP: {ds['remote_ip_address']} ({ds['remote_ip_country_name']})\n"
    if ds["security_state"] == "secure":
        tweetText += f"🔐 SSL/TLS : {ds['security_protocol']} Issued By \"{ds['security_issuer']}\"\n"
    else:
        tweetText += "🔐 SSL/TLS : NO\n"
    tweetText += "\n#phishing #alert #scam #scampage"

    # download image
    img_data = requests.get(ds["screenshot"]["index"]).content
    temp_image_path = f"/tmp/{str(ds['_id'])}.jpg"
    with open(temp_image_path, 'wb') as handler:
        handler.write(img_data)

    tweetImage = temp_image_path
    tweet(tweetText, tweetImage)

    # delete temp image
    os.remove(temp_image_path)

    logging.info("Tweeting dataset complete")

def check_similarity(ds_id):
    ds = DATASETS.find_one({"_id": ObjectId(ds_id)})
    logging.info("Checking similarity for {}", ds["url"])

    start_time = datetime.now()

    # calculate similarity
    similarity_res = calculate_similarity(ds)
    # sort the result
    similarity_res = sorted(similarity_res, key=lambda k: k['final_score'], reverse=True)

    end_time = datetime.now()
    # calculate the time to scan
    time_to_scan = end_time - start_time
    time_to_scan_seconds = time_to_scan.total_seconds()

    final_score = similarity_res[0]["final_score"]
    if final_score > MINIMUM_SCORE:
        # update the dataset status
        # format score to 2 decimal places
        str_final_score = "{:.2f}".format(final_score)
        DATASETS.update_one({"_id": ObjectId(ds_id)}, {"$set": {"status": f"need_check_{str_final_score}"}})
        logging.info(">> OK, need check")
        logging.info(">> Score: {}", str(final_score))

        # tweet the dataset
        tweet_dataset(ds)

    logging.info("Finished in {} seconds", str(time_to_scan_seconds))

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

        url_domain = urlparse(url).netloc

        # Check is domain already in dataset
        if DATASETS.count_documents({"domain_name": url_domain}) > 0:
            logging.info("Domain already in dataset")
            URL_COLLECTIONS.update_one({"_id": fish_id}, { "$set": { "status": "done", "updated_at": datetime.today().replace(microsecond=0)} })
            JOBS.update_one({"_id": job_id}, { "$set": { "http_status_code": None, "save_status": "failed", "details": "Domain already in dataset", "updated_at": datetime.today().replace(microsecond=0)} })
            continue

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
                
                with open(f"json/{uuid}.json", 'w') as f:
                    json.dump(urlscan_data, f)

                err, whois_data = whoisxmlapi(domain=urlscan_data["page"]["domain"])
                if err != None:
                    whois_data = {}
                err, ip_data = ipwhois(ip=urlscan_data["stats"]["ipStats"][0]["ip"])

                domain_age = None
                urlscan_date = urlscan_data["task"]["time"]
                # convert to datetime
                urlscan_date = datetime.strptime(urlscan_date, "%Y-%m-%dT%H:%M:%S.%fZ")

                if whois_data.get("created_date", None) != None:
                    domain_age = (urlscan_date - whois_data["created_date"]).days

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
                logging.info("Taking screenshot to {}", screenshot_path_index)
                screenshot("file://"+ds_abs_path+"/index.html", screenshot_path_index)
                
                # upload screenshot to s3
                upload_image(os.getenv('AWS_BUCKET_IMAGES'), local_file=screenshot_path_index, dest=f"screenshot/index/{str(fish_id)}.jpg")
                
                # clean
                screenshot_path_clean = dataset_info["dataset_path"]+"/screenshot_clean.jpg"
                logging.info("Taking screenshot to {}", screenshot_path_clean)
                screenshot("file://"+ds_abs_path+"/clean.html", screenshot_path_clean)
                
                # upload screenshot to s3
                upload_image(os.getenv('AWS_BUCKET_IMAGES'), local_file=screenshot_path_clean, dest=f"screenshot/clean/{str(fish_id)}.jpg")

                # original
                screenshot_path_original = dataset_info["dataset_path"]+"/screenshot_original.jpg"
                logging.info("Taking screenshot to {}", screenshot_path_original)
                screenshot("file://"+ds_abs_path+"/original.html", screenshot_path_original)
                
                # upload screenshot to s3
                upload_image(os.getenv('AWS_BUCKET_IMAGES'), local_file=screenshot_path_original, dest=f"screenshot/original/{str(fish_id)}.jpg")

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
                    "urlscan_scan_date": urlscan_date,
                    "screenshot": {
                        "index": f"https://fh-ss-images.s3.ap-southeast-1.amazonaws.com/screenshot/index/"+str(fish_id)+".jpg",
                        "original": f"https://fh-ss-images.s3.ap-southeast-1.amazonaws.com/screenshot/original/"+str(fish_id)+".jpg",
                        "clean": f"https://fh-ss-images.s3.ap-southeast-1.amazonaws.com/screenshot/clean/"+str(fish_id)+".jpg"
                    },
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

                # Check similarity
                check_similarity(data["_id"])
            else:
                JOBS.update_one({"_id": job_id}, { "$set": { "http_status_code": dataset_info["http_status_code"], "save_status": "failed", "details": dataset_info["reject_details"], "updated_at": datetime.today().replace(microsecond=0)} })

        else:
            JOBS.update_one({"_id": job_id}, { "$set": { "http_status_code": None, "save_status": "failed", "details": "Domain not found in urlscan.io", "updated_at": datetime.today().replace(microsecond=0)} })

        # Update fish as executed
        URL_COLLECTIONS.update_one({"_id": fish_id}, { "$set": { "status": "done", "updated_at": datetime.today().replace(microsecond=0)} })
