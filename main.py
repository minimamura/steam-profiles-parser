import asyncio
import logging
from pprint import pprint
from typing import Any, Optional, Dict
import re
import aiohttp
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message

logging.basicConfig(level=logging.INFO)
#
TOKEN = "7624797816:AAG6IBjSwLo1Rz-Tx8rKw74lGxvm8tN1j0M"
STEAM_API_KEY = "6450F125515588614814C4A636002A51"
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

STEAM_PATTERNS = [
    r"https?:\/\/steamcommunity\.com\/(?:profiles|id)\/[a-zA-Z0-9_-]+\/?",
    r"https?:\/\/steamcommunity\.com\/(?:profiles|id)\/[a-zA-Z0-9_-]+\/(?:games|inventory|screenshots|videos|workshop)\/?",
    r"https?:\/\/store\.steampowered\.com\/app\/\d+\/?.*",
]

STATUS_CODES = {
    0: "Offline",
    1: "Online",
    2: "Busy",
    3: "Away",
    4: "Snooze",
    5: "Looking to Trade",
    6: "Looking to Play"
}


class SteamAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.steampowered.com"
        logging.info(f"SteamAPI initialized with key {self.api_key[:5]}...")  # Logging part of the API key for tracking

    async def get_player_summary(self, steam_id: str) -> Optional[Dict]:
        logging.info(f"Fetching player summary for Steam ID: {steam_id}")
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
                        logging.debug(f"Player summary data: {data}")
                        return data['response']['players'][0] if data['response']['players'] else None
                    logging.warning(f"Failed to fetch player summary: Status code {response.status}")
                    return None
            except Exception as e:
                logging.error(f"Error fetching player summary for {steam_id}: {e}")
                return None

    async def get_owned_games(self, steam_id: str) -> Optional[Dict]:
        logging.info(f"Fetching owned games for Steam ID: {steam_id}")
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
                        data = await response.json()
                        logging.debug(f"Owned games data: {data}")
                        return data
                    logging.warning(f"Failed to fetch owned games: Status code {response.status}")
                    return None
            except Exception as e:
                logging.error(f"Error fetching owned games for {steam_id}: {e}")
                return None

    async def resolve_vanity_url(self, vanity_url: str) -> Optional[str]:
        logging.info(f"Resolving vanity URL: {vanity_url}")
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/ISteamUser/ResolveVanityURL/v0001/"
            params = {
                "key": self.api_key,
                "vanityurl": vanity_url
            }
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        logging.debug(f"Resolved Steam ID: {data}")
                        return data['response'].get('steamid')
                    logging.warning(f"Failed to resolve vanity URL: Status code {response.status}")
                    return None
            except Exception as e:
                logging.error(f"Error resolving vanity URL {vanity_url}: {e}")
                return None


class DotaBuffAPI:
    async def get_player_stats(self, steam_id: str) -> Optional[Dict]:
        logging.info(f"Fetching DotaBuff stats for Steam ID: {steam_id}")
        steam3_id = int(steam_id) // 2
        print(steam3_id)
        url = f"https://www.dotabuff.com/players/{steam3_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        logging.debug(f"Fetched DotaBuff page HTML: {html[:500]}...")  # Log first 500 chars of the HTML
                        return self._parse_dotabuff_page(html)
                    logging.warning(f"Failed to fetch DotaBuff data: Status code {response.status}")
                    return None
            except Exception as e:
                logging.error(f"Error fetching DotaBuff data for {steam3_id}: {e}")
                return None

    def _parse_dotabuff_page(self, html: str) -> Dict:
        logging.info("Parsing DotaBuff page HTML...")
        soup = BeautifulSoup(html, 'html.parser')
        stats = {}
        print(html)

        try:
            wins_element = soup.select_one('.header-content-secondary .wing.won')
            losses_element = soup.select_one('.header-content-secondary .wing.lost')

            if wins_element and losses_element:
                wins = int(wins_element.text.strip())
                losses = int(losses_element.text.strip())
                win_rate = round((wins / (wins + losses)) * 100, 2)
                stats['wins'] = wins
                stats['losses'] = losses
                stats['win_rate'] = win_rate
                logging.debug(f"Win rate: {win_rate}%")
            else:
                logging.warning("Unable to find win/loss data in DotaBuff page.")

            rank_element = soup.select_one('.rank-tier')
            if rank_element:
                stats['rank'] = rank_element.get('title', 'Unknown')
                logging.debug(f"Rank: {stats['rank']}")

            hero_table = soup.select('section.player-heroes table tr')
            if hero_table:
                most_played = []
                for i, row in enumerate(hero_table[1:4], 1):
                    cols = row.select('td')
                    if len(cols) >= 2:
                        hero_name = cols[0].text.strip()
                        matches = cols[1].text.strip()
                        most_played.append(f"{hero_name} ({matches} matches)")
                stats['most_played_heroes'] = most_played
                logging.debug(f"Most played heroes: {most_played}")

        except Exception as e:
            logging.error(f"Error parsing DotaBuff page: {e}")

        return stats


