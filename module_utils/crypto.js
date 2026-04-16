const PEM_BEGIN = "-----BEGIN PUBLIC KEY-----";
const PEM_END = "-----END PUBLIC KEY-----";
const RSA_NAME = "RSA-OAEP";
const AES_NAME = "AES-GCM";
const ALLOWED_HASHES = ["SHA-256", "SHA-512"];

function toBase64(buffer) {
  return Buffer.from(buffer).toString("base64");
}

function fromBase64(base64) {
  return Uint8Array.from(Buffer.from(base64, "base64")).buffer;
}

function pemBodyToArrayBuffer(pem) {
  if (!pem.startsWith(PEM_BEGIN) || !pem.trim().endsWith(PEM_END)) {
    throw new Error("Provided payload is not a valid PEM formatted public key.");
  }

  const body = pem
    .replace(PEM_BEGIN, "")
    .replace(PEM_END, "")
    .replace(/\s+/g, "");

  return fromBase64(body);
}

async function pemToCryptoKey(pem, hash = "SHA-512") {
  if (!ALLOWED_HASHES.includes(hash)) {
    throw new Error(
      `Unsupported public key hash algorithm: ${hash}; Must be one of: ${ALLOWED_HASHES.join(", ")}`
    );
  }

  const keyData = pemBodyToArrayBuffer(pem);

  return crypto.subtle.importKey(
    "spki",
    keyData,
    { name: RSA_NAME, hash },
    true,
    ["encrypt"]
  );
}

async function encryptString(publicKey, plaintext) {
  const encoded = new TextEncoder().encode(plaintext);
  const iv = crypto.getRandomValues(new Uint8Array(12));

  const aesKey = await crypto.subtle.generateKey(
    { name: AES_NAME, length: 256 },
    true,
    ["encrypt", "decrypt"]
  );

  const rawAesKey = await crypto.subtle.exportKey("raw", aesKey);

  const encryptedAesKey = await crypto.subtle.encrypt(
    { name: RSA_NAME },
    publicKey,
    rawAesKey
  );

  const encryptedPayload = await crypto.subtle.encrypt(
    { name: AES_NAME, iv },
    aesKey,
    encoded
  );

  const merged = new Uint8Array(iv.byteLength + encryptedPayload.byteLength);
  merged.set(iv, 0);
  merged.set(new Uint8Array(encryptedPayload), iv.byteLength);

  const result = {
    key: toBase64(encryptedAesKey),
    payload: toBase64(merged),
  };

  return Buffer.from(JSON.stringify(result), "utf8").toString("base64");
}

async function generateLoginPayload(username, password, publicKeyPem) {
  const publicKey = await pemToCryptoKey(publicKeyPem, "SHA-512");
  const loginObject = JSON.stringify({ username, password });
  return encryptString(publicKey, loginObject);
}

// Example
(async () => {
  const publicKeyPem = `-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAjePYky5yP0m\/eC+borYT
v7XgFYeOMxCqunkV3aW05adB5HQPlSC6tjJF2kJMoONYPUv\/UYU1YAEAXbHua5bn
8w8k3SUlcQI+aenew1RxO6Pa4Q065vfZ+akg\/HlF5cQQ37crTjeDpiTHCQ0zYo39
3fg6cZCbgbaP8n91lbFg2wUVafwJE0Q48lc4Vvsh1evRG\/ym6kn1ngCqVsVYsaSs
cenhKDqYIkQUHCy1j7vVecHw9CSe\/p3k5jBo0fAQ2xriA750+mm2m29Iak42YGgR
yIRg7Vb1l0Lza2xZU85AyrJfqPGfgq+G2jnnUdffZJ04kROfSLW1Skw2NjzYU1dy
yuAP6hCZyO8pazhKGbtWC+C3DWzQUTFF00BZ+FW4dKyBeDdzRj0yzfDpT25x3Ivw
RbOzUDbgT\/3lHWhbU6E4T3IyAo\/Ac8JftffgK+pZJmbuoEoU064VBNCt725\/1IFx
M6dwgGRYtmv6BoT4bpqe9ETLXhXpNzUqtcaIMyej7OKoSB5cgfJb6QP3MOgwysM\/
0wwtA4K5RdgGCjjQtir\/mFB47t25LnpPdgmsj4ANVZSDP\/ZbehUrsfRf2+aAJkH\/
5uU0+U7fnS7k3Z4kf7FfSJJZ4N2SA8SpYaed623pNTq+Tn3CfNM4uvuyiNo4HOu2
9NdDcypdQRL8X63HwB6FY0UCAwEAAQ==
-----END PUBLIC KEY-----`;

  const payload = await generateLoginPayload("ucsec", "ucsec", publicKeyPem);
  console.log(payload);
})();