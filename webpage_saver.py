from email.mime import base
from urllib.parse import urlparse, urljoin
import re, html
from pathlib import Path
import requests
import os
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings
import validators
disable_warnings(InsecureRequestWarning)
import logging

def logs(*arg):
    return
    for a in arg:
        print(a, end="")
        if a == arg[len(arg)-1]:
            print()
        else:
            print(" ", end="")

def read_file(filename):
	try:
		with open(filename, 'r', encoding="utf8") as f:
			data = f.read()
		return data

	except Exception as ex:
		logs("Error opening or reading input file: ", ex)
		logging.error("Error opening or reading input file: {}", ex)
		exit()

def remove_dir(directory):
    try:
        directory = Path(directory)
        for item in directory.iterdir():
            if item.is_dir():
                remove_dir(item)
            else:
                item.unlink()
        directory.rmdir()
    except Exception as ex: # Ex always the exception
        None

def create_dir(path):
    try:
        os.makedirs(path, exist_ok = True)
        # logs("[!] Creating dir ", path, "OK")
    except OSError as error:
        logs("[X] Failed creating dir")
        logging.error("Failed creating dir {}", path)

def normalize_path(path):
    return path.replace("\\", "/")

def clean_path(path):
    path = normalize_path(path)
    if len(path) > 2:
        if path[:2] == "./":
            return path[2:]

    return path

def dont_slash(path):
    if len(path) > 0:
        if path[0] in ['/', '\\']:
            return path[1:]
    return path

def get_content(url, max_retry=2):
    if max_retry == 0: return None
    try:
        req = requests.get(url, timeout=5, allow_redirects=False, verify=False)
        return req
    except:
        get_content(url, max_retry-1)
    
    return None

def get_file_name(spath):
    url_path = urlparse(spath).path
    file_name = url_path[url_path.rfind("/")+1:]
    if url_path.rfind(".") == -1: file_type = "file";
    else: file_type = url_path[url_path.rfind(".")+1:]; file_name = file_name[:file_name.rfind(".")]
    
    if file_name == "": file_name = "UNKNOWN"
    for forbiden_char in "\ / : * ? \" ' < > |".split(" "):
        if forbiden_char in file_type:
            file_type = "file"
            break

    return file_name, file_type

def download_local_asset(saved_path, base_url, file_path, asset, assets_list):
    # Calculate saved asset name
    if len(asset['name']) + len(asset['type']) == 0:
        logs(f"\t[X] Warning, assets is weird '{asset['name']}.{asset['type']}'")
        return
    asset["saved_to"] = normalize_path(f"assets/{asset['name']}.{asset['type']}")
    
    uniq = 0
    while os.path.exists(f"{saved_path}/{asset['saved_to']}"):
        asset["saved_to"] = normalize_path(f"assets/{asset['name']}-{uniq}.{asset['type']}")
        uniq+=1

    logs("\t[!] asset fullurl", asset["url"])
    logs("\t[!] asset saved_to", asset["saved_to"])
    logs("\t[!] file_src", asset["source"]["file"])

    # return
    # Fix path from current edited file_src
    old_content = read_file(f"{saved_path}/{asset['source']['file']}")
    replacement = asset["saved_to"]
    if asset["source"]["file"].count("/") > 0: replacement = asset["saved_to"][len("assets/"):]
    new_content = old_content.replace(asset["source"]["replace"], asset["source"]["replace"].replace(asset["path"], replacement))
    with open(normalize_path(f"{saved_path}/{asset['source']['file']}"), "w", encoding="utf-8") as f: f.write(new_content)

    logs("\t[!] Downloading assets", asset["url"])
    logging.info(">> Downloading asset {}", asset["url"])
    req = get_content(asset["url"])
    if req == None:
        logs("\t[X] Failed to download assets")
        return

    logs(f"\t[!] RESP {req.status_code}")
    asset["status_code"] = req.status_code
    if req != None and req.status_code == 200:
        logs(f"\t[!] Saving asset to {asset['saved_to']}")
        logging.info(">> Saving asset to {}", asset['saved_to'])
        with open(normalize_path(f"{saved_path}/{asset['saved_to']}"), "wb") as f: f.write(req.content)

        # LOGS TO assets/assets_info.txt
        with open(normalize_path(f"{saved_path}/assets/assets_info.txt"), "a") as f: f.write(f"{asset['saved_to']} => {asset['url']}\n")

        # CHECK IF ASSET IS CSS AND HAS LOCAL URL
        if asset['type'] == "css":
            matches = re.finditer(r"(?<=url\().*?(?=\))", req.text, re.MULTILINE)
            css_asset_list = []
            for match in matches:
                css_url = match.group()
                css_url_unescaped = html.unescape(css_url)
                if len(css_url_unescaped) <= 2: continue

                css_localcontent_url = css_url_unescaped
                if css_url_unescaped[0]+css_url_unescaped[-1] in ['""', "''"]:
                    css_localcontent_url = css_url_unescaped[1:-1]
                
                if "data:image/" in css_localcontent_url:continue

                if len(css_localcontent_url) >= 2:
                    logs("\n[!] FOUND ASSET FROM CSS FILE", css_localcontent_url)
                    css_localcontent_url = clean_path(css_localcontent_url)
                    css_asset_list.append({"path":css_localcontent_url, "source":{"file":asset["saved_to"],"replace":css_url}})

            for css_asset in css_asset_list:
                logs("[!] Processing css_asset", css_asset)
                if "status_code" in css_asset.keys(): continue
                # Converting assets to full url

                parsed = urlparse(asset["url"])
                css_file_path = os.path.normpath(parsed.path[:parsed.path.rfind("/")+1]).replace("\\", "/") + "/"

                asset_fullurl = css_asset['path']
                if css_asset['path'][:2] == "//":
                    asset_fullurl = urlparse(base_url).scheme + ":" + css_asset['path']
                elif urlparse(css_asset['path']).scheme == "":
                    if css_asset['path'][0] in ['/', '\\']:
                        asset_fullurl = normalize_path(urljoin(base_url, css_asset['path']))
                    else:
                        asset_fullurl = normalize_path(urljoin(urljoin(base_url, css_file_path), css_asset['path']))
                
                css_asset["source"]["url"] = asset["url"]
                css_asset["url"] = asset_fullurl
                css_asset["name"], css_asset["type"] = get_file_name(asset_fullurl)                        

                if validators.url(css_asset["url"]):
                    download_local_asset(saved_path, base_url, css_file_path, css_asset, assets_list)
                else:
                    logs(css_asset["url"].encode())
                    logs("\t[X] ASSETS IS INVALID!")
                    css_asset_list.remove(css_asset)

                assets_list.append(css_asset)

