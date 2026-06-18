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

blocks = re.findall(r'<div class="[^"]*result__body[^"]*">(.*?)</div>\s*</div>', html, re.DOTALL)
print("Total result blocks found:", len(blocks))

results = []
for i, block in enumerate(blocks):
    # Find all <a> tags inside the block
    anchors = re.findall(r'<a([^>]+)>(.*?)</a>', block, re.DOTALL)
    
    href = None
    title_raw = None
    snippet_raw = None
    
    for attrs, content in anchors:
        if 'result__a' in attrs:
            href_match = re.search(r'href="([^"]+)"', attrs)
            if href_match:
                href = href_match.group(1)
                title_raw = content
        elif 'result__snippet' in attrs:
            snippet_raw = content
            
    if href and title_raw and snippet_raw:
        if "uddg=" in href:
            href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
            
        title = html_lib.unescape(re.sub(r'<[^>]+>', '', title_raw).strip())
        snippet = html_lib.unescape(re.sub(r'<[^>]+>', '', snippet_raw).strip())
        
        print(f"Block {len(results)+1}:")
        print("  Title:", title.encode('ascii', 'ignore').decode('ascii'))
        print("  Href:", href)
        print("  Snippet:", snippet.encode('ascii', 'ignore').decode('ascii')[:100])
        results.append({
            "title": title,
            "url": href,
            "snippet": snippet
        })
        if len(results) >= 3:
            break
