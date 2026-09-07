import hashlib
import hmac
import time
import traceback

import requests
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

# the Freebox API always returns exactly 5 dns slots, padded with empty strings
DNS_SLOTS = 5

DISCORD_API = "https://discord.com/api/v10"


class Settings(
    BaseSettings,
    env_file=".env",
    extra="ignore",
):
    TF_VAR_FREEBOX_TOKEN: str
    TF_VAR_FREEBOX_ENDPOINT: str
    DISCORD_BOT_TOKEN: str
    FREEBOX_DNS_SERVERS: str
    FREEBOX_DNS_DISCORD_CHANNEL_ID: int
    FREEBOX_APP_ID: str = "terraform-provider-freebox"
    FREEBOX_API_VERSION: str = "v16"
    FREEBOX_CHECK_INTERVAL: float = 30.0


settings = Settings()  # type: ignore[call-arg]

BASE_URL = "{}/api/{}".format(
    (
        settings.TF_VAR_FREEBOX_ENDPOINT.rstrip("/")
        if "://" in settings.TF_VAR_FREEBOX_ENDPOINT
        else f"https://{settings.TF_VAR_FREEBOX_ENDPOINT.rstrip('/')}"
    ),
    settings.FREEBOX_API_VERSION,
)

DESIRED_DNS = [
    server.strip()
    for server in settings.FREEBOX_DNS_SERVERS.split(",")
    if server.strip()
]


class FreeboxError(Exception):
    pass


def api_call(
    session: requests.Session,
    method: str,
    path: str,
    session_token: str | None = None,
    json: dict | None = None,
) -> dict:
    headers = {"X-Fbx-App-Auth": session_token} if session_token else {}
    response = session.request(
        method, f"{BASE_URL}{path}", headers=headers, json=json, timeout=10
    )
    payload = response.json()

    if not payload.get("success"):
        raise FreeboxError(
            f"{method} {path} failed: {payload.get('error_code')} {payload.get('msg')}"
        )
    return payload.get("result", {})


def open_session(session: requests.Session) -> str:
    challenge = api_call(session, "GET", "/login/")["challenge"]
    password = hmac.new(
        settings.TF_VAR_FREEBOX_TOKEN.encode(),
        challenge.encode(),
        hashlib.sha1,
    ).hexdigest()
    result = api_call(
        session,
        "POST",
        "/login/session/",
        json={"app_id": settings.FREEBOX_APP_ID, "password": password},
    )
    return result["session_token"]


def enforce_dns(
    session: requests.Session,
) -> tuple[list[str], list[str]] | None:
    """Set the DHCP dns servers if they differ, returning (old, new) on change."""
    session_token = open_session(session)

    config = api_call(session, "GET", "/dhcp/config/", session_token)
    current = [server for server in config.get("dns", []) if server]
    if current == DESIRED_DNS:
        return None

    padded = (DESIRED_DNS + [""] * DNS_SLOTS)[:DNS_SLOTS]
    api_call(
        session, "PUT", "/dhcp/config/", session_token, json={"dns": padded}
    )
    return current, DESIRED_DNS


def notify_discord(session: requests.Session, content: str) -> None:
    channel_id = settings.FREEBOX_DNS_DISCORD_CHANNEL_ID
    response = session.post(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
        json={"content": content},
        timeout=10,
    )
    response.raise_for_status()


def main() -> None:
    session = requests.Session()
    while True:
        try:
            change = enforce_dns(session)
            if change is not None:
                old, new = change
                message = (
                    f"Force set Freebox DNS servers from "
                    f"[{', '.join(old)}] -> [{', '.join(new)}]"
                )
                print(message)
                notify_discord(session, message)
        except Exception as e:
            print(f"Error enforcing DNS servers: {e}")
            traceback.print_exc()

        time.sleep(settings.FREEBOX_CHECK_INTERVAL)


if __name__ == "__main__":
    main()
