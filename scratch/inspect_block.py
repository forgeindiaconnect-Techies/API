import httpx
import re

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
html = resp.text

blocks = re.findall(r'<div class="[^"]*result__body[^"]*">(.*?)</div>\s*</div>', html, re.DOTALL)
print("Blocks count:", len(blocks))
if blocks:
    print("Block 1 content:")
    print(blocks[0][:1000])
