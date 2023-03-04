from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from PIL import Image
from io import BytesIO

options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-javascript')
# disable cors
options.add_argument('--disable-web-security')
options.add_argument('--allow-running-insecure-content')
options.add_argument('--allow-insecure-localhost')
options.add_argument('--allow-file-access-from-files')
options.add_argument('--allow-file-access')
options.add_argument('--allow-cross-origin-auth-prompt')

driver = webdriver.Chrome(service=Service("/usr/local/bin/chromedriver"), options=options)

driver.maximize_window()
driver.set_window_size(1920, 1080)

def screenshot(url, save_to="test_ss.png"):
    global driver
    driver.get(url)    
    ss = driver.get_screenshot_as_png()

    # convert to jpg
    img = Image.open(BytesIO(ss))
    img = img.convert("RGB")
    img.save(save_to)

if __name__ == "__main__":
    screenshot("https://www.google.com", save_to="test_ss.jpg")