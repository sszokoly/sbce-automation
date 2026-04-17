#!/usr/bin/env python3

from __future__ import annotations
import base64
import os
import re
import json
import requests
import sys
import urllib
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from typing import Final, Literal
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_public_key


DEFAULT_UCSEC_PASSWORD = "ucsec"
DEBUG = False
PEM_BEGIN: Final[str] = "-----BEGIN PUBLIC KEY-----"
PEM_END: Final[str] = "-----END PUBLIC KEY-----"
ALLOWED_HASHES: Final[set[str]] = {"SHA-256", "SHA-512"}


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def from_base64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def pem_body_to_bytes(pem: str) -> bytes:
    pem = pem.strip()
    if not pem.startswith(PEM_BEGIN) or not pem.endswith(PEM_END):
        raise ValueError("Provided payload is not a valid PEM formatted public key.")

    body = pem.replace(PEM_BEGIN, "").replace(PEM_END, "")
    body = "".join(body.split())
    return from_base64(body)


def pem_to_crypto_key(
    pem: str,
    hash_name: Literal["SHA-256", "SHA-512"] = "SHA-512",
):
    if hash_name not in ALLOWED_HASHES:
        raise ValueError(
            f"Unsupported public key hash algorithm: {hash_name}; "
            f"Must be one of: {', '.join(sorted(ALLOWED_HASHES))}"
        )

    key_data = pem_body_to_bytes(pem)

    public_key = load_pem_public_key(
        pem.encode("utf-8")
        if pem.startswith(PEM_BEGIN)
        else key_data  # practically unused here, kept for parity
    )

    return public_key


def _get_oaep_hash(hash_name: str):
    if hash_name == "SHA-256":
        return hashes.SHA256()
    if hash_name == "SHA-512":
        return hashes.SHA512()
    raise ValueError(f"Unsupported hash: {hash_name}")


def encrypt_string(
    public_key,
    plaintext: str,
    hash_name: Literal["SHA-256", "SHA-512"] = "SHA-512",
) -> str:
    encoded = plaintext.encode("utf-8")

    # 12-byte IV, same as crypto.getRandomValues(new Uint8Array(12))
    iv = os.urandom(12)

    # AES-256-GCM key, same as generateKey({name:"AES-GCM", length:256})
    raw_aes_key = os.urandom(32)

    # RSA-OAEP encrypt the raw AES key
    oaep_hash = _get_oaep_hash(hash_name)
    encrypted_aes_key = public_key.encrypt(
        raw_aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=oaep_hash),
            algorithm=oaep_hash,
            label=None,
        ),
    )

    # AES-GCM encrypt the plaintext
    aesgcm = AESGCM(raw_aes_key)
    encrypted_payload = aesgcm.encrypt(iv, encoded, None)

    # JS code concatenates IV + ciphertext_and_tag
    merged = iv + encrypted_payload

    result = {
        "key": to_base64(encrypted_aes_key),
        "payload": to_base64(merged),
    }

    # JS does btoa(JSON.stringify(result))
    return to_base64(json.dumps(result, separators=(",", ":")).encode("utf-8"))


def generate_login_payload(
    username: str,
    password: str,
    public_key_pem: str,
    hash_name: Literal["SHA-256", "SHA-512"] = "SHA-512",
) -> str:
    public_key = pem_to_crypto_key(public_key_pem, hash_name)
    login_object = json.dumps(
        {"username": username, "password": password},
        separators=(",", ":"),
    )
    return encrypt_string(public_key, login_object, hash_name)


def initial_ucsec_login(host, new_ucsec_password, debug=False):
    session = requests.Session()

    # GET CSRF token and JSESSIONID cookie
    resp = session.get(
        f"https://{host}/sbc/eula/",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0",
        },
        verify=False,
    )

    jsessionid = session.cookies.get("JSESSIONID")
    m = re.search(r'name="_csrf" value="([^"]+)"', resp.text)
    csrf_token = m.group(1) if m else None

    # POST confirmation of EULA
    resp = session.post(
        f"https://{host}/sbc/eula/",
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

    if debug:
        print("[+] POST EULA DONE")
        print(json.dumps({
            "JSESSIONID": jsessionid,
            "_csrf": csrf_token,
        }, indent=2), "\n")


    # GET publicKey from login page
    resp = session.get(
        f"https://{host}/sbc/login/",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "cookie": f"JSESSIONID={jsessionid}",
            "User-Agent": "Mozilla/5.0",
        },
        verify=False,
    )

    m = re.search(r'const publicKey = "([^"]+)"', resp.text)
    public_key = m.group(1) if m else None

    if public_key:
        public_key = json.loads('"' + public_key + '"')

    if debug:
        print("[+] GET publicKey DONE")
        print(json.dumps({
            "publicKey": public_key,
        }, indent=2), "\n")


    # POST username 'ucsec' on login page
    resp = session.post(
        f"https://{host}/login/check-challenge",
        headers={
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/json",
            "X-CSRF-TOKEN": csrf_token,
            "cookie": f"JSESSIONID={jsessionid}",
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/sbc/login/",
            "User-Agent": "Mozilla/5.0",
        },
        data={
            "username": "ucsec",
        },
        verify=False,
    )

    if debug:
        print("[+] POST username DONE")
        print(json.dumps({
            "username": "ucsec",
        }, indent=2), "\n")


    # POST username 'ucsec' and default password 'ucsec' on login page
    resp = session.post(
        f"https://{host}/sbc/login/",
        headers={
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRF-TOKEN": csrf_token,
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/sbc/login/",
            "cookie": f"JSESSIONID={jsessionid}",
            "User-Agent": "Mozilla/5.0",
        },
        data={
            "_csrf": csrf_token,
            "payload": generate_login_payload(
                username="ucsec",
                password=DEFAULT_UCSEC_PASSWORD,
                public_key_pem=public_key,
            ),
        },
        verify=False,
    )

    if debug:
        print("[+] POST default password DONE")
        print(json.dumps({
            "_csrf": csrf_token,
            "payload": generate_login_payload(
                username="ucsec",
                password=DEFAULT_UCSEC_PASSWORD,
                public_key_pem=public_key,
            ),
        }, indent=2), "\n")


    # POST current password and new password on login page
    resp = session.post(
        f"https://{host}/sbc/change-password/",
        headers={
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/sbc/change-password/",
            "cookie": f"JSESSIONID={jsessionid}",
            "User-Agent": "Mozilla/5.0",
        },
        data={
            "_csrf": csrf_token,
            "current-password": "ucsec",
            "new-password": new_ucsec_password,
            "repeat-password": new_ucsec_password,
        },
        verify=False,
    )

    if debug:
        print("[+] POST new password DONE")
        print(json.dumps({
            "_csrf": csrf_token,
            "current-password": "ucsec",
            "new-password": new_ucsec_password,
            "repeat-password": new_ucsec_password,
        }, indent=2), "\n")


    return 0 if "Your password has been changed" in resp.text else 1


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.122.10"
    new_ucsec_password = sys.argv[2] if len(sys.argv) > 2 else "cmb@Dm1n"
    sys.exit(initial_ucsec_login(host, new_ucsec_password, debug=DEBUG))