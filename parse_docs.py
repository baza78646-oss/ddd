import urllib.request
from bs4 import BeautifulSoup
import re

url1 = "https://docs.cryptocloud.plus/en/api-reference-v2/create-invoice"
url2 = "https://docs.cryptocloud.plus/en/api-reference-v2/invoice-information"

def get_text(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read()
    soup = BeautifulSoup(html, 'html.parser')
    print(f"--- {url} ---")
    for code in soup.find_all('code'):
        print(code.text)

get_text(url1)
get_text(url2)
