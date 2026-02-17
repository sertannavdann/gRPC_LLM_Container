"""
Clash Royale Adapter - Player stats and battle log from Supercell API.

API docs: https://developer.clashroyale.com
Auth: Bearer token in Authorization header
Player tag: URL-encode '#' as '%23'
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from urllib.parse import quote

import aiohttp

from shared.adapters.base import BaseAdapter, AdapterConfig
from shared.adapters.registry import register_adapter
from shared.schemas.canonical import GamingProfile, GamingMatch

logger = logging.getLogger(__name__)

BASE_URL = "https://api.clashroyale.com/v1"


def _encode_tag(tag: str) -> str:
    """URL-encode player tag (#ABC → %23ABC)."""
    tag = tag.strip()
    if not tag.startswith("#"):
        tag = f"#{tag}"
    return quote(tag, safe="")


def _parse_battle_time(time_str: str) -> datetime:
    """Parse Clash Royale battle timestamp (yyyyMMddTHHmmss.000Z)."""
    try:
        return datetime.strptime(time_str, "%Y%m%dT%H%M%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return datetime.now(tz=timezone.utc)


@register_adapter(
    category="gaming",
    platform="clashroyale",
    display_name="Clash Royale",
    description="Player profile, trophies, and battle log from Clash Royale API",
    icon="\u2694\ufe0f",
    requires_auth=True,
    auth_type="api_key",
)
class ClashRoyaleAdapter(BaseAdapter[GamingProfile]):
    """Adapter for Clash Royale API (Supercell)."""

    category = "gaming"
    platform = "clashroyale"

    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        api_key = config.credentials.get("api_key", "")
        if not api_key:
            raise ValueError(
                "Clash Royale API key not configured (credentials.api_key)"
            )

        player_tag = config.settings.get("player_tag", "")
        if not player_tag:
            raise ValueError(
                "Player tag not configured (settings.player_tag). Example: #ABCDEF"
            )

        encoded_tag = _encode_tag(player_tag)
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        include_battlelog = config.settings.get("include_battlelog", True)

        result: Dict[str, Any] = {}

        async with aiohttp.ClientSession(headers=headers) as session:
            # Player profile
            async with session.get(
                f"{BASE_URL}/players/{encoded_tag}",
                timeout=aiohttp.ClientTimeout(total=config.timeout_seconds),
            ) as resp:
                if resp.status == 403:
                    raise ValueError(
                        "Clash Royale API: Access denied. Check your API key and IP whitelist."
                    )
                if resp.status == 404:
                    raise ValueError(f"Player tag not found: {player_tag}")
                if resp.status != 200:
                    body = await resp.text()
                    raise ValueError(f"Clash Royale API error {resp.status}: {body}")
                result["profile"] = await resp.json()

            # Battle log
            if include_battlelog:
                async with session.get(
                    f"{BASE_URL}/players/{encoded_tag}/battlelog",
                    timeout=aiohttp.ClientTimeout(total=config.timeout_seconds),
                ) as resp:
                    if resp.status == 200:
                        result["battlelog"] = await resp.json()

        return result

    def transform(self, raw_data: Dict[str, Any]) -> List[GamingProfile]:
        profile_data = raw_data.get("profile", {})
        if not profile_data:
            return []

        tag = profile_data.get("tag", "")
        stable_id = f"cr:{hashlib.md5(tag.encode()).hexdigest()[:12]}"

        # Parse battle log
        battles = raw_data.get("battlelog", [])
        match_list = [self._transform_battle(b) for b in battles[:25]]

        wins = profile_data.get("wins", 0)
        losses = profile_data.get("losses", 0)

        profile = GamingProfile(
            id=stable_id,
            username=profile_data.get("name", "Unknown"),
            platform_tag=tag,
            level=profile_data.get("expLevel", 0),
            trophies=profile_data.get("trophies", 0),
            wins=wins,
            losses=losses,
            games_played=profile_data.get("battleCount", wins + losses),
            clan_name=profile_data.get("clan", {}).get("name"),
            clan_tag=profile_data.get("clan", {}).get("tag"),
            arena=profile_data.get("arena", {}).get("name"),
            platform="clashroyale",
            metadata={
                "best_trophies": profile_data.get("bestTrophies", 0),
                "donations": profile_data.get("donations", 0),
                "donations_received": profile_data.get("donationsReceived", 0),
                "challenge_max_wins": profile_data.get("challengeMaxWins", 0),
                "challenge_cards_won": profile_data.get("challengeCardsWon", 0),
                "tournament_cards_won": profile_data.get("tournamentCardsWon", 0),
                "war_day_wins": profile_data.get("warDayWins", 0),
                "current_deck": [
                    card.get("name") for card in profile_data.get("currentDeck", [])
                ],
                "recent_battles": [m.to_dict() for m in match_list],
            },
        )

        return [profile]

    def _transform_battle(self, battle: Dict[str, Any]) -> GamingMatch:
        ts = _parse_battle_time(battle.get("battleTime", ""))
        battle_id = f"cr:b:{hashlib.md5(battle.get('battleTime', '').encode()).hexdigest()[:12]}"

        # Determine result from crowns
        team = battle.get("team", [{}])
        opponent = battle.get("opponent", [{}])
        team_crowns = team[0].get("crowns", 0) if team else 0
        opp_crowns = opponent[0].get("crowns", 0) if opponent else 0

        if team_crowns > opp_crowns:
            result = "win"
        elif team_crowns < opp_crowns:
            result = "loss"
        else:
            result = "draw"

        trophy_change = team[0].get("trophyChange", 0) if team else 0
        opp_tag = opponent[0].get("tag", "") if opponent else ""
        opp_name = opponent[0].get("name", "") if opponent else ""

        game_type = battle.get("type", "unknown")
        if "ladder" in game_type.lower() or "PvP" in game_type:
            game_type = "ladder"
        elif "challenge" in game_type.lower():
            game_type = "challenge"
        elif "tournament" in game_type.lower():
            game_type = "tournament"
        elif "friendly" in game_type.lower():
            game_type = "friendly"

        return GamingMatch(
            id=battle_id,
            timestamp=ts,
            game_type=game_type,
            result=result,
            trophies_change=trophy_change,
            opponent_tag=opp_tag,
            opponent_name=opp_name,
            platform="clashroyale",
            metadata={
                "arena": battle.get("arena", {}).get("name", ""),
                "deck_selection": battle.get("deckSelection", ""),
                "team_crowns": team_crowns,
                "opponent_crowns": opp_crowns,
            },
        )

    @classmethod
    def normalize_category_for_tools(cls, raw_category_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize gaming data for tool consumption."""
        return {
            "profiles": raw_category_data.get("profiles", []),
            "platforms": raw_category_data.get("platforms", []),
        }

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": False,
            "batch": False,
            "webhooks": False,
            "profile": True,
            "battlelog": True,
        }
