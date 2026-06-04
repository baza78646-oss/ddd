import urllib.request
from bs4 import BeautifulSoup
import re

url1 = "https://docs.cryptocloud.plus/en/api-reference-v2/create-invoice"
url2 = "https://docs.cryptocloud.plus/en/api-reference-v2/invoice-information"

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read()
    soup = BeautifulSoup(html, 'html.parser')
    for pre in soup.find_all('pre'):
        if "{" in pre.text and "status" in pre.text and "result" in pre.text:
            print(pre.text)

get_json(url1)
print("------")
get_json(url2)
