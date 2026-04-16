from __future__ import annotations

import base64
import json
import os
from typing import Final, Literal

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_public_key


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


if __name__ == "__main__":
    public_key_pem = """-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAjePYky5yP0m/eC+borYT
v7XgFYeOMxCqunkV3aW05adB5HQPlSC6tjJF2kJMoONYPUv/UYU1YAEAXbHua5bn
8w8k3SUlcQI+aenew1RxO6Pa4Q065vfZ+akg/HlF5cQQ37crTjeDpiTHCQ0zYo39
3fg6cZCbgbaP8n91lbFg2wUVafwJE0Q48lc4Vvsh1evRG/ym6kn1ngCqVsVYsaSs
cenhKDqYIkQUHCy1j7vVecHw9CSe/p3k5jBo0fAQ2xriA750+mm2m29Iak42YGgR
yIRg7Vb1l0Lza2xZU85AyrJfqPGfgq+G2jnnUdffZJ04kROfSLW1Skw2NjzYU1dy
yuAP6hCZyO8pazhKGbtWC+C3DWzQUTFF00BZ+FW4dKyBeDdzRj0yzfDpT25x3Ivw
RbOzUDbgT/3lHWhbU6E4T3IyAo/Ac8JftffgK+pZJmbuoEoU064VBNCt725/1IFx
M6dwgGRYtmv6BoT4bpqe9ETLXhXpNzUqtcaIMyej7OKoSB5cgfJb6QP3MOgwysM/
0wwtA4K5RdgGCjjQtir/mFB47t25LnpPdgmsj4ANVZSDP/ZbehUrsfRf2+aAJkH/
5uU0+U7fnS7k3Z4kf7FfSJJZ4N2SA8SpYaed623pNTq+Tn3CfNM4uvuyiNo4HOu2
9NdDcypdQRL8X63HwB6FY0UCAwEAAQ==
-----END PUBLIC KEY-----"""

    payload = generate_login_payload(
        username="ucsec",
        password="ucsec",
        public_key_pem=public_key_pem,
        hash_name="SHA-512",
    )
    print(payload)