import httpx
import re

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
print("Status:", resp.status_code)
html = resp.text

# Check if there are matches for typical classes
print("result__snippet matches:", len(re.findall(r'result__snippet', html)))
print("result__url matches:", len(re.findall(r'result__url', html)))
print("result__snippet content sample:")
for match in re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)[:3]:
    print("-", match.strip())

print("\nresult__url content sample:")
for match in re.findall(r'<a class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)[:3]:
    print("-", match.strip())

print("\nresult__link matches:")
for match in re.findall(r'<a class="result__link"[^>]*>(.*?)</a>', html, re.DOTALL)[:3]:
    print("-", match.strip())

# Let's search for any anchor tags with class inside result__body or results
print("\nAnchor classes found in body:")
classes = set(re.findall(r'class="([^"]+)"', html))
for c in classes:
    if "result" in c:
        print("-", c)
