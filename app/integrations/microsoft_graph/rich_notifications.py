from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

_PEM_CERT_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----",
    re.DOTALL,
)
_PEM_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA )?PRIVATE KEY-----.+?-----END (?:RSA )?PRIVATE KEY-----",
    re.DOTALL,
)


class RichNotificationError(Exception):
    pass


def _looks_like_filesystem_path(text: str) -> bool:
    if len(text) > 512 or "\n" in text or "-----BEGIN" in text:
        return False
    lowered = text.lower()
    if lowered.endswith((".pem", ".crt", ".cer", ".key", ".pub")):
        return True
    return text.startswith(("/", "./", "../", "~/")) or ("/" in text and " " not in text)


def _normalize_secret_text(value: str) -> str:
    """Strip whitespace/quotes and expand file paths / base64-wrapped PEM."""
    text = value.strip().strip('"').strip("'").strip()
    if not text:
        return text

    if _looks_like_filesystem_path(text):
        path = Path(text).expanduser()
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()

    # Common .env pattern: base64(PEM) so newlines don't break parsing.
    if "-----BEGIN" not in text:
        try:
            decoded = base64.b64decode("".join(text.split()), validate=True)
            as_text = decoded.decode("utf-8", errors="ignore")
            if "-----BEGIN" in as_text:
                return as_text.strip()
        except Exception:
            pass

    return text


def certificate_to_base64(certificate_pem_or_b64: str) -> str:
    """Return Graph-ready base64 of an X.509 certificate DER."""
    text = _normalize_secret_text(certificate_pem_or_b64)

    pem_match = _PEM_CERT_RE.search(text)
    if pem_match:
        cert = x509.load_pem_x509_certificate(pem_match.group(0).encode("utf-8"))
        return base64.b64encode(cert.public_bytes(Encoding.DER)).decode("ascii")

    # base64-encoded DER certificate
    try:
        compact = "".join(text.split())
        der = base64.b64decode(compact, validate=True)
        x509.load_der_x509_certificate(der)
        return compact
    except Exception as exc:
        raise RichNotificationError(
            "GRAPH_NOTIFICATION_CERTIFICATE must be PEM, base64(PEM), "
            "base64-encoded DER X.509, or a path to a .crt/.pem file"
        ) from exc


def load_private_key(private_key_pem: str):
    text = _normalize_secret_text(private_key_pem)
    pem_match = _PEM_KEY_RE.search(text)
    if not pem_match:
        raise RichNotificationError(
            "GRAPH_NOTIFICATION_PRIVATE_KEY must be a PEM private key, "
            "base64(PEM), or a path to a .key/.pem file"
        )
    return serialization.load_pem_private_key(pem_match.group(0).encode("utf-8"), password=None)


def public_key_matches_certificate(certificate_pem_or_b64: str, private_key_pem: str) -> bool:
    """Best-effort sanity check that the private key belongs to the certificate."""
    try:
        b64 = certificate_to_base64(certificate_pem_or_b64)
        cert = x509.load_der_x509_certificate(base64.b64decode(b64))
        private_key = load_private_key(private_key_pem)
        cert_public = cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        key_public = private_key.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
        return cert_public == key_public
    except Exception:
        return False


def decrypt_encrypted_content(
    *,
    data: str,
    data_key: str,
    data_signature: str,
    private_key_pem: str,
) -> dict[str, Any]:
    """
    Decrypt Graph change-notification encryptedContent.

    Steps follow Microsoft docs: RSA-OAEP-SHA1 unwrap of dataKey, HMAC-SHA256
    integrity check, then AES-CBC with IV = first 16 bytes of the symmetric key.
    """
    private_key = load_private_key(private_key_pem)
    try:
        encrypted_symmetric_key = base64.b64decode(data_key)
        encrypted_payload = base64.b64decode(data)
        expected_signature = base64.b64decode(data_signature)
    except Exception as exc:
        raise RichNotificationError("Invalid base64 in encryptedContent") from exc

    try:
        symmetric_key = private_key.decrypt(
            encrypted_symmetric_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None,
            ),
        )
    except Exception as exc:
        raise RichNotificationError("Failed to decrypt dataKey with private key") from exc

    actual_signature = hmac.new(symmetric_key, encrypted_payload, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise RichNotificationError("encryptedContent dataSignature mismatch")

    if len(symmetric_key) < 16:
        raise RichNotificationError("Decrypted symmetric key is too short")

    iv = symmetric_key[:16]
    cipher = Cipher(algorithms.AES(symmetric_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    try:
        padded = decryptor.update(encrypted_payload) + decryptor.finalize()
        plaintext = _pkcs7_unpad(padded)
    except Exception as exc:
        raise RichNotificationError("Failed to decrypt encryptedContent data") from exc

    try:
        parsed = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise RichNotificationError("Decrypted content is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise RichNotificationError("Decrypted content is not a JSON object")
    return parsed


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise RichNotificationError("Empty decrypted payload")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16 or pad_len > len(data):
        raise RichNotificationError("Invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise RichNotificationError("Invalid PKCS7 padding")
    return data[:-pad_len]
