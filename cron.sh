# Run proxy scrapper every 24 hours
# 0 * * * * echo > /fish-hunter-worker/proxy-scraper/output.txt && /usr/local/bin/python3 /fish-hunter-worker/proxy-scraper/proxyScraper.py -p http -o /fish-hunter-worker/proxy-scraper/output.txt

# Remove app.log file every 24 hours
# 0 0 * * * rm /fish-hunter-worker/app.log

# Run url scrapper every 5 minutes
# */5 * * * * /usr/local/bin/python3 /fish-hunter-worker/url_scrapper.py