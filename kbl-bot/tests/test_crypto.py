"""Unit tests for CryptoService (AES-256-GCM + HMAC-SHA256)."""

import pytest
from core.exceptions import CryptoError
from core.security.crypto import CryptoService

# A valid 32-byte (64 hex char) test key
_MASTER_KEY = "a" * 64
_HMAC_SECRET = "b" * 64


@pytest.fixture
def crypto() -> CryptoService:
    """Return a CryptoService with deterministic test keys."""
    return CryptoService(master_key_hex=_MASTER_KEY, hmac_secret_hex=_HMAC_SECRET)


class TestEncryptDecrypt:
    """Tests for AES-256-GCM round-trip correctness."""

    def test_encrypt_returns_string(self, crypto: CryptoService) -> None:
        """encrypt() must return a non-empty string."""
        token = crypto.encrypt("hello")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_encrypt_decrypt_roundtrip(self, crypto: CryptoService) -> None:
        """decrypt(encrypt(x)) == x for arbitrary plaintext."""
        plaintext = "kakao_user_key_abc123"
        token = crypto.encrypt(plaintext)
        recovered = crypto.decrypt(token)
        assert recovered == plaintext

    def test_encrypt_produces_unique_tokens(self, crypto: CryptoService) -> None:
        """Two encryptions of the same plaintext must produce different tokens (random nonce)."""
        t1 = crypto.encrypt("same")
        t2 = crypto.encrypt("same")
        assert t1 != t2

    def test_decrypt_tampered_raises(self, crypto: CryptoService) -> None:
        """Decrypting tampered ciphertext must raise CryptoError."""
        token = crypto.encrypt("secure")
        tampered = token[:-4] + "XXXX"
        with pytest.raises(CryptoError):
            crypto.decrypt(tampered)

    def test_encrypt_empty_string(self, crypto: CryptoService) -> None:
        """Empty string must encrypt and decrypt without error."""
        token = crypto.encrypt("")
        assert crypto.decrypt(token) == ""

    def test_encrypt_unicode(self, crypto: CryptoService) -> None:
        """Unicode (Korean) characters must round-trip correctly."""
        plaintext = "안녕하세요 KBL 봇"
        assert crypto.decrypt(crypto.encrypt(plaintext)) == plaintext

    def test_encrypt_decrypt_with_aad_binding(self, crypto: CryptoService) -> None:
        """Ciphertext bound to an AAD (e.g. user HMAC) must fail decryption if AAD differs."""
        aad_user_a = crypto.hmac_sha256("user_a")
        aad_user_b = crypto.hmac_sha256("user_b")
        token = crypto.encrypt("secret_user_key", aad=aad_user_a)
        assert crypto.decrypt(token, aad=aad_user_a) == "secret_user_key"
        with pytest.raises(CryptoError):
            crypto.decrypt(token, aad=aad_user_b)


class TestHmac:
    """Tests for HMAC-SHA256 keyed hashing."""

    def test_hmac_returns_64_hex_chars(self, crypto: CryptoService) -> None:
        """HMAC output must be exactly 64 hex characters."""
        digest = crypto.hmac_sha256("test")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_hmac_deterministic(self, crypto: CryptoService) -> None:
        """Same input must always produce the same HMAC digest."""
        assert crypto.hmac_sha256("user_key") == crypto.hmac_sha256("user_key")

    def test_hmac_different_inputs(self, crypto: CryptoService) -> None:
        """Different inputs must produce different digests."""
        assert crypto.hmac_sha256("key_a") != crypto.hmac_sha256("key_b")

    def test_hmac_empty_string(self, crypto: CryptoService) -> None:
        """Empty string must produce a valid 64-char digest."""
        digest = crypto.hmac_sha256("")
        assert len(digest) == 64


class TestCryptoServiceInit:
    """Tests for CryptoService key validation on instantiation."""

    def test_invalid_hex_key_raises(self) -> None:
        """Non-hex master key must raise CryptoError."""
        with pytest.raises(CryptoError):
            CryptoService(master_key_hex="not-hex!!", hmac_secret_hex=_HMAC_SECRET)

    def test_wrong_length_key_raises(self) -> None:
        """A hex key with wrong length must raise CryptoError."""
        short_key = "aa" * 16  # 16 bytes, not 32
        with pytest.raises(CryptoError):
            CryptoService(master_key_hex=short_key, hmac_secret_hex=_HMAC_SECRET)