def save_webpage(url, html_content="", saved_path="result"):
    logs("[!] SAVING", url)
    logging.info("SAVING {}", url)
    remove_dir(saved_path)
    create_dir(saved_path)
    create_dir(normalize_path(saved_path+"/assets"))

    parsed = urlparse(url)
    base_url = parsed.scheme + "://" + parsed.netloc + "/"
    file_path = os.path.normpath(parsed.path[:parsed.path.rfind("/")+1]).replace("\\", "/") + "/"
    if len(file_path) > 0: file_path = file_path[1:]
    logs("[!] base_url", base_url)
    logs("[!] file_path", file_path)

    if html_content == "": html_content = get_content(url).text
    # Write HTML first
    with open(normalize_path(saved_path+"/index.html"), "w", encoding="utf-8") as f: f.write(html_content)
    html_tag_cssjs = { "link" : "href", "script" : "src", "img":"src" }

    # Collect assets
    assets_list = []
    assets_stats = {"downloaded":0, "total":0}
    for tag in html_tag_cssjs.keys():
        pattern = fr"(?<=<{tag}).*?(?=>)"
        matches = re.finditer(pattern, html_content, re.MULTILINE)
        for match in matches:
            attr=html_tag_cssjs[tag]
            
            tag_attr = match.group()
            pattern2 = rf"(?<={attr}=(\"|')).*?(?=(\"|'))"
            matches2 = re.finditer(pattern2, tag_attr, re.MULTILINE)

            for match2 in matches2:
                asset_path = match2.group()
                lquote = match2.group(1)
                rquote = match2.group(2)

                replace = f"{lquote}{asset_path}{rquote}"
                # DOWNLOAD ASSET IF LOCAL ASSET
                if len(asset_path) >= 2:
                    asset_path = clean_path(asset_path)
                    logs("\n[!] FOUND ASSET", asset_path)
                    assets_list.append({"path":asset_path, "source":{"file":normalize_path("index.html"),"replace":replace}})
    
    # Also download from inline css
    pattern = r"(?<=url\().*?(?=\))"
    matches = re.finditer(pattern, html_content, re.MULTILINE)

    for match in matches:
        css_url = match.group()
        css_url_unescaped = html.unescape(css_url)
        if len(css_url_unescaped) <= 2: continue

        css_localcontent_url = css_url_unescaped
        if css_url_unescaped[0]+css_url_unescaped[-1] in ['""', "''"]:
            css_localcontent_url = css_url_unescaped[1:-1]
        
        if "data:image/" in css_localcontent_url:continue

        if len(css_localcontent_url) >= 2:
            logs("\n[!] FOUND INLINE CSS ASSET", css_localcontent_url)
            css_localcontent_url = clean_path(css_localcontent_url)
            assets_list.append({"path":css_localcontent_url, "source":{"file":normalize_path("index.html"),"replace":css_url}})

    for asset in assets_list:
        if "status_code" in asset.keys(): continue
        logs("[!] Start Downloading Asset", asset)
        # Converting assets to full url
        asset_fullurl = asset["path"]
        if asset["path"][:2] == "//":
            asset_fullurl = urlparse(base_url).scheme + ":" + asset["path"]
        elif urlparse(asset["path"]).scheme == "":
            if asset["path"][0] in ['/', '\\']:
                asset_fullurl = normalize_path(urljoin(base_url, asset["path"]))
            else:
                asset_fullurl = normalize_path(urljoin(urljoin(base_url, file_path), asset["path"]))
        
        asset["url"] = asset_fullurl
        asset["source"]["url"] = base_url+"index.html"
        # Get filetype
        asset["name"], asset["type"] = get_file_name(asset_fullurl)

        if validators.url(asset["url"]):
            download_local_asset(saved_path, base_url, file_path, asset, assets_list)
        else:
            logs("[X] Assets is invalid!")
            assets_list.remove(asset)
    
    import json
    with open(saved_path+"/assets.json", "w") as f:
        json.dump(assets_list, f, indent=4, sort_keys=True)
    # if assets_stats["total"] == 0: return 1.0
    assets_ok = [x for x in assets_list if "status_code" in x.keys() and x['status_code'] == 200]
    if len(assets_list) == 0: return 1.0
    return float(len(assets_ok)/len(assets_list))

if __name__ == "__main__":
    None
    # html_text = read_file("dom_sample.html")
    # url = "https://www.paypal.com/signin"
    # asset_downloaded = save_webpage(url, saved_path="result/")
    # logs("assets_downloaded", asset_downloaded)