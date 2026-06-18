import httpx
import re

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
html = resp.text

# We search for <a tags and then check if they contain class="result__a"
matches = re.findall(r'<a([^>]+)>(.*?)</a>', html, re.DOTALL)
print("Total <a> tags:", len(matches))
count = 0
for attrs, content in matches:
    if 'result__a' in attrs:
        count += 1
        href_match = re.search(r'href="([^"]+)"', attrs)
        href = href_match.group(1) if href_match else 'None'
        print(f"Match {count}:")
        print("  Href:", href)
        print("  Title:", content.strip())
        if count >= 3:
            break
