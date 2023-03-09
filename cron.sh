# Run proxy scrapper every 24 hours
# 0 * * * * echo > /app/proxy-scraper/output.txt && /usr/local/bin/python3 /app/proxy-scraper/proxyScraper.py -p http -o /app/proxy-scraper/output.txt

# Remove app.log file every 24 hours
# 0 0 * * * rm /app/app.log

# Run url scrapper every 5 minutes
# */5 * * * * /usr/local/bin/python3 /app/url_scrapper.py