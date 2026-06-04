import urllib.request
from bs4 import BeautifulSoup

url2 = "https://docs.cryptocloud.plus/en/api-reference-v2/invoice-information"

req = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read()
soup = BeautifulSoup(html, 'html.parser')
for code in soup.find_all('code'):
    print(code.text)
