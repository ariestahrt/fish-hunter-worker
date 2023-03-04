# read env
import requests
import json
import os
import random
from dotenv import load_dotenv
from datetime import date, datetime, timedelta

load_dotenv()

def convert_date(date_str):
    rtr = None
    # "2023-01-27T04:29:33.0Z"
    dateformat = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S.%f%Z",
    ]

    for f in dateformat:
        try:
            rtr = datetime.strptime(date_str, f)
            break
        except:
            pass
    
    return rtr

def whoisxmlapi(domain):
    print("DOMAIN ==>", domain)
    # get random api key
    api_keys = open(os.getenv('WHOISXML_API_KEYS'), 'r').read().splitlines()
    if len(api_keys) == 0: api_keys = [""]
    api_key = api_keys[0]

    try:
        url = 'https://www.whoisxmlapi.com/whoisserver/WhoisService'
        params = {
            'apiKey': api_key,
            'domainName': domain,
            'outputFormat': 'JSON'
        }
        response = requests.get(url, params=params)

        if response.status_code == 401:
            # remove api key from file
            with open(os.getenv('WHOISXML_API_KEYS'), 'r') as f:
                lines = f.readlines()
            with open(os.getenv('WHOISXML_API_KEYS'), 'w') as f:
                for line in lines:
                    if line.strip("\n") != api_key:
                        f.write(line)

        rtr = {}
        if response.status_code != 200:
            return Exception('API Error'), None
        
        # save to file
        with open('whoisxmlapi.json', 'w') as f:
            f.write(response.text)
        
        rtr["text"] = response.text
        rtr["domain_name"] = response.json()["WhoisRecord"]["domainName"]
        rtr["registrar_name"] = response.json()["WhoisRecord"]["registrarName"]
        
        try:
            rtr["registrar_url"] = response.json()["WhoisRecord"]["registryData"]["rawText"].split("Registrar URL: ")[1].split("\n")[0]
        except:
            rtr["registrar_url"] = None
        
        rtr["created_date"] = response.json()["WhoisRecord"]["registryData"]["createdDate"]
        rtr["updated_date"] = response.json()["WhoisRecord"]["registryData"]["updatedDate"]
        rtr["expires_date"] = response.json()["WhoisRecord"]["registryData"]["expiresDate"]

        # convert date
        rtr["created_date"] = convert_date(rtr["created_date"])
        rtr["updated_date"] = convert_date(rtr["updated_date"])
        rtr["expires_date"] = convert_date(rtr["expires_date"])

        rtr["name_servers"] = response.json()["WhoisRecord"]["registryData"]["nameServers"]["hostNames"]
        return None, rtr
    except Exception as e:
        print(e)
        return e, {}

def ipwhois(ip):
    try:
        url = 'https://ipwho.is/' + ip
        response = requests.get(url)

        rtr = {}
        if response.status_code != 200:
            return Exception('API Error'), None
        
        rtr["country_name"] = response.json()["country"]
        rtr["asn"] = response.json()["connection"]["asn"]
        rtr["org"] = response.json()["connection"]["org"]
        rtr["isp"] = response.json()["connection"]["isp"]
        rtr["domain"] = response.json()["connection"]["domain"]
        return None, rtr
    except Exception as e:
        return e, {}

# main
def main():
    domain = 'atorebates.line.pm'
    ip = '2a06:98c1:3121::3'
    # print(ip)
    err, result_whois = whoisxmlapi(domain)
    if err != None:
        print(err)
        return None
    
    err, result_ip = ipwhois(ip)
    if err != None:
        print(err)
        return None
        
    print(json.dumps(result_whois, indent=4, default=str))
    print(json.dumps(result_ip, indent=4, default=str))
    
if __name__ == '__main__':
    main()