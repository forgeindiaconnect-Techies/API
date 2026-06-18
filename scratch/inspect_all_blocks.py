import httpx
import re

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
html = resp.text

blocks = re.findall(r'<div class="[^"]*result__body[^"]*">(.*?)</div>\s*</div>', html, re.DOTALL)
print("Blocks:", len(blocks))
for idx, block in enumerate(blocks):
    print(f"Block {idx+1}:")
    anchors = re.findall(r'<a\s+([^>]+)>(.*?)</a>', block, re.DOTALL)
    print("  Anchors count:", len(anchors))
    for i, (attrs, content) in enumerate(anchors):
        classes = re.findall(r'class="([^"]+)"', attrs)
        print(f"    Anchor {i+1} classes:", classes)
