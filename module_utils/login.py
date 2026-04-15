import re
import json
import requests

url = "https://10.10.48.180/sbc/login/"

session = requests.Session()
resp = session.get(
    url,
    headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0",
    },
    verify=False,
)

jsessionid = session.cookies.get("JSESSIONID")
m = re.search(r'<meta name="_csrf" content="([^"]+)"', resp.text)
csrf_token = m.group(1) if m else None

print(json.dumps({
    "JSESSIONID": jsessionid,
    "X-CSRF-TOKEN": csrf_token,
    "cookie_header": f"JSESSIONID={jsessionid}" if jsessionid else None,
}, indent=2))