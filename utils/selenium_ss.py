from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from PIL import Image
from io import BytesIO

options = Options()
options.add_argument('--headless=new')
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

prefs = {}
prefs["webkit.webprefs.javascript_enabled"] = False
prefs["profile.content_settings.exceptions.javascript.*.setting"] = 2
prefs["profile.default_content_setting_values.javascript"] = 2
prefs["profile.managed_default_content_settings.javascript"] = 2

options.add_experimental_option("prefs", prefs)

def screenshot(url, save_to="test_ss.png"):
    driver = webdriver.Chrome(service=Service("/usr/local/bin/chromedriver"), options=options, desired_capabilities=DesiredCapabilities.CHROME)

    driver.maximize_window()
    driver.set_window_size(1920, 1080)
    driver.get(url)
    ss = driver.get_screenshot_as_png()

    # convert to jpg
    img = Image.open(BytesIO(ss))
    img = img.convert("RGB")
    img.save(save_to)

    driver.quit()

if __name__ == "__main__":
    screenshot("https://www.whatismybrowser.com/detect/is-javascript-enabled", save_to="test_ss.jpg")