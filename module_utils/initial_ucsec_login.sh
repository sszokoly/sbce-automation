#!/bin/bash

host='192.168.122.10'
new_password='cmb@Dm1n'
new_password=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$new_password")

headers=$(mktemp)
body=$(mktemp)

##### Fetch EULA page to get JSESSIONID and CSRF token #####
url="https://$host/sbc/eula/"

echo "Fetching EULA page..."
curl -k -sS -D "$headers" -o "$body" \
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \
  -H 'User-Agent: Mozilla/5.0' \
  "$url"

jsessionid=$(awk -F'[=;]' '/^[Ss]et-[Cc]ookie: JSESSIONID=/{print $2; exit}' "$headers")
csrf_token=$(grep -oP 'name="_csrf"\s+value="\K[^"]+' "$body" | head -1)
    
printf 'JSESSIONID=%s\n' "$jsessionid"
printf 'X-CSRF-TOKEN=%s\n' "$csrf_token"


##### Submit EULA acceptance #####
echo "Submitting EULA acceptance..."
curl -k -X POST "https://$host/sbc/eula/" \
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H "Cookie: JSESSIONID=$jsessionid" \
  -H "Origin: https://$host" \
  -H "Referer: https://$host/sbc/eula/" \
  -H 'User-Agent: Mozilla/5.0' \
  --data "_csrf=$csrf_token&confirm=true"


##### Fetch login page to get public key #####
url="https://$host/sbc/login/"

echo "Fetching login page ..."
curl -k -sS -D "$headers" -o "$body" \
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \
  -H "Cookie: JSESSIONID=$jsessionid" \
  -H 'User-Agent: Mozilla/5.0' \
  "$url"

public_key=$(perl -0777 -ne 'if (/const\s+publicKey\s*=\s*"((?:\\.|[^"])*)";/s) { print $1 }' "$body")
public_key=${public_key//\\\//\/}

printf 'Public Key:\n%s\n' "$public_key"
printf 'JSESSIONID=%s\n' "$jsessionid"
printf 'X-CSRF-TOKEN=%s\n' "$csrf_token"

##### Submit ucsec username #####
echo "Submitting user..."
curl -k -i "https://$host/sbc/login/check-challenge" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/plain, */*' \
  -H "X-CSRF-TOKEN: $csrf_token" \
  -H "Origin: https://$host" \
  -H "Referer: https://$host/sbc/login/" \
  -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36' \
  -b "JSESSIONID=$jsessionid" \
  --data '{"username":"ucsec"}'


##### Submit encrypted password #####
echo "Submitting password..."
curl -k -i "https://$host/sbc/login/" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept: application/json, text/plain, */*' \
  -H "X-CSRF-TOKEN: $csrf_token"  \
  -H "Origin: https://$host" \
  -H "Referer: https://$host/sbc/login/" \
  -H 'User-Agent: Mozilla/5.0' \
  -b "JSESSIONID=$jsessionid" \
  --data-urlencode "payload=$(python3 crypto.py)" \
  --data-urlencode "_csrf=$csrf_token"


##### Change password to cmb@Dm1n #####
echo "Changing password..."
curl -k -i "https://$host/sbc/change-password/" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept: application/json, text/plain, */*' \
  -H "Cookie: JSESSIONID=$jsessionid" \
  -H "Origin: https://$host" \
  -H "Referer: https://$host/sbc/change-password/" \
  -H 'User-Agent: Mozilla/5.0' \
  -b "JSESSIONID=$jsessionid" \
  --data "_csrf=$csrf_token&current-password=ucsec&new-password=$new_password&repeat-password=$new_password"

echo "Done. You can now log in with username 'ucsec' and password 'cmb@Dm1n'."