import httpx
import re

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
html = resp.text

blocks = re.findall(r'<div class="[^"]*result__body[^"]*">(.*?)</div>\s*</div>', html, re.DOTALL)
if blocks:
    print("Block 0 anchors:")
    # We find all anchors inside block 0
    # To be safe against nested tags, we can match <a... href=...
    anchors = re.findall(r'<a\s+([^>]+)>(.*?)</a>', blocks[0], re.DOTALL)
    print("Total anchors in block 0:", len(anchors))
    for i, (attrs, content) in enumerate(anchors):
        print(f"  Anchor {i+1}:")
        print("    Attrs:", attrs.strip()[:200])
        print("    Content:", content.strip()[:100])
