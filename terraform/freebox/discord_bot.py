import io
import json
import subprocess
import traceback

import discord
import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# also export .env vars to the process env, so the terraform subprocess inherits them
load_dotenv()


class Settings(
    BaseSettings,
    env_file=".env",
    extra="ignore",
):
    DISCORD_BOT_TOKEN: str
    TERRAFORM_PATH: str = "."
    TERRAFORM_COMMAND: str = "tofu"
    USERS_DEFINITION_PATH: str = "users.yml"
    ALLOWED_IPS: str = "192.168.27.64/27"
    DNS: str = "192.168.27.65"


settings = Settings()  # type: ignore[call-arg]

with open(settings.USERS_DEFINITION_PATH) as f:
    users = yaml.safe_load(f)


def get_vpn_users() -> dict[str, str]:
    """Return login -> wireguard config, read from the `vpn_users` terraform output."""
    result = subprocess.run(
        [
            settings.TERRAFORM_COMMAND,
            f"-chdir={settings.TERRAFORM_PATH}",
            "output",
            "-json",
            "vpn_users",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(result.stdout)


def transform_config(config: str, allowed_ips: str, dns: str) -> str:
    lines = []
    for line in config.splitlines():
        stripped = line.strip()
        if stripped.startswith("AllowedIPs"):
            lines.append(f"AllowedIPs = {allowed_ips}")
        elif stripped.startswith("DNS"):
            lines.append(f"DNS = {dns}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if not isinstance(message.channel, discord.DMChannel):
        return

    if message.content.strip() != "!vpn":
        return

    login_prefix = users.get(message.author.id)
    if login_prefix is None:
        return

    try:
        vpn_users = get_vpn_users()
        matches = {
            login: config
            for login, config in vpn_users.items()
            if login.startswith(login_prefix)
        }

        if not matches:
            await message.reply(f"No VPN config found for `{login_prefix}`.")
            return

        files = [
            discord.File(
                io.BytesIO(
                    transform_config(
                        config, settings.ALLOWED_IPS, settings.DNS
                    ).encode()
                ),
                filename=f"{login}.conf",
            )
            for login, config in matches.items()
        ]
        await message.reply(files=files)
    except Exception as e:
        await message.reply(f"```\n{e!r}\n```")
        print(f"Error handling message {message}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    bot.run(settings.DISCORD_BOT_TOKEN)
