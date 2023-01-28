# Run proxy scrapper
# /usr/bin/python3 /root/http-proxy-list/main.py
echo > /root/proxy-scraper/output.txt && /usr/bin/python3 /root/proxy-scraper/proxyScraper.py -p http

# Remove app.log file
rm /root/fish-hunter-worker/app.log