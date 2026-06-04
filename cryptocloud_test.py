import urllib.request
import json

def search():
    req = urllib.request.Request("https://html.duckduckgo.com/html/?q=cryptocloud+api+v2+invoice+status", headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    print(html[:1000])

search()
