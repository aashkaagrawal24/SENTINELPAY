from functools import lru_cache
from typing import Literal

from pydantic import HttpUrl, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "staging", "production"] = "development"
    supabase_url: HttpUrl
    supabase_anon_key: SecretStr
    supabase_database_url: SecretStr
    supabase_server_secret: SecretStr | None = None
    frontend_url: HttpUrl = "http://localhost:3000"
    backend_url: HttpUrl = "http://localhost:8000"
    app_version: str = "4.2.0"
    groq_api_key: SecretStr | None = None
    nvidia_nim_api_key: SecretStr | None = None
    model_timeout_seconds: float = 30.0
    model_max_retries: int = 1
    groq_fast_model: str = "openai/gpt-oss-20b"
    groq_reasoning_model: str = "openai/gpt-oss-120b"
    nvidia_agent_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    nvidia_ultra_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    model_max_completion_tokens: int = 2048
    razorpay_test_key_id: str | None = None
    razorpay_test_key_secret: SecretStr | None = None
    razorpay_webhook_secret: SecretStr | None = None
    razorpay_api_url: str = "https://api.razorpay.com/v1"
    payment_timeout_seconds: float = 15.0
    campaign_scan_interval_minutes: int = 15
    campaign_inventory_pressure_threshold: int = 15
    campaign_weight_inventory_pressure: float = 0.30
    campaign_weight_conversion_gap: float = 0.25
    campaign_weight_demand_signal: float = 0.20
    campaign_weight_margin_room: float = 0.15
    campaign_weight_historical_lift: float = 0.10
    feature_external_market_intelligence: bool = True
    feature_contextual_bandit: bool = True
    feature_zk_budget_sufficiency: bool = True
    feature_multi_verifier: bool = True
    feature_b2b_procurement: bool = True
    feature_negotiation_simulator: bool = True
    feature_advanced_analytics: bool = True
    feature_privacy_stack: bool = True
    advanced_verification_threshold_minor: int = 50_000_000
    bls_mandate_signing_key: SecretStr | None = None
    bls_policy_signing_key: SecretStr | None = None
    bls_risk_signing_key: SecretStr | None = None

    @property
    def campaign_score_weights(self) -> dict[str, float]:
        return {
            "inventory_pressure": self.campaign_weight_inventory_pressure,
            "conversion_gap": self.campaign_weight_conversion_gap,
            "demand_signal": self.campaign_weight_demand_signal,
            "margin_room": self.campaign_weight_margin_room,
            "historical_lift": self.campaign_weight_historical_lift,
        }

    @property
    def jwks_url(self) -> str:
        return f"{str(self.supabase_url).rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        missing = sorted({str(item["loc"][0]).upper() for item in exc.errors()})
        raise RuntimeError("Invalid backend configuration; set: " + ", ".join(missing)) from exc
