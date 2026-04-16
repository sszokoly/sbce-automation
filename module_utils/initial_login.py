import re
import json
import requests
import sys
import urllib

def accept_eula(host):
    url = f"https://{host}/sbc/eula/"
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
        "_csrf": csrf_token,
    }, indent=2))


    resp = session.post(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "cookie": f"JSESSIONID={jsessionid}",
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/sbc/eula/",
            "User-Agent": "Mozilla/5.0",
        },
        data={
            "_csrf": csrf_token,
            "confirm": "true",
        },
        verify=False,
    )

def main(args):
    host = args[0]
    ucsec_password = urllib.parse.quote(args[1], safe="")
    print(ucsec_password)

if __name__ == "__main__":
    main(sys.argv[1:])