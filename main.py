import asyncio
import logging
from typing import Any, Optional, Dict
import re
import aiohttp
from urllib.parse import urlparse, parse_qs

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
TOKEN = "7624797816:AAG6IBjSwLo1Rz-Tx8rKw74lGxvm8tN1j0M"
STEAM_API_KEY = "6450F125515588614814C4A636002A51"  # Replace with your Steam API key
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

# Steam URL patterns
STEAM_PATTERNS = [
    r"https?:\/\/steamcommunity\.com\/(?:profiles|id)\/[a-zA-Z0-9_-]+\/?",
    r"https?:\/\/steamcommunity\.com\/(?:profiles|id)\/[a-zA-Z0-9_-]+\/(?:games|inventory|screenshots|videos|workshop)\/?",
    r"https?:\/\/store\.steampowered\.com\/app\/\d+\/?.*",
]


class SteamAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.steampowered.com"

    async def get_player_summary(self, steam_id: str) -> Optional[Dict]:
        """Get player summary from Steam API."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/ISteamUser/GetPlayerSummaries/v2/"
            params = {
                "key": self.api_key,
                "steamids": steam_id
            }

            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['response']['players'][0] if data['response']['players'] else None
                    return None
            except Exception as e:
                logging.error(f"Error fetching player summary: {e}")
                return None

    async def get_owned_games(self, steam_id: str) -> Optional[Dict]:
        """Get player's owned games."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/IPlayerService/GetOwnedGames/v1/"
            params = {
                "key": self.api_key,
                "steamid": steam_id,
                "include_appinfo": 1,
                "include_played_free_games": 1
            }

            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
            except Exception as e:
                logging.error(f"Error fetching owned games: {e}")
                return None

    async def resolve_vanity_url(self, vanity_url: str) -> Optional[str]:
        """Convert vanity URL to Steam ID."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/ISteamUser/ResolveVanityURL/v1/"
            params = {
                "key": self.api_key,
                "vanityurl": vanity_url
            }

            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['response'].get('steamid')
                    return None
            except Exception as e:
                logging.error(f"Error resolving vanity URL: {e}")
                return None


steam_api = SteamAPI(STEAM_API_KEY)


def extract_steam_id(url: str) -> Optional[str]:
    """Extract Steam ID or vanity URL from profile link."""
    path = urlparse(url).path
    parts = [p for p in path.split('/') if p]

    if len(parts) >= 2:
        if parts[0] == 'profiles':
            return parts[1]
        elif parts[0] == 'id':
            return parts[1]
    return None


def format_player_data(player_data: Dict, games_data: Optional[Dict] = None) -> str:
    """Format player data into readable text."""
    status_codes = {
        0: "Offline",
        1: "Online",
        2: "Busy",
        3: "Away",
        4: "Snooze",
        5: "Looking to Trade",
        6: "Looking to Play"
    }

    text = []
    text.append("📊 Steam Profile Information:")
    text.append(f"👤 Name: {player_data.get('personaname', 'N/A')}")
    text.append(f"🆔 Steam ID: {player_data.get('steamid', 'N/A')}")
    text.append(f"📍 Status: {status_codes.get(player_data.get('personastate', 0), 'Unknown')}")

    if player_data.get('realname'):
        text.append(f"📝 Real Name: {player_data['realname']}")

    if player_data.get('loccountrycode'):
        text.append(f"🌍 Country: {player_data['loccountrycode']}")

    if player_data.get('timecreated'):
        from datetime import datetime
        created = datetime.fromtimestamp(player_data['timecreated'])
        text.append(f"📅 Account Created: {created.strftime('%Y-%m-%d')}")

    if games_data and 'game_count' in games_data.get('response', {}):
        text.append(f"🎮 Games Owned: {games_data['response']['game_count']}")

    text.append(f"\n🔗 Profile URL: {player_data.get('profileurl', 'N/A')}")

    return "\n".join(text)


def is_valid_steam_url(text: str) -> bool:
    """Check if the text contains a valid Steam URL."""
    for pattern in STEAM_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


@router.message(Command("start"))
async def cmd_start(message: Message) -> Any:
    """Handle the /start command."""
    await message.answer(
        "👋 Welcome! I can help you get information about Steam profiles.\n\n"
        "Just send me a Steam profile link and I'll fetch the available information!"
    )


@router.message(F.text)
async def handle_text(message: Message) -> Any:
    """Handle incoming text messages."""
    if not message.text:
        await message.answer("Please send a text message containing a Steam profile link.")
        return

    if not is_valid_steam_url(message.text):
        await message.answer(
            "❌ This doesn't look like a valid Steam link.\n\n"
            "Please send a valid Steam community profile link."
        )
        return

    # Show processing message
    processing_msg = await message.answer("🔄 Processing Steam profile...")

    try:
        # Extract Steam ID or vanity URL
        steam_id_or_vanity = extract_steam_id(message.text)
        if not steam_id_or_vanity:
            await processing_msg.edit_text("❌ Couldn't extract Steam ID from the URL.")
            return

        # If it's a vanity URL, resolve it to Steam ID
        if "/id/" in message.text:
            steam_id = await steam_api.resolve_vanity_url(steam_id_or_vanity)
            if not steam_id:
                await processing_msg.edit_text("❌ Couldn't resolve vanity URL to Steam ID.")
                return
        else:
            steam_id = steam_id_or_vanity

        # Fetch player data
        player_data = await steam_api.get_player_summary(steam_id)
        if not player_data:
            await processing_msg.edit_text("❌ Couldn't fetch player data.")
            return

        # Fetch owned games data
        games_data = await steam_api.get_owned_games(steam_id)

        # Format and send the response
        formatted_data = format_player_data(player_data, games_data)
        await processing_msg.edit_text(formatted_data)

    except Exception as e:
        logging.error(f"Error processing Steam profile: {e}")
        await processing_msg.edit_text("❌ An error occurred while processing the Steam profile.")


async def main() -> None:
    # Register the router
    dp.include_router(router)

    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())