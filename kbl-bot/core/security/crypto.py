"""AES-256-GCM encryption and HMAC-SHA256 utilities for user data protection."""

import base64
import hashlib
import hmac
import os
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.exceptions import CryptoError

NONCE_SIZE: Final[int] = 12  # 96-bit nonce for AES-GCM
KEY_SIZE: Final[int] = 32    # 256-bit key


class CryptoService:
    """Provides AES-256-GCM encryption/decryption and HMAC-SHA256 keyed hashing."""

    def __init__(self, master_key_hex: str, hmac_secret_hex: str) -> None:
        """
        Initialise CryptoService.

        Args:
            master_key_hex: Hex-encoded 32-byte AES master key.
            hmac_secret_hex: Hex-encoded secret used for HMAC-SHA256.

        Raises:
            CryptoError: If either key cannot be decoded or has the wrong length.
        """
        try:
            master_bytes = bytes.fromhex(master_key_hex)
        except ValueError as exc:
            raise CryptoError("master_encryption_key is not valid hex") from exc

        if len(master_bytes) != KEY_SIZE:
            raise CryptoError(
                f"master_encryption_key must be {KEY_SIZE} bytes ({KEY_SIZE * 2} hex chars), "
                f"got {len(master_bytes)} bytes"
            )

        if not hmac_secret_hex or not hmac_secret_hex.strip():
            raise CryptoError("hmac_secret_key must not be empty")
        try:
            hmac_bytes = bytes.fromhex(hmac_secret_hex)
        except ValueError:
            hmac_bytes = hmac_secret_hex.encode("utf-8")

        self._aesgcm = AESGCM(master_bytes)
        self._hmac_secret = hmac_bytes

    def encrypt(self, plaintext: str, aad: str | None = None) -> str:
        """
        Encrypt a UTF-8 string using AES-256-GCM.

        The returned ciphertext is base64url-encoded and contains
        the random nonce prepended to the cipher bytes.

        Args:
            plaintext: String to encrypt.
            aad: Optional Associated Authenticated Data (e.g. user HMAC) to bind ciphertext.

        Returns:
            Base64url-encoded string: ``nonce || ciphertext``.

        Raises:
            CryptoError: If encryption fails.
        """
        if not isinstance(plaintext, str):
            raise CryptoError("plaintext must be a str")
        try:
            nonce = os.urandom(NONCE_SIZE)
            aad_bytes = aad.encode("utf-8") if aad is not None else None
            ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad_bytes)
            return base64.urlsafe_b64encode(nonce + ct).decode("ascii")
        except Exception as exc:
            raise CryptoError(f"Encryption failed: {exc}") from exc

    def decrypt(self, token: str, aad: str | None = None) -> str:
        """
        Decrypt a token produced by :meth:`encrypt`.

        Args:
            token: Base64url-encoded ``nonce || ciphertext`` string.
            aad: Optional Associated Authenticated Data bound during encryption.

        Returns:
            Original plaintext string.

        Raises:
            CryptoError: If decryption fails (wrong key, tampered data, etc.).
        """
        try:
            raw = base64.urlsafe_b64decode(token)
            if len(raw) < NONCE_SIZE + 16:
                raise CryptoError("Ciphertext token is too short")
            nonce, ct = raw[:NONCE_SIZE], raw[NONCE_SIZE:]
            aad_bytes = aad.encode("utf-8") if aad is not None else None
            plaintext = self._aesgcm.decrypt(nonce, ct, aad_bytes)
            return plaintext.decode("utf-8")
        except CryptoError:
            raise
        except Exception as exc:
            raise CryptoError(f"Decryption failed: {exc}") from exc

    def hmac_sha256(self, data: str) -> str:
        """
        Compute HMAC-SHA256 of *data* using the configured secret.

        Args:
            data: String to hash.

        Returns:
            64-character lowercase hex digest.

        Raises:
            CryptoError: If *data* is not a non-empty string.
        """
        if not isinstance(data, str):
            raise CryptoError("data must be a str")
        digest = hmac.new(
            self._hmac_secret,
            data.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        return digest  # 64 hex chars
