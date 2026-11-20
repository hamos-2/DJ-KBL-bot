"""Unit tests for P2 OCI 952 MiB hardening & runtime config safeguards."""

from unittest.mock import MagicMock

import pytest

from apps.kakao.router import _resolve_public_base_url, _verify_skill_secret
from core.config import get_settings
from core.security.crypto import CryptoService
from services.content.lineup_board import (
    _BOARD_IMAGE_MEMORY_CACHE,
    _MAX_BOARD_IMAGE_CACHE_BYTES,
    _load_font,
    get_cached_board_image,
    invalidate_lineup_caches,
    set_cached_board_image,
)
from services.user.service import UserService


def test_user_service_lru_cache_bounded_eviction() -> None:
    """UserService LRU cache evicts oldest entries without wiping hot entries."""
    crypto = CryptoService("a" * 64, "b" * 64)
    svc = UserService(crypto=crypto)
    svc._USER_CACHE_MAX = 3

    u1, u2, u3, u4 = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    svc._cache_put("h1", u1)
    svc._cache_put("h2", u2)
    svc._cache_put("h3", u3)
    # Access h1 so h2 becomes LRU
    svc._cache_put("h1", u1)
    svc._cache_put("h4", u4)

    assert list(svc._user_cache.keys()) == ["h3", "h1", "h4"]


def test_board_image_memory_cache_respects_byte_budget() -> None:
    """Board image cache enforces byte budget and LRU order for 952 MiB OCI RAM."""
    invalidate_lineup_caches()
    chunk = b"x" * (6 * 1024 * 1024)  # 6 MiB each -> max 2 fit under 16 MiB
    set_cached_board_image("sig1", chunk)
    set_cached_board_image("sig2", chunk)
    assert get_cached_board_image("sig1") is not None  # promotes sig1

    set_cached_board_image("sig3", chunk)
    assert "sig2" not in _BOARD_IMAGE_MEMORY_CACHE
    assert "sig1" in _BOARD_IMAGE_MEMORY_CACHE
    assert "sig3" in _BOARD_IMAGE_MEMORY_CACHE
    total = sum(len(v) for v in _BOARD_IMAGE_MEMORY_CACHE.values())
    assert total <= _MAX_BOARD_IMAGE_CACHE_BYTES
    invalidate_lineup_caches()


def test_load_font_uses_lru_cache() -> None:
    """Repeated _load_font lookups hit the lru_cache instead of re-parsing TTF files."""
    _load_font.cache_clear()
    f1 = _load_font(22, bold=True)
    f2 = _load_font(22, bold=True)
    assert f1 is f2
    assert _load_font.cache_info().hits >= 1


def test_resolve_public_base_url_and_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """_resolve_public_base_url honors PUBLIC_BASE_URL and forwarded hosts; _verify_skill_secret validates."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://kbl.example.com/")
    monkeypatch.setenv("KAKAO_SKILL_SECRET", "top-secret-key")
    get_settings.cache_clear()
    try:
        assert _resolve_public_base_url(None) == "https://kbl.example.com"
        req = MagicMock()
        req.headers = {"x-forwarded-host": "bot.example.com"}
        assert _resolve_public_base_url(req) == "https://bot.example.com"

        assert _verify_skill_secret("top-secret-key") is True
        assert _verify_skill_secret("wrong") is False
        assert _verify_skill_secret(None) is False
    finally:
        get_settings.cache_clear()
