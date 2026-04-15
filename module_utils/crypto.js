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
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAqwhoFjzZZWTAUIeWz6lW
cPJvyOqy2AzRuEdIXJCZZWG0Z/c73OZ+NugJYhEX9vWtKf7iX+wwPArd/6u7qU2v
CDr8kqQ0iLkQ1v/kGIQKoXqsRdQCEmWJtkZvhbqtce5cmAyP4UAQgxvSYPuf748L
5BNzOe3GefDdXj74O18I/6IGZx/2XeEGN3gHZIF6IdhFx4ee0OpqVEif3sG8BSsk
yEIb0Or98mMQiMUfat0VF40wqsjWgUu4mj6kdvpUX/NOhsJ9DKtxOuuRDocegCaH
m23Qfg/xB/pZKClAMD1L3MNkYenfjUpGDE+wMMjH3+SU8QrgZZolPf3lznDjSjSW
eg6iD6f79pzcO2Tp0PgS0mikJ8sDhfGzyvcCiGiYr/iGaUOgPnIQ6gjSXcoqwXDS
Qb3Er1wVq3J8SPErwiE828ea8CyzRx1o2SS290GRI3Wv77C5gz8IXUNcZ5vFWfw8
DTyIBT8fhJnSNvYvKiXcUlPkk5J1JkUPuZPcUVR14HIR0rzALehNF/DP30wbEg7U
OMWhoHOKMmeOjjvZi2Wuc1eFq0CHMx/dHisAwk86iz88UPZYYxPioePRm3gdNAqE
Tn/WmXQWAUn7PeG9/PmzCgkPc/9FqoTBnaJcQZVmu7gl+h+LemMVI/q5Z1BfQW14
wI2QkyErR7DAc1hD7uLBRVUCAwEAAQ==
-----END PUBLIC KEY-----`;

  const payload = await generateLoginPayload("ucsec", "YourPasswordHere", publicKeyPem);
  console.log(payload);
})();