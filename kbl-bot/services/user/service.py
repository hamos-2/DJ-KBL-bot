"""User domain service — registration, HMAC lookup, encrypt/decrypt."""

import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import User
from core.exceptions import UserNotFoundError
from core.logging import get_logger
from core.security.crypto import CryptoService

logger = get_logger("service.user")


class UserService:
    """Handles user registration and secure lookup by KakaoTalk user key."""

    def __init__(self, crypto: CryptoService) -> None:
        """
        Initialise UserService.

        Args:
            crypto: Configured CryptoService instance.
        """
        self._crypto = crypto
        self._user_cache: dict[str, User] = {}

    async def get_or_create(
        self,
        db: AsyncSession,
        kakao_user_key: str,
        nickname: Optional[str] = None,
        favorite_team: Optional[str] = None,
    ) -> tuple[User, bool]:
        """
        Return an existing user or atomically create a new one (concurrency-safe).

        The raw *kakao_user_key* is stored encrypted with its HMAC bound as AAD;
        the HMAC digest is used as the lookup index so plaintext is never stored.

        Args:
            db: Async SQLAlchemy session.
            kakao_user_key: Raw KakaoTalk botUserKey string.
            nickname: Optional display name to set on creation.
            favorite_team: Optional favourite team code to set on creation.

        Returns:
            Tuple of (User, created) where *created* is True for new users.
        """
        key_hmac = self._crypto.hmac_sha256(kakao_user_key)
        cached_user = self._user_cache.get(key_hmac)
        if cached_user is not None:
            return cached_user, False

        stmt = select(User).where(User.kakao_user_key_hmac == key_hmac)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is not None:
            logger.debug("Existing user found", hmac_prefix=key_hmac[:8])
            if len(self._user_cache) >= 5000:
                self._user_cache.clear()
            self._user_cache[key_hmac] = user
            return user, False

        encrypted_key = self._crypto.encrypt(kakao_user_key, aad=key_hmac)
        now = datetime.now(UTC)
        new_id = uuid.uuid4()

        upsert_stmt = (
            pg_insert(User)
            .values(
                id=new_id,
                kakao_user_key_hmac=key_hmac,
                encrypted_kakao_user_key=encrypted_key,
                key_version=1,
                nickname=nickname,
                favorite_team=favorite_team,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["kakao_user_key_hmac"])
        )
        insert_res = await db.execute(upsert_stmt)
        await db.flush()

        result = await db.execute(stmt)
        user = result.scalar_one()
        created = bool(insert_res.rowcount and insert_res.rowcount > 0)
        if created:
            logger.info("New user created", hmac_prefix=key_hmac[:8])
        if len(self._user_cache) >= 5000:
            self._user_cache.clear()
        self._user_cache[key_hmac] = user
        return user, created

    async def get_by_kakao_key(self, db: AsyncSession, kakao_user_key: str) -> User:
        """
        Look up a user by raw KakaoTalk key.

        Args:
            db: Async SQLAlchemy session.
            kakao_user_key: Raw KakaoTalk botUserKey string.

        Returns:
            The matching User ORM instance.

        Raises:
            UserNotFoundError: If no matching user exists.
        """
        key_hmac = self._crypto.hmac_sha256(kakao_user_key)
        stmt = select(User).where(User.kakao_user_key_hmac == key_hmac)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise UserNotFoundError(kakao_user_key)
        return user

    def decrypt_kakao_key(self, user: User) -> str:
        """
        Decrypt and return the original KakaoTalk user key for push delivery.

        Args:
            user: User ORM instance with encrypted_kakao_user_key set.

        Returns:
            Plaintext KakaoTalk botUserKey.
        """
        return self._crypto.decrypt(
            user.encrypted_kakao_user_key, aad=user.kakao_user_key_hmac
        )

    def get_hmac(self, kakao_user_key: str) -> str:
        """Return the HMAC-SHA256 digest of *kakao_user_key*."""
        return self._crypto.hmac_sha256(kakao_user_key)

    async def set_favorite_team(
        self, db: AsyncSession, kakao_user_key: str, favorite_team: Optional[str]
    ) -> User:
        """Update the user's favorite KBL team."""
        user, _ = await self.get_or_create(db, kakao_user_key)
        user.favorite_team = favorite_team
        user.updated_at = datetime.now(UTC)
        await db.flush()
        return user

