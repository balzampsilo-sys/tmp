from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    telegram_bot_token: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24 * 7  # 1 week

    # S3 / Yandex Object Storage
    s3_endpoint: str = "https://storage.yandexcloud.net"
    s3_bucket: str = "srs-platform-cards"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Claude API (for AI card generation)
    anthropic_api_key: str = ""

    # FSRS desired retention (0-1)
    target_retention: float = 0.9

    # Max new cards per day per user (free tier)
    free_new_cards_per_day: int = 20
    pro_new_cards_per_day: int = 200


settings = Settings()
