from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    dg_email: str = os.getenv("DG_EMAIL", "")
    dg_password: str = os.getenv("DG_PASSWORD", "")
    dg_login_url: str = os.getenv("DG_LOGIN_URL", "https://www.datagaffer.com/login")
    dg_goal_zone_url: str = os.getenv("DG_GOAL_ZONE_URL", "https://www.datagaffer.com/goal_zone")
    dg_win_outlook_url: str = os.getenv(
        "DG_WIN_OUTLOOK_URL", "https://www.datagaffer.com/outlooks#win-outlook"
    )
    dg_email_selector: str = os.getenv("DG_EMAIL_SELECTOR", "input[type='email']")
    dg_password_selector: str = os.getenv("DG_PASSWORD_SELECTOR", "input[type='password']")
    dg_submit_selector: str = os.getenv("DG_SUBMIT_SELECTOR", "button[type='submit']")
    app_env: str = os.getenv("APP_ENV", "dev")
    api_football_key: str = os.getenv("API_FOOTBALL_KEY", "") or os.getenv("APISPORTS_KEY", "")
    bot_api_key: str = os.getenv("BOT_API_KEY", "")


settings = Settings()
