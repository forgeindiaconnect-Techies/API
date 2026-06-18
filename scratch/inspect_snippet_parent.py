import httpx
import re

url = "https://html.duckduckgo.com/html/?q=car"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
}
resp = httpx.get(url, headers=headers)
html = resp.text

# We find all occurrences of result__snippet and print the parent tags
matches = re.finditer(r'class="result__snippet"', html)
for i, m in enumerate(matches):
    start = m.start()
    print(f"Occurrence {i+1} parent tags:")
    # Print 500 chars before to see parent divs
    context = html[max(0, start-400):start]
    print(context[-200:])
    if i >= 3:
        break
