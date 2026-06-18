import httpx
import re

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
html = resp.text

# Let's find matches for result__a anchors
matches = re.findall(r'<a class="[^"]*result__a[^"]*"(.*?)>(.*?)</a>', html, re.DOTALL)
print("Matches found:", len(matches))
for i, (attrs, content) in enumerate(matches[:3]):
    print(f"Match {i}:")
    print("  Attrs:", attrs.strip())
    print("  Content:", content.strip())
