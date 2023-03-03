# Run proxy scrapper
# /usr/bin/python3 /root/http-proxy-list/main.py
echo > /mnt/c/code/research/proxy-scraper/output.txt && /usr/bin/python3 /mnt/c/code/research/proxy-scraper/proxyScraper.py -p http

# Remove app.log file
rm /root/fish-hunter-worker/app.log