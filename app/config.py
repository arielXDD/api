from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./api.db"
    jwt_secret: str = "solo-desarrollo-cambiar"
    access_token_minutes: int = 30
    openai_api_key: str | None = None
    stripe_secret_key: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

