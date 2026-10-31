"""Domain exceptions for the KBL Bot backend."""


class KBLBotError(Exception):
    """Base exception for all KBL Bot domain errors."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message: str = user_message or message


class GameNotFoundError(KBLBotError):
    """Raised when a requested game does not exist."""

    def __init__(self, game_id: str) -> None:
        super().__init__(
            message=f"Game not found: {game_id}",
            user_message="요청한 경기 정보를 찾을 수 없습니다.",
        )


class ProviderError(KBLBotError):
    """Raised when the sports data provider returns an error or times out."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            message=f"Provider error: {detail}",
            user_message="일시적으로 데이터를 불러올 수 없습니다.",
        )


class PredictionClosedError(KBLBotError):
    """Raised when a user tries to predict after the game has started."""

    def __init__(self, game_id: str) -> None:
        super().__init__(
            message=f"Prediction closed for game: {game_id}",
            user_message="경기가 이미 시작되어 예측이 마감되었습니다.",
        )


class UserNotFoundError(KBLBotError):
    """Raised when a user record does not exist."""

    def __init__(self, kakao_user_key: str) -> None:
        super().__init__(
            message=f"User not found for key hash: {kakao_user_key[:8]}...",
            user_message="사용자 정보를 찾을 수 없습니다. 먼저 서비스를 시작해 주세요.",
        )


class CryptoError(KBLBotError):
    """Raised when encryption or decryption fails."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            message=f"Crypto error: {detail}",
            user_message="보안 처리 중 오류가 발생했습니다.",
        )


class StartupError(Exception):
    """Raised during application startup if a required resource is unavailable."""

    pass
