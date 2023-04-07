import json
import os, json
from dotenv import load_dotenv
from FishHunterUtil.similarity import calculate_dict_similarity, lcs, ngram_similarity, cosine_similarity, calculate_by_lcs
from ngram import NGram as NGramOri
from pymongo import MongoClient
from datetime import datetime
import threading

max_threads = 9999
thread_semaphore = threading.BoundedSemaphore(max_threads)

threads = []
list_result = []

load_dotenv()
MULTIPLIER_CSS = float(os.getenv("MULTIPLIER_CSS"))
MULTIPLIER_HTML = float(os.getenv("MULTIPLIER_HTML"))
MULTIPLIER_TEXT = float(os.getenv("MULTIPLIER_TEXT"))

MONGO_CLIENT = MongoClient(os.getenv("MONGO_CONNECTION_STRING"))
DB = MONGO_CLIENT['hunter']
SAMPLES = DB["samples"]

def calculate(feat_ds, sample):
    global threads, list_result
    try:
        thread_semaphore.acquire()
        # print(">>> Calculating similarity for sample: {}".format(sample["url"]))
        f_text = feat_ds["text"]
        f_html = json.loads(feat_ds["html"])
        f_css = json.loads(feat_ds["css"])

        # get sample features
        feat_sm = sample["features"]
        sample_text = feat_sm["text"]
        sample_html = json.loads(feat_sm["html"])
        sample_css = json.loads(feat_sm["css"])

        # compare features

        # CSS by cosine similarity
        css_time_start = datetime.now()
        css_score = calculate_dict_similarity(f_css, sample_css)
        css_time_end = datetime.now()
        css_time_seconds = (css_time_end - css_time_start).total_seconds()

        # HTML By LCS
        html_time_start = datetime.now()
        lcs_res = lcs(f_html, sample_html)
        html_score = (2 * lcs_res[0]) / (len(f_html) + len(sample_html))
        html_time_end = datetime.now()
        html_time_seconds = (html_time_end - html_time_start).total_seconds()

        # TEXT By
        # Calculate by using ngram=1
        text_time_start = datetime.now()
        by_ngram1 = ngram_similarity(f_text, sample_text, 1)

        # Calculate by ngram similarity
        # by_ngram = NGramOri.compare(f_text, sample_text, N=1)
        by_ngram = 0.0

        # Calculate by cosine similarity
        by_cosine = cosine_similarity(f_text, sample_text)

        # Calculate by LCS
        # by_lcs = calculate_by_lcs(f_text, sample_text)
        text_time_end = datetime.now()
        text_time_seconds = (text_time_end - text_time_start).total_seconds()

        FINAL_CSS_SCORE = max(css_score[0], css_score[1])
        FINAL_HTML_SCORE = html_score
        FINAL_TEXT_SCORE = max(by_ngram, by_ngram1, by_cosine)

        FINAL_SCORE = FINAL_CSS_SCORE*MULTIPLIER_CSS + FINAL_HTML_SCORE*MULTIPLIER_HTML + FINAL_TEXT_SCORE*MULTIPLIER_TEXT

        list_result.append({
            "brands": sample["brands"],
            "ref_sample": str(sample["_id"]),
            "url": sample["url"],
            "css": {
                "score": FINAL_CSS_SCORE,
                "time": css_time_seconds,
            },
            "html": {
                "score": FINAL_HTML_SCORE,
                "time": html_time_seconds,
            },
            "text": {
                "score": FINAL_TEXT_SCORE,
                "time": text_time_seconds,
            },
            "final_score": FINAL_SCORE,
        })
    except Exception as e:
        print(e)
    finally:
        thread_semaphore.release()
        # print("<<< Calculating similarity for sample: {} (done)".format(sample["url"]))
        None

def calculate_similarity(ds):
    global list_result, threads

    threads = []

    feat_ds = ds["features"]
    lang = ds["language"]

    # get all samples with the same language
    list_samples = SAMPLES.find({"lang": lang})

    list_result = []

    # loop through samples
    list_samples = list(SAMPLES.find())
    for sample in list_samples:
        t = threading.Thread(target=calculate, args=(feat_ds, sample))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return list_result