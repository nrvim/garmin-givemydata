from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.binary_location = "/usr/bin/google-chrome"

options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")

driver = webdriver.Chrome(options=options)

driver.get("https://example.com")
print(driver.title)

driver.quit()