steam_api = SteamAPI(STEAM_API_KEY)
dotabuff_api = DotaBuffAPI()


def extract_steam_id(url: str) -> Optional[str]:
    logging.info(f"Extracting Steam ID from URL: {url}")
    path = urlparse(url).path
    parts = [p for p in path.split('/') if p]

    if len(parts) >= 2:
        if parts[0] == 'profiles':
            logging.debug(f"Extracted Steam ID: {parts[1]}")
            return parts[1]
        elif parts[0] == 'id':
            logging.debug(f"Extracted vanity URL: {parts[1]}")
            return parts[1]
    return None


def is_valid_steam_url(text: str) -> bool:
    logging.info(f"Validating Steam URL: {text}")
    for pattern in STEAM_PATTERNS:
        if re.search(pattern, text):
            logging.debug(f"Valid Steam URL: {text}")
            return True
    logging.warning(f"Invalid Steam URL: {text}")
    return False


def format_player_data(player_data: Dict, games_data: Optional[Dict] = None, dota_data: Optional[Dict] = None) -> str:
    logging.info("Formatting player data...")
    text = []
    text.append("📊 Steam Profile Information:")
    text.append(f"👤 Name: {player_data.get('personaname', 'N/A')}")
    text.append(f"🆔 Steam ID: {player_data.get('steamid', 'N/A')}")
    text.append(f"📍 Status: {STATUS_CODES.get(player_data.get('personastate', 0), 'Unknown')}")

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

    if dota_data:
        text.append("\n🎯 Dota 2 Statistics (via DotaBuff):")
        if 'rank' in dota_data:
            text.append(f"🏅 Rank: {dota_data['rank']}")
        if 'wins' in dota_data and 'losses' in dota_data:
            text.append(f"📈 Record: {dota_data['wins']}W - {dota_data['losses']}L")
            text.append(f"💯 Win Rate: {dota_data['win_rate']}%")
        if 'most_played_heroes' in dota_data:
            text.append("🦸 Most Played Heroes:")
            for hero in dota_data['most_played_heroes']:
                text.append(f"  • {hero}")

    text.append(f"\n🔗 Profile URL: {player_data.get('profileurl', 'N/A')}")
    return "\n".join(text)


@router.message(Command("start"))
async def cmd_start(message: Message) -> Any:
    logging.info(f"User started the bot: {message.from_user.id}")
    await message.answer(
        "👋 Welcome! I can help you get information about Steam profiles and Dota 2 statistics.\n\n"
        "Just send me a Steam profile link!"
    )


@router.message(F.text)
async def handle_text(message: Message) -> Any:
    logging.info(f"Received message from {message.from_user.id}: {message.text}")

    if not message.text:
        await message.answer("Please send a text message containing a Steam profile link.")
        return

    if not is_valid_steam_url(message.text):
        await message.answer("❌ This doesn't look like a valid Steam link.")
        return

    processing_msg = await message.answer("🔄 Processing Steam profile...")

    try:
        steam_id_or_vanity = extract_steam_id(message.text)
        if not steam_id_or_vanity:
            await processing_msg.edit_text("❌ Couldn't extract Steam ID from the URL.")
            return

        if "/id/" in message.text:
            steam_id = await steam_api.resolve_vanity_url(steam_id_or_vanity)
            if not steam_id:
                await processing_msg.edit_text("❌ Couldn't resolve vanity URL to Steam ID.")
                return
        else:
            steam_id = steam_id_or_vanity

        player_data, games_data, dota_data = await asyncio.gather(
            steam_api.get_player_summary(steam_id),
            steam_api.get_owned_games(steam_id),
            dotabuff_api.get_player_stats(steam_id)
        )

        if not player_data:
            await processing_msg.edit_text("❌ Couldn't fetch player data.")
            return
        pprint(dota_data)

        formatted_data = format_player_data(player_data, games_data, dota_data)
        await processing_msg.edit_text(formatted_data)

    except Exception as e:
        logging.error(f"Error processing profile: {e}")
        await processing_msg.edit_text("❌ An error occurred while processing the profile.")


async def main() -> None:
    logging.info("Bot started.")
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
                                                                  