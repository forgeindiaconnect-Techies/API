import httpx
import re
import urllib.parse
import html as html_lib

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
html = resp.text

# Extract all title links and all snippet links
links = re.findall(r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
snippets = re.findall(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)

print("Links found:", len(links))
print("Snippets found:", len(snippets))

results = []
for i in range(min(5, len(links), len(snippets))):
    href = links[i][0]
    if "uddg=" in href:
        href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
        
    title = html_lib.unescape(re.sub(r'<[^>]+>', '', links[i][1]).strip())
    snippet = html_lib.unescape(re.sub(r'<[^>]+>', '', snippets[i]).strip())
    
    print(f"Result {i+1}:")
    print("  Title:", title.encode('ascii', 'ignore').decode('ascii'))
    print("  Href:", href)
    print("  Snippet:", snippet.encode('ascii', 'ignore').decode('ascii')[:100])
