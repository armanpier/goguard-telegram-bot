from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Bot
    BOT_TOKEN: str = Field(..., description="Telegram Bot Token from @BotFather")
    ADMIN_IDS: List[int] = Field(default_factory=list, description="Telegram User IDs with admin access")
    SUPPORT_USERNAME: str = Field(default="@vpn_support", description="Support contact username")
    REQUIRED_CHANNEL_ID: Optional[str] = Field(default=None, description="Mandatory channel ID or username (e.g. @channel)")

    # GoGuard Panel API 1.0
    GOGUARD_BASE_URL: str = Field(default="https://core.erfjab.com", description="Base URL of GoGuard Panel")
    GOGUARD_USERNAME: str = Field(..., description="Admin username for GoGuard Panel API")
    GOGUARD_PASSWORD: str = Field(..., description="Admin password for GoGuard Panel API")
    GOGUARD_SUB_URL_TEMPLATE: str = Field(
        default="{base_url}/sub/{username}",
        description="Template for building subscription URLs if not returned by API"
    )
    GOGUARD_TIMEOUT_SECONDS: float = Field(default=15.0, description="HTTP request timeout in seconds")

    # Database
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///bot.db", description="SQLAlchemy database connection URL")

    # Payment (Card-to-Card)
    CARD_NUMBER: str = Field(default="6037-9918-0000-0000", description="Bank card number for manual transfers")
    CARD_HOLDER: str = Field(default="مدیریت", description="Cardholder full name")
    CURRENCY_TITLE: str = Field(default="تومان", description="Currency title displayed to users")

    # Free Trial
    FREE_TRIAL_ENABLED: bool = Field(default=True, description="Enable free trial accounts")
    FREE_TRIAL_TRAFFIC_GB: float = Field(default=1.0, description="Traffic in GB for free trial")
    FREE_TRIAL_DURATION_DAYS: int = Field(default=1, description="Duration in days for free trial")

    # Referral Program
    REFERRAL_ENABLED: bool = Field(default=True, description="Enable referral program")
    REFERRAL_COMMISSION_PERCENT: int = Field(default=10, description="Commission percentage for referrals")

    # General
    DEFAULT_LANGUAGE: str = Field(default="fa", description="Default bot language (fa/en)")
    DEBUG: bool = Field(default=False, description="Debug mode")

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(item.strip()) for item in v.split(",") if item.strip()]
        if isinstance(v, int):
            return [v]
        return v

    @field_validator("GOGUARD_BASE_URL", mode="after")
    @classmethod
    def clean_base_url(cls, v: str) -> str:
        return v.rstrip("/")


settings = Settings()
