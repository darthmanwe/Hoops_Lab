from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ball_dont_lie_api_key: str | None = os.getenv("BALLDONTLIE_API_KEY")
    cf_api_token: str | None = os.getenv("CLOUDFLARE_API_TOKEN")
    cf_account_id: str | None = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    d1_database_name: str = os.getenv("D1_DATABASE_NAME", "hoopslab-db")
