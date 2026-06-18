import httpx
import re

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
html = resp.text

# Let's find first occurrence of 'result__snippet' and print 500 chars before and after it
idx = html.find('result__snippet')
if idx != -1:
    print("Found result__snippet at index:", idx)
    print("Context:")
    print(html[idx-300:idx+500])
else:
    print("result__snippet not found in raw html")
