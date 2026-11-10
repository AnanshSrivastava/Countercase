from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root when running from a checkout (apps/api/app/settings.py). In Docker, FIXTURES_DIR is set.
_HERE = Path(__file__).resolve()
_DEFAULT_FIXTURES = _HERE.parents[3] / "fixtures" if len(_HERE.parents) > 3 else Path("/fixtures")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://recoup:recoup@localhost:5432/recoup"
    hindsight_url: str = "http://localhost:8888"
    web_origin: str = "http://localhost:3000"
    fixtures_dir: Path = _DEFAULT_FIXTURES
    # Agent wiring (owner: Shivansh). dispute_source auto = core DB, else fixtures when DB is down.
    dispute_source: str = "auto"  # auto | core | fixtures
    memory_backend: str = "inmemory"  # inmemory | hindsight
    memory_seed: str = "demo"  # inmemory only: demo = 3 cases | full = data/seed/history.json

    # Stripe (test mode). Webhooks are rejected with 503 while the secret is unset.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # PayPal (sandbox only). Webhooks are rejected with 503 while PAYPAL_WEBHOOK_ID is unset,
    # unless demo tools are on and verification is explicitly disabled (local fixtures only).
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_verify_webhooks: bool = True

    # Drafting LLM (Anthropic Messages API). Unset = deterministic template claims.
    llm_api_key: str = ""
    llm_model_draft: str = ""

    # Customer hashing (IMPROVEMENTS #7) and the single demo seller.
    customer_hash_salt: str = "dev-only-salt"
    default_seller_id: str = "sel_demo"

    # Demo-only tools (simulate a bank outcome). Off unless DEMO_TOOLS=1.
    demo_tools: bool = False

    # Deadline alerts (72h / 24h / 6h). Without SMTP they are stored as labelled SIMULATED emails.
    # ALERTS_INTERVAL_SECONDS > 0 starts a background check; 0 = only POST /core/alerts/run checks.
    alerts_interval_seconds: int = 0
    alert_email_to: str = ""
    alert_email_from: str = "recoup@localhost"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Seller uploads (Phase 3). In Docker UPLOAD_DIR points at a named volume.
    upload_dir: Path = _HERE.parents[1] / "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024


settings = Settings()
