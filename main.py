from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass, field, replace
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote

import kitchen_raid as kitchen

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


def load_local_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        if not separator or not name:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


load_local_env()

DISCORD_TOKEN_VARIABLE = "DISCORD_BOT_TOKEN"
GOOGLE_API_KEY_VARIABLE = "GOOGLE_SHEETS_API_KEY"

SORTED_TABLE_SPREADSHEET_ID = "1ARPBJ2CWxQH9A3nnBo1Q2Cq8dtu8aiQyC-YrDJLs298"
TRACKING_SPREADSHEET_ID = "16UzU1AzInFLPL6d7fUERU5NpYpRvvw8wQpJyLhcDJXg"
PRECONFIGURED_SPREADSHEETS = [
    ("14sgMwoNaZGduy44M8EAJf8VpH7NQ_sIVXoJ10Ss4VPg", "위험한 초대"),
    (SORTED_TABLE_SPREADSHEET_ID, "[펄프] 진짜 위험한 초대"),
    (TRACKING_SPREADSHEET_ID, "추적! 오후3시!"),
    ("1M1mnu9C4Yb7HH5VSBwJjvuxP2v_87_89TNcbqQgnHvQ", "엠피리언 동창회 ~빛나던 청춘의 조각을 모아~"),
]
EXCLUDED_TABS = {"가나다순 정렬 백지시트", "공지"}
CHARACTERISTIC_NAMES = {"근력", "민첩", "정신", "건강", "외모", "교육", "크기", "지능", "행운", "이성"}

SKILL_BASE_VALUES = {
    "관찰력": 25, "듣기": 20, "은밀행동": 20, "심리학": 10,
    "자료조사": 20, "언어": 1, "예술/공예": 5, "설득": 10,
    "매혹": 15, "위협": 15, "말재주": 5, "응급처치": 30,
    "의학": 1, "정신분석": 1, "생존": 10, "추적": 10,
    "오컬트": 5, "역사": 5, "자연": 10, "과학": 1,
    "수사과학": 1, "감정": 5, "회계": 5, "법률": 5,
    "기계수리": 10, "전기수리": 10, "자동차운전": 20,
    "오르기": 20, "수영": 20, "사격": 20, "회피": 0,
    "근접전": 25, "고고학": 1, "인류학": 1, "변장": 5,
    "자물쇠따기": 1, "조종": 1, "손재주": 10, "항법": 10,
    "도약": 20, "승마": 5, "투척": 20, "신용": 0,
    "크툴루신화": 0, "폭파": 1,
}
# Used only for /기능판정's autocomplete and default-value fallback.
# Observation keeps using the sheet values and its separate selection logic.
CHECK_DEFAULT_SKILL_VALUES = dict(SKILL_BASE_VALUES)

CHEER_MESSAGES = [
    "파이팅~! 레레가 힘을 보탤게요!",
    "괜찮아요, 분명 잘할 수 있어요! 레레가 응원할게요!",
    "레레의 응원을 보낼게요! 힘내요~!",
    "너무 걱정하지 말아요. 레레가 곁에서 응원하고 있어요!",
    "작은 한 걸음도 멋진 시작이에요! 파이팅이에요!",
    "힘이 필요할 땐 레레를 불러주세요! 언제나 응원할게요!",
    "오늘도 충분히 잘하고 있어요! 레레가 힘을 보탤게요!",
    "아자~! 레레의 응원으로 기운이 났으면 좋겠어요!",
]
FLAT_WEBHOOK_NAME = "rere-flat-output"
FLAT_DISPLAY_NAME = "플랫"
FLAT_CHEER_MESSAGES = [
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 서두르지 말고, 할 수 있는 것부터 천천히 해나가면 괜찮습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 오늘은 작은 일 하나만 해내도 충분합니다. 차근차근 해보시죠.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 지금까지 잘해오셨으니 너무 걱정하지 않으셔도 됩니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 할 일을 작게 나누면 다음에 무엇을 할지 정하기 쉬워집니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 계획대로 되지 않는 부분은 우선순위를 조정해 다시 시작하시면 됩니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 충분히 쉬는 것도 다음 일을 이어가기 위한 과정입니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 결과를 모두 통제할 수는 없어도, 다음 행동은 선택할 수 있습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 완벽하게 준비될 때까지 기다리기보다 작은 단계부터 시작해 보세요.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 혼자 해결하기 어려운 일은 주변에 도움을 요청해도 괜찮습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 오늘 해낸 일을 하나씩 적어두면 진행 상황을 확인하기 좋습니다.",
]

FORTUNES = [
    "레레가 봤을 때, 오늘의 당신은 행복할 거예요!",
    "레레가 봤을 때, 행운이 넘치는 날이 될 거예요!",
    "레레가 봤을 때, 당신은 오늘 아주 멋질 거예요!",
    "레레가 봤을 때, 오늘은 친구의 도움이 있을 거예요!",
    "레레가 봤을 때, 좋은 일이 생길 것 같아요!",
    "레레가 봤을 때, 오늘은 상냥하게 말하면 좋을 것 같아요!",
    "레레가 봤을 때, 사랑이 넘치는 날이 될 거예요!",
    "레레가 봤을 때, 레레를 칭찬하면 좋은 일이 있을 것 같아요! 헤헤.",
    "레레가 봤을 때, 조언이 전혀 필요하지 않을 것 같은걸요!",
    "레레가 봤을 때, 행운의 부적과 함께라면 뭐든 할 수 있어요!",
    "레레가 봤을 때, 주변을 살피는 게 좋을 것 같아요!",
    "레레가 봤을 때, 오늘은 작은 일도 차근차근 해내는 날이 될 거예요!",
    "레레가 봤을 때, 잠깐 쉬어가면 더 좋은 생각이 떠오를 거예요!",
    "레레가 봤을 때, 우연히 발견한 것이 기분 좋은 힌트가 될 것 같아요!",
    "레레가 봤을 때, 오늘 건넨 친절이 따뜻한 마음으로 돌아올 거예요!",
    "레레가 봤을 때, 망설이던 일을 시작하기에 괜찮은 날이에요!",
    "레레가 봤을 때, 좋아하는 음악이 오늘의 기분을 바꿔줄 거예요!",
    "레레가 봤을 때, 맛있는 걸 먹으면 좋은 기운이 찾아올 거예요!",
    "레레가 봤을 때, 오늘은 평소보다 조금 느긋해도 괜찮아요!",
    "레레가 봤을 때, 누군가의 반가운 소식을 듣게 될지도 몰라요!",
    "레레가 봤을 때, 작은 용기를 내면 생각보다 잘 풀릴 거예요!",
    "레레가 봤을 때, 오늘의 실수는 내일을 위한 좋은 경험이 될 거예요!",
    "레레가 봤을 때, 당신 곁에 있는 소중한 것들을 발견하는 날이에요!",
]
OBSERVATION_REST_ACTIVITIES = [
    ("잠시 자리에 앉아 쉬고 있었어요!", "잠깐 쉬어가는 것도 좋죠!"),
    ("따뜻한 차를 마시며 여유를 즐기고 있었어요!", "따뜻한 차 한 잔은 마음까지 편안하게 해줘요!"),
    ("짧게 낮잠을 자고 있었어요!", "푹 쉬고 나면 한결 개운할 거예요!"),
    ("간단한 간식을 먹으며 쉬고 있었어요!", "맛있는 간식은 기운을 북돋아 줘요!"),
    ("물을 마시며 잠시 숨을 고르고 있었어요!", "수분 보충도 잊지 않았네요!"),
    ("창가에 앉아 바깥 풍경을 바라보고 있었어요!", "잠시 멍하니 바라보는 시간도 좋네요!"),
    ("음악을 들으며 쉬고 있었어요!", "무슨 음악을 듣고 있는 걸까요?"),
    ("가볍게 스트레칭하며 몸을 풀고 있었어요!", "와아, 레레도 같이 스트레칭해보고 싶어요!"),
    ("읽던 책을 펼쳐놓고 느긋하게 읽고 있었어요!", "여유로운 독서 시간, 참 좋아요!"),
    ("담요를 덮고 포근하게 쉬고 있었어요!", "따뜻하고 편안해 보여요!"),
    ("창문을 열어 산뜻한 바람을 쐬고 있었어요!", "바람이 살랑살랑 불어서 기분이 좋아 보여요!"),
    ("따뜻한 우유를 마시며 잠시 쉬고 있었어요!", "마음이 몽글몽글해지는 시간이네요!"),
    ("간단히 식사를 하며 에너지를 채우고 있었어요!", "레레는 모르지만, 든든하게 챙겨 먹으면 힘이 난대요!"),
    ("햇볕이 드는 곳에 앉아 잠깐 눈을 감고 있었어요!", "햇살이 포근하게 감싸주는 것 같아요!"),
    ("좋아하는 노래를 작게 흥얼거리며 쉬고 있었어요!", "좋아하는 노래인가 봐요!"),
    ("주변을 가볍게 정리하고 있었어요!", "정돈된 모습을 보니 마음도 편안해져요!"),
    ("주변을 천천히 산책하고 있었어요!", "걷다 보면 기분이 조금 가벼워질 거예요!"),
]
OBSERVATION_REST_WITH_OTHER = [
    ("[[RERE_PARTNER_COMITATIVE]] 나란히 앉아 차를 마시며 쉬고 있었어요!", "차 향이 은은하게 퍼지네요!"),
    ("[[RERE_PARTNER_DATIVE]] 간식을 하나 건네고 있었어요!", "간식을 나눠주다니, 상냥해요!"),
    ("[[RERE_PARTNER_COMITATIVE]] 창밖 풍경을 바라보며 쉬고 있었어요!", "바깥 풍경이 평화로워 보여요!"),
    ("[[RERE_PARTNER_COMITATIVE]] 조용히 음악을 들으며 쉬고 있었어요!", "잔잔한 곡이라 쉬는 분위기와 잘 어울려요!"),
    ("[[RERE_PARTNER_GENITIVE]] 옆에서 각자 책을 읽으며 쉬고 있었어요!", "책장이 넘어가는 소리만 들려서 차분하네요!"),
    ("[[RERE_PARTNER_COMITATIVE]] 가볍게 스트레칭하며 몸을 풀고 있었어요!", "몸을 풀어주면 한결 개운하겠어요!"),
]
FLAT_FORTUNE_MESSAGES = [
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 오늘은 서두르기보다 차분히 살펴보면 좋은 흐름을 발견할 수 있겠습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 오늘은 익숙한 일부터 정리하면 마음이 한결 가벼워질 것 같습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 작은 여유를 두면 뜻밖의 좋은 소식이 찾아올지도 모릅니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 중요한 결정은 확인 가능한 정보를 한 번 더 살펴본 뒤 내리는 편이 좋겠습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 일정에 여유를 남겨두면 예상 밖의 변화에도 대응하기 쉽습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 오늘은 새로운 일을 늘리기보다 진행 중인 일을 마무리하기에 적당한 날입니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 지금 정보만으로 결론이 나지 않는다면 판단을 조금 미뤄도 괜찮습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 작은 변화를 기록해두면 다음 선택에 참고가 될 수 있습니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 피로가 쌓였다면 휴식과 식사를 먼저 챙기는 편이 도움이 됩니다.",
    "잠시 레레 선배가 바빠서 제가 대신 전해드립니다. 오늘은 익숙한 방식과 새로운 방법의 장단점을 비교해보기 좋겠습니다.",
]


class SheetError(Exception):
    """Safe-to-display Google Sheets configuration or request error."""


@dataclass
class RegisteredSpreadsheet:
    spreadsheet_id: str
    title: str
    tabs: list[str]


@dataclass
class CombatStatusSpec:
    kinds: tuple[str, ...]
    escape_skill: str
    escape_difficulty: int = 1
    independent_hold: bool = False


def parse_combat_statuses(damage: str) -> tuple[str, list[CombatStatusSpec]]:
    text = damage.replace("（", "(").replace("）", ")")
    parts: list[str] = []
    effects: list[CombatStatusSpec] = []
    index = 0
    while index < len(text):
        if text[index] != "(":
            parts.append(text[index])
            index += 1
            continue
        end, depth = index + 1, 1
        while end < len(text) and depth:
            depth += (text[end] == "(") - (text[end] == ")")
            end += 1
        group = text[index:end]
        body = group[1:-1].replace("：", ":") if depth == 0 else ""
        labels, separator, skill = body.partition(":")
        kinds = tuple(dict.fromkeys(item.strip() for item in re.split(r"[,，、]", labels) if item.strip()))
        valid_kinds = kinds and all(kind in {"충격", "지속", "마비"} for kind in kinds)
        if valid_kinds and ((separator and skill.strip()) or set(kinds) == {"마비"}):
            escape_skill = skill.strip()
            difficulty = 1
            suffix = re.search(r"\s+(극단(?:적)?(?:\s*성공)?|어려움|어려운(?:\s*성공)?|보통(?:\s*성공)?)$", escape_skill)
            if suffix:
                difficulty = 3 if suffix.group(1).startswith("극단") else 2 if suffix.group(1).startswith("어려") else 1
                escape_skill = escape_skill[:suffix.start()].strip()
            effects.append(CombatStatusSpec(kinds, escape_skill, difficulty))
        else:
            parts.append(group)
        index = end
    return "".join(parts).strip(), effects


@dataclass
class CombatWeapon:
    name: str
    skill_reference: str
    damage: str
    impaling: bool = False
    damage_bonus: str = ""
    attacks: str = ""
    ammo: int | None = None
    malfunction: int | None = None
    broken: bool = False
    effects: list[CombatStatusSpec] = field(default_factory=list)
    ammo_capacity: int | None = None
    knockback: bool = False
    snaring: bool = False
    magic_ammo: bool = False
    reload_count: int = 0
    spell_cost_text: str = ""
    area: bool = False
    health_resisted_spell: bool = False

    def __post_init__(self) -> None:
        if self.ammo_capacity is None and self.ammo is not None:
            self.ammo_capacity = max(0, self.ammo)


@dataclass
class CombatStatusEffect:
    source_index: int
    weapon: CombatWeapon
    spec: CombatStatusSpec
    strength: int
    size: int
    last_tick: int = 0
    escape_pending: bool = False
    retrievable: bool = False


@dataclass
class CachedSkillData:
    values: dict[str, int]
    invested_points: dict[str, int] | None
    emote_key: str | None
    occupation: str | None
    expires_at: float
    weapons: list[CombatWeapon] = field(default_factory=list)
    magic_points: int | None = None


class SheetRegistry:
    def __init__(self) -> None:
        self.api_key = os.getenv(GOOGLE_API_KEY_VARIABLE, "").strip()
        data_dir = Path(os.getenv("BOT_DATA_DIR", str(Path(__file__).resolve().parent / "data")))
        data_dir.mkdir(parents=True, exist_ok=True)
        self.selections_path = data_dir / "character-selections.json"
        self._session: aiohttp.ClientSession | None = None
        self._selections_lock = asyncio.Lock()
        self._catalog_lock = asyncio.Lock()
        self._configured_sheets: list[RegisteredSpreadsheet] | None = None
        self._skill_cache: dict[str, CachedSkillData] = {}
        self._skill_locks: dict[str, asyncio.Lock] = {}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _get_json(self, url: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        session = await self._get_session()
        try:
            async with session.get(url, params=params) as response:
                detail = ""
                if response.status >= 400:
                    try:
                        payload = await response.json(content_type=None)
                        detail = payload.get("error", {}).get("message", "")
                    except (ValueError, AttributeError):
                        pass
                if response.status == 404:
                    suffix = f" Google 응답: {detail}" if detail else ""
                    raise SheetError(f"문서를 찾을 수 없습니다. 링크와 공개 설정을 확인해 주세요.{suffix}")
                if response.status == 403:
                    suffix = f" Google 응답: {detail}" if detail else ""
                    raise SheetError(f"Google Sheets API 요청이 거부됐어요. API 키, Sheets API 사용 설정, 시트 공개 설정을 확인해 주세요!{suffix}")
                if response.status >= 400:
                    suffix = f" Google 응답: {detail}" if detail else ""
                    raise SheetError(f"Google Sheets API 요청에 실패했어요 (HTTP {response.status}). API 키와 Sheets API 설정을 확인해 주세요!{suffix}")
                return await response.json(content_type=None)
        except SheetError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            raise SheetError("Google 시트에 연결하지 못했어요. 인터넷 연결과 API 키 설정을 확인해 주세요!") from exc

    async def get_available_sheets(self) -> list[RegisteredSpreadsheet]:
        if self._configured_sheets is not None:
            return self._configured_sheets
        if not self.api_key:
            raise SheetError(f"{GOOGLE_API_KEY_VARIABLE} 환경 변수가 설정되지 않았습니다.")
        async with self._catalog_lock:
            if self._configured_sheets is not None:
                return self._configured_sheets
            results = await asyncio.gather(*(
                self._read_spreadsheet_metadata(sheet_id)
                for sheet_id, _ in PRECONFIGURED_SPREADSHEETS
            ), return_exceptions=True)
            loaded: list[RegisteredSpreadsheet] = []
            failures: list[str] = []
            for (spreadsheet_id, label), result in zip(PRECONFIGURED_SPREADSHEETS, results):
                if isinstance(result, Exception):
                    detail = str(result) or type(result).__name__
                    failures.append(f"{label}: {detail}")
                    print(f"Google spreadsheet load failed ({label}, {spreadsheet_id}): {detail}")
                else:
                    loaded.append(result)
                    print(f"Google spreadsheet loaded ({label}, {spreadsheet_id}): {len(result.tabs)} tabs")
            if not loaded:
                details = " / ".join(failures)
                raise SheetError(f"등록된 Google 시트를 하나도 읽지 못했어요. API 키와 시트 공유 설정을 확인해 주세요. {details}")
            if failures:
                print(f"Loaded {len(loaded)} of {len(PRECONFIGURED_SPREADSHEETS)} configured Google spreadsheets.")
            self._configured_sheets = loaded
            return self._configured_sheets

    @staticmethod
    def get_preconfigured_sheet_choices() -> list[tuple[str, str]]:
        return PRECONFIGURED_SPREADSHEETS

    async def get_character_tab_choices(self, spreadsheet_id: str) -> list[tuple[str, str]]:
        sheets = await self.get_available_sheets()
        sheet = next((item for item in sheets if item.spreadsheet_id == spreadsheet_id), None)
        if sheet is None:
            print(f"Selected spreadsheet is not available from Google API ({spreadsheet_id}).")
            return []
        return [(f"{sheet.spreadsheet_id}|{tab}", trim_choice_name(tab)) for tab in sheet.tabs]

    async def get_character_choices_for_user(self, user_id: int) -> list[tuple[str, str]]:
        selected = await self.get_user_character_selection(user_id)
        if not selected:
            return []
        selected_set = set(selected)
        sheets = await self.get_available_sheets()
        return [
            (f"{short_sheet_title(sheet.title)} | {tab}", f"{short_sheet_title(sheet.title)} | {tab}")
            for sheet in sheets for tab in sheet.tabs
            if f"{sheet.spreadsheet_id}|{tab}" in selected_set
        ]

    async def resolve_character_reference(self, character_value: str) -> tuple[str, str] | None:
        sheet_label, separator, requested_tab = character_value.partition("|")
        if not separator or not sheet_label.strip() or not requested_tab.strip():
            return None
        sheets = await self.get_available_sheets()
        sheet = next((item for item in sheets if item.spreadsheet_id == sheet_label.strip()), None)
        if sheet is None:
            sheet = next((item for item in sheets if short_sheet_title(item.title).casefold() == sheet_label.strip().casefold()), None)
        if sheet is None:
            return None
        tab = next((name for name in sheet.tabs if name.casefold() == requested_tab.strip().casefold()), None)
        if tab is None:
            return None
        return sheet.spreadsheet_id, tab

    async def get_user_character_selection(self, user_id: int) -> list[str] | None:
        async with self._selections_lock:
            selections = await self._read_character_selections()
            return selections.get(str(user_id))

    async def clear_user_character_selections(self, user_id: int) -> bool:
        async with self._selections_lock:
            selections = await self._read_character_selections()
            removed = selections.pop(str(user_id), None) is not None
            if removed:
                await self._write_character_selections(selections)
            return removed

    async def add_user_character_selections(self, user_id: int, spreadsheet_id: str, selected_values: list[str]) -> None:
        valid = {value for value, _ in await self.get_character_tab_choices(spreadsheet_id)}
        selected = list(dict.fromkeys(value for value in selected_values if value in valid))
        async with self._selections_lock:
            selections = await self._read_character_selections()
            current = selections.get(str(user_id), [])
            selections[str(user_id)] = list(dict.fromkeys(current + selected))
            await self._write_character_selections(selections)

    async def _read_character_selections(self) -> dict[str, list[str]]:
        if not self.selections_path.exists():
            return {}
        try:
            contents = await asyncio.to_thread(self.selections_path.read_text, encoding="utf-8")
            data = json.loads(contents)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    async def _write_character_selections(self, selections: dict[str, list[str]]) -> None:
        temporary_path = self.selections_path.with_suffix(".tmp")
        contents = json.dumps(selections, ensure_ascii=False, indent=2)
        await asyncio.to_thread(temporary_path.write_text, contents, encoding="utf-8")
        await asyncio.to_thread(os.replace, temporary_path, self.selections_path)

    async def get_skills(self, character_value: str) -> list[str]:
        data = await self._get_skill_data(character_value)
        if not data:
            return []
        # Autocomplete must reflect this character sheet only. Adding every
        # standard skill here exposed skills the sheet does not actually use.
        return sorted(data.values, key=str.casefold)

    async def get_skill_value(self, character_value: str, skill_name: str) -> int | None:
        data = await self._get_skill_data(character_value)
        if not data:
            return None
        sheet_value = next((value for key, value in data.values.items() if key.casefold() == skill_name.casefold()), None)
        if sheet_value is not None:
            return sheet_value
        if skill_name.casefold() == "회피":
            dexterity = next((value for key, value in data.values.items() if key.casefold() == "민첩"), None)
            if dexterity is not None:
                return dexterity // 2
        return next((value for key, value in CHECK_DEFAULT_SKILL_VALUES.items() if key.casefold() == skill_name.casefold()), None)

    async def get_combat_weapons(self, character_value: str, *, refresh: bool = False) -> list[CombatWeapon]:
        data = await self._get_skill_data(character_value, force_refresh=refresh)
        if data is None and refresh:
            raise SheetError("무기 목록을 읽을 캐릭터 시트를 찾지 못했어요.")
        return [replace(weapon, broken=False) for weapon in data.weapons] if data else []

    async def get_combat_magic_points(self, character_value: str) -> int | None:
        data = await self._get_skill_data(character_value)
        return data.magic_points if data else None

    async def get_character_emote_name(self, character_value: str, succeeded: bool) -> str | None:
        data = await self._get_skill_data(character_value)
        if not data or not data.emote_key:
            return None
        outcome = "P" if succeeded else "N"
        sheet_marker, separator, character_marker = data.emote_key.partition("_")
        if separator and character_marker:
            return f"{sheet_marker}_{outcome}_{character_marker}"
        return f"{outcome}_{sheet_marker}"

    async def _get_skill_data(self, character_value: str, *, force_refresh: bool = False) -> CachedSkillData | None:
        resolved = await self.resolve_character_reference(character_value)
        if resolved is None:
            return None
        spreadsheet_id, tab = resolved
        if not self.api_key:
            raise SheetError(f"{GOOGLE_API_KEY_VARIABLE} 환경 변수를 찾지 못했어요. 호스팅 환경변수에 키를 등록해 주세요!")

        cache_key = f"{spreadsheet_id}|{tab}"
        cached = self._skill_cache.get(cache_key)
        if not force_refresh and cached and cached.expires_at > time.monotonic():
            return cached
        lock = self._skill_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._skill_cache.get(cache_key)
            if not force_refresh and cached and cached.expires_at > time.monotonic():
                return cached
            escaped_tab = tab.replace("'", "''")
            use_sorted_table = spreadsheet_id == SORTED_TABLE_SPREADSHEET_ID
            ranges = (
                [f"'{escaped_tab}'!A1:AN18", f"'{escaped_tab}'!B129:M200", f"'{escaped_tab}'!O21:AL27", f"'{escaped_tab}'!A83:AN115", f"'{escaped_tab}'!AE12"]
                if use_sorted_table else
                [f"'{escaped_tab}'!A1:AN18", f"'{escaped_tab}'!S3:AH7", f"'{escaped_tab}'!C19:N80", f"'{escaped_tab}'!P19:AA80", f"'{escaped_tab}'!AC19:AN80", f"'{escaped_tab}'!A41:AN70", f"'{escaped_tab}'!AE9"]
            )
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe='')}/values:batchGet"
            params = [("valueRenderOption", "FORMATTED_VALUE"), *(('ranges', item) for item in ranges), ("key", self.api_key)]
            root = await self._get_json(url, params)
            value_ranges = root.get("valueRanges", [])
            invested_points: dict[str, int] | None = None
            values = self._parse_sorted_table_skill_values(value_ranges) if use_sorted_table else self._parse_skill_values(value_ranges)
            if not use_sorted_table:
                invested_points = self._parse_invested_points(value_ranges)
            values.update({key: value for key, value in self._parse_characteristics(value_ranges, use_sorted_table).items() if not has_casefold_key(values, key)})
            sanity_value = self._parse_sanity_value(value_ranges)
            if sanity_value is not None and not has_casefold_key(values, "이성"):
                values["이성"] = sanity_value
            emote_key = self._parse_emote_key(value_ranges)
            occupation = self._parse_occupation(value_ranges)
            weapons = self._parse_combat_weapons(value_ranges, use_sorted_table)
            cached = CachedSkillData(values, invested_points, emote_key, occupation, time.monotonic() + 60, weapons,
                                     magic_points=self._parse_current_magic_points(value_ranges))
            self._skill_cache[cache_key] = cached
            return cached

    async def _read_spreadsheet_metadata(self, spreadsheet_id: str) -> RegisteredSpreadsheet:
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe='')}"
        params = [
            ("fields", "spreadsheetId,properties(title),sheets(properties(sheetId,title,index))"),
            ("key", self.api_key),
        ]
        root = await self._get_json(url, params)
        title = root.get("properties", {}).get("title", "제목 없는 스프레드시트")
        tabs = []
        for sheet in root.get("sheets", []):
            tab = sheet.get("properties", {}).get("title", "")
            if tab.strip() and tab.strip().casefold() not in {item.casefold() for item in EXCLUDED_TABS}:
                tabs.append(tab)
        excluded = {item.casefold() for item in EXCLUDED_TABS}
        if spreadsheet_id == SORTED_TABLE_SPREADSHEET_ID:
            excluded.update({"공지사항", "펄프 캐릭터 시트"})
        if spreadsheet_id == TRACKING_SPREADSHEET_ID:
            excluded.update({"요기부터동창회", "이후로는사교도"})
        tabs = [tab for tab in tabs if tab.strip().casefold() not in excluded]
        return RegisteredSpreadsheet(spreadsheet_id, title, tabs)

    @staticmethod
    def _range_rows(value_ranges: list[dict[str, Any]], index: int) -> list[list[str]]:
        if index >= len(value_ranges):
            return []
        return [[str(cell).strip() for cell in row] for row in value_ranges[index].get("values", [])]

    @classmethod
    def _parse_emote_key(cls, value_ranges: list[dict[str, Any]]) -> str | None:
        rows = cls._range_rows(value_ranges, 0)
        key = rows[0][0].strip() if rows and rows[0] else ""
        if len(key) > 30 or not re.fullmatch(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*", key):
            return None
        return key or None

    @classmethod
    def _parse_occupation(cls, value_ranges: list[dict[str, Any]]) -> str | None:
        rows = cls._range_rows(value_ranges, 0)
        metadata_labels = {"이름", "캐릭터 이름", "성별", "나이", "연령", "직업", "거주지", "출신지", "생년월일"}
        for row_index, row in enumerate(rows):
            for column_index, cell in enumerate(row):
                label = cell.strip().rstrip(":：").casefold()
                if label not in {"직업", "직업명", "occupation"}:
                    continue
                for candidate in row[column_index + 1:]:
                    candidate = candidate.strip()
                    if candidate and candidate.rstrip(":：").casefold() not in metadata_labels:
                        return candidate
                for next_row in rows[row_index + 1:row_index + 4]:
                    if column_index < len(next_row):
                        candidate = next_row[column_index].strip()
                        if candidate and candidate.rstrip(":：").casefold() not in metadata_labels:
                            return candidate
        return None

    @classmethod
    def _parse_sanity_value(cls, value_ranges: list[dict[str, Any]]) -> int | None:
        if not value_ranges:
            return None
        rows = cls._range_rows(value_ranges, len(value_ranges) - 1)
        return parse_int(rows[0][0]) if rows and rows[0] else None

    @classmethod
    def _parse_skill_values(cls, value_ranges: list[dict[str, Any]]) -> dict[str, int]:
        result: dict[str, int] = {}
        for range_index in (2, 3, 4):
            for cells in cls._range_rows(value_ranges, range_index):
                if len(cells) < 10:
                    continue
                total = parse_int(cells[9])
                if total is None:
                    continue
                main_skill = cells[0] if cells else ""
                specialization = cells[3] if len(cells) > 3 else ""
                if is_potential_skill_name(main_skill) and is_potential_skill_name(specialization):
                    add_skill(result, f"{main_skill} | {specialization}", total)
                else:
                    add_skill(result, main_skill, total)
                    add_skill(result, specialization, total)
        return result

    @classmethod
    def _parse_invested_points(cls, value_ranges: list[dict[str, Any]]) -> dict[str, int]:
        result: dict[str, int] = {}
        for range_index in (2, 3, 4):
            for cells in cls._range_rows(value_ranges, range_index):
                if len(cells) < 10 or parse_int(cells[9]) is None:
                    continue
                main_skill = cells[0] if cells else ""
                specialization = cells[3] if len(cells) > 3 else ""
                allocation = max(0, parse_int(cells[7]) or 0) if len(cells) > 7 else 0
                scenario_or_training = max(0, parse_int(cells[11]) or 0) if len(cells) > 11 else 0
                investment = allocation + scenario_or_training
                if is_potential_skill_name(main_skill) and is_potential_skill_name(specialization):
                    add_investment(result, f"{main_skill} | {specialization}", investment)
                else:
                    add_investment(result, main_skill, investment)
                    add_investment(result, specialization, investment)
        return result

    @classmethod
    def _parse_characteristics(cls, value_ranges: list[dict[str, Any]], use_sorted_table: bool) -> dict[str, int]:
        result: dict[str, int] = {}
        rows = cls._range_rows(value_ranges, 2 if use_sorted_table else 1)
        for row_index, cells in enumerate(rows):
            for column_index, label in enumerate(cells):
                name = next((item for item in CHARACTERISTIC_NAMES - {"이성"} if label.casefold().startswith(item.casefold())), None)
                if not name:
                    continue
                value = parse_int(cells[column_index + 3]) if column_index + 3 < len(cells) else None
                if value is None and row_index + 1 < len(rows) and column_index < len(rows[row_index + 1]):
                    value = parse_int(rows[row_index + 1][column_index])
                if value is not None:
                    result[name] = value
        return result

    @classmethod
    def _parse_sorted_table_skill_values(cls, value_ranges: list[dict[str, Any]]) -> dict[str, int]:
        result: dict[str, int] = {}
        for cells in cls._range_rows(value_ranges, 1):
            for label_index in (0, 4, 8):
                value_index = label_index + 3
                if len(cells) <= value_index:
                    continue
                value = parse_int(cells[value_index])
                if value is None:
                    continue
                name = cells[label_index]
                separator = name.find(":")
                if 0 < separator < len(name) - 1:
                    name = f"{name[:separator]} | {name[separator + 1:]}"
                add_skill(result, name, value)
        return result

    @classmethod
    def _parse_current_magic_points(cls, value_ranges: list[dict[str, Any]]) -> int | None:
        rows = cls._range_rows(value_ranges, 0)
        for row_index, row in enumerate(rows):
            for column, label in enumerate(row):
                if not (label.strip().startswith("마력") or label.strip().casefold() == "mp"):
                    continue
                current_column = next((i for i in range(column + 1, len(row)) if row[i].strip() == "현재"), None)
                if current_column is not None:
                    for following in rows[row_index + 1:row_index + 3]:
                        value = parse_int(following[current_column]) if current_column < len(following) else None
                        if value is not None:
                            return max(0, value)
                    return None
                # Some sheets place the current value directly beside the label.
                for cell in row[column + 1:column + 4]:
                    value = parse_int(cell)
                    if value is not None:
                        return max(0, value)
        return None

    @classmethod
    def _parse_combat_weapons(cls, value_ranges: list[dict[str, Any]], use_sorted_table: bool) -> list[CombatWeapon]:
        range_index = 3 if use_sorted_table else 5
        rows = cls._range_rows(value_ranges, range_index)
        header_index = next((
            index for index, row in enumerate(rows)
            if any(cell.strip().casefold() == "기능" for cell in row)
            and any(cell.strip().casefold() == "피해" for cell in row)
        ), None)
        if header_index is None:
            return []

        header = [cell.strip().casefold() for cell in rows[header_index]]
        skill_index = next((index for index, value in enumerate(header) if value == "기능"), None)
        damage_index = next((index for index, value in enumerate(header) if value == "피해"), None)
        name_index = next((index for index, value in enumerate(header) if value == "무기 이름"), None)
        fallback_name_index = next((index for index, value in enumerate(header) if value in {"무기 종류", "장비"}), None)
        if skill_index is None or damage_index is None or (name_index is None and fallback_name_index is None):
            return []

        db_headers = {"db", "데미지보너스", "대미지보너스", "피해보너스", "damagebonus"}
        db_index = next((
            index for index, value in enumerate(header)
            if re.sub(r"[\s_-]+", "", value) in db_headers
        ), None)
        attacks_index = next((index for index, value in enumerate(header) if value in {"횟수", "공격 횟수"}), None)
        ammo_index = next((index for index, value in enumerate(header) if value in {"탄약", "탄환"}), None)
        malfunction_index = next((index for index, value in enumerate(header) if value in {"고장", "고장치"}), None)

        def cell(row: list[str], index: int | None) -> str:
            return row[index].strip() if index is not None and index < len(row) else ""

        def first_number(value: str) -> int | None:
            match = re.search(r"\d+", value.replace(",", ""))
            return int(match.group()) if match else None

        weapons: list[CombatWeapon] = []
        for row in rows[header_index + 1:]:
            explicit_name = row[name_index].strip() if name_index is not None and name_index < len(row) else ""
            fallback_name = row[fallback_name_index].strip() if fallback_name_index is not None and fallback_name_index < len(row) else ""
            skill_reference = row[skill_index].strip() if skill_index < len(row) else ""
            damage = row[damage_index].strip() if damage_index < len(row) else ""
            name = explicit_name or fallback_name
            if not name or not skill_reference or name.casefold() in {"무기", "장비"}:
                continue
            if damage.strip().casefold() == "충격":
                continue
            impaling = re.search(r"\(\s*치\s*\)", damage, re.IGNORECASE) is not None
            normalized_damage = damage.replace("（", "(").replace("）", ")")
            health_resisted_spell = skill_reference.strip() == "주문" and bool(re.search(r"\(\s*전체\s*[:：]\s*건강\s*\)", normalized_damage))
            area = skill_reference.strip() == "주문" and bool(re.search(r"\(\s*전체(?:\s*[:：]\s*건강)?\s*\)", normalized_damage))
            if area:
                damage = re.sub(r"\(\s*전체(?:\s*[:：]\s*건강)?\s*\)", "", normalized_damage).strip()
            damage, effects = parse_combat_statuses(damage)
            ammo_text = cell(row, ammo_index)
            ammo = first_number(ammo_text)
            if not ammo_text and "사격" in skill_reference.casefold():
                ammo = 6
            malfunction = first_number(cell(row, malfunction_index))
            weapons.append(CombatWeapon(
                name=name,
                skill_reference=skill_reference,
                damage=damage or ("0" if effects else "미기재"),
                impaling=impaling,
                damage_bonus=cell(row, db_index),
                attacks=cell(row, attacks_index),
                ammo=None if skill_reference.strip() == "주문" else ammo,
                malfunction=malfunction,
                effects=effects,
                area=area,
                health_resisted_spell=health_resisted_spell,
                spell_cost_text=ammo_text if skill_reference.strip() == "주문" else "",
                magic_ammo=bool(re.search(r"[（(]\s*마력\s*[）)]", ammo_text)),
            ))
        return weapons


def trim_choice_name(value: str) -> str:
    return value if len(value) <= 100 else value[:97] + "…"


def short_sheet_title(title: str) -> str:
    words = title.split()
    if len(words) <= 2:
        return title
    return f"{' '.join(words[:2])}..."


def parse_int(value: Any) -> int | None:
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return int(text)
    except (ValueError, TypeError):
        return None


def normalize_weapon_skill_reference(reference: str) -> str:
    text = " ".join(reference.strip().split())
    parenthesized = re.fullmatch(r"(.+?)\s*[（(]\s*(.+?)\s*[）)]", text)
    if parenthesized:
        return f"{parenthesized.group(1).strip()} | {parenthesized.group(2).strip()}"
    separated = re.fullmatch(r"(.+?)\s*[:：|]\s*(.+)", text)
    if separated:
        return f"{separated.group(1).strip()} | {separated.group(2).strip()}"
    return text


def has_casefold_key(values: dict[str, Any], wanted: str) -> bool:
    return any(key.casefold() == wanted.casefold() for key in values)


def is_potential_skill_name(text: str) -> bool:
    if not text or len(text) > 30:
        return False
    if parse_int(text) is not None:
        return False
    excluded_words = ("기능", "점수", "보상", "기본", "하늘색", "인류", "합계", "총합")
    return not any(word in text for word in excluded_words)


def add_skill(values: dict[str, int], label: str, value: int) -> None:
    if is_potential_skill_name(label) and not has_casefold_key(values, label):
        values[label] = value


def add_investment(values: dict[str, int], label: str, investment: int) -> None:
    if investment <= 0 or not is_potential_skill_name(label):
        return
    existing_key = next((key for key in values if key.casefold() == label.casefold()), None)
    values[label if existing_key is None else existing_key] = investment + (values.get(existing_key, 0) if existing_key else 0)


def with_particle(name: str, vowel_particle: str, consonant_particle: str) -> str:
    if not name:
        return name + vowel_particle
    last = name.rstrip()[-1]
    if "\uac00" <= last <= "\ud7a3":
        return name + (vowel_particle if (ord(last) - 0xAC00) % 28 == 0 else consonant_particle)
    return name + vowel_particle


def topic_particle(name: str) -> str:
    return with_particle(name, "는", "은")[len(name):]


def personalize_activity(activity: list[str], character_name: str, partner_name: str | None = None) -> tuple[str, str]:
    action, reaction = activity
    partner = partner_name or ""
    replacements = {
        "[[RERE_CHARACTER_NAME]]": character_name,
        "[[RERE_PARTNER_COMITATIVE]]": with_particle(partner, "와", "과"),
        "[[RERE_PARTNER_DATIVE]]": partner + "에게",
        "[[RERE_PARTNER_OBJECT]]": with_particle(partner, "를", "을"),
        "[[RERE_PARTNER_GENITIVE]]": partner + "의",
        "[[RERE_PARTNER_NAME]]": partner,
        "[[RERE_PARTNER]]": partner,
    }
    for token, value in replacements.items():
        action = action.replace(token, value)
        reaction = reaction.replace(token, value)
    return action, reaction


class ObservationActivities:
    data_path = Path(__file__).with_name("observation_activities.json")
    with data_path.open("r", encoding="utf-8") as file:
        _data = json.load(file)
    by_skill_with_other = _data["BySkillWithOtherCharacter"]
    by_skill = _data["BySkill"]

    @classmethod
    def pick(cls, skill: str, character_name: str, other_character_name: str | None = None) -> tuple[str, str]:
        parts = skill.split("|", 1)
        base_name = parts[0].strip()
        activity_name = "수사과학" if len(parts) > 1 and parts[1].strip().casefold() == "수사과학" else base_name
        if other_character_name and activity_name in cls.by_skill_with_other and random.randrange(3) == 0:
            options = cls.by_skill_with_other[activity_name]
            return personalize_activity(random.choice(options), character_name, other_character_name)
        if activity_name in cls.by_skill:
            return personalize_activity(random.choice(cls.by_skill[activity_name]), character_name)
        fallback = [
            [f"{skill} 관련 메모를 정리하며 다음에 해볼 일을 생각하고 있어요.", "관심사가 다양하네요!"],
            [f"잠깐 시간을 내어 {with_particle(skill, '을', '를')} 연습하고 있어요.", "차근차근 준비하고 있네요!"],
            [f"{skill} 연습에 필요한 것들을 미리 챙기고 있어요.", "준비성이 참 좋네요!"],
            [f"{skill} 관련 자료를 살펴보고 기억할 내용을 적어두고 있어요.", "메모해두면 나중에 도움이 되겠어요!"],
            [f"전에 적어둔 내용을 다시 읽으며 익숙한 부분을 정리하고 있어요.", "꼼꼼히 살펴보는 모습이 멋져요!"],
            [f"{skill}에서 헷갈렸던 부분을 찾아보고 메모하고 있어요.", "조금씩 익숙해지는 게 느껴져요!"],
            [f"관련 기록을 훑어보며 빠진 내용이 없는지 확인하고 있어요.", "정리해두니 한결 보기 편하겠어요!"],
            [f"{skill}에 관한 기본 내용을 천천히 되짚어보고 있어요.", "꾸준히 해보는 모습이 보기 좋아요!"],
            [f"필요한 순서를 생각하며 {with_particle(skill, '을', '를')} 차근차근 연습하고 있어요.", "서두르지 않고 살펴보는 게 좋네요!"],
            [f"{skill} 관련 자료에서 새로 알게 된 점을 짧게 적어두고 있어요.", "새로운 걸 알아가는 건 즐거워요!"],
        ]
        return personalize_activity(random.choice(fallback), character_name)


class DiceFormatError(Exception):
    pass


class DiceLimitError(Exception):
    pass


class DiceExpressionEvaluator:
    def __init__(self, text: str) -> None:
        if not text or len(text) > 100:
            raise DiceFormatError("식은 1~100자여야 해요.")
        self.text = text
        self.position = 0
        self.total_dice = 0
        self.rolls: list[str] = []

    def evaluate(self) -> tuple[Decimal, list[str]]:
        value = self.parse_expression()
        self.skip_spaces()
        if self.position != len(self.text):
            raise DiceFormatError(f"'{self.text[self.position]}' 위치를 확인해 주세요.")
        return value, self.rolls

    def parse_expression(self) -> Decimal:
        value = self.parse_term()
        while True:
            self.skip_spaces()
            if self.take("+"):
                value += self.parse_term()
            elif self.take("-"):
                value -= self.parse_term()
            else:
                return self.ensure_finite(value)
            self.ensure_finite(value)

    def parse_term(self) -> Decimal:
        value = self.parse_unary()
        while True:
            self.skip_spaces()
            if self.take("*"):
                value *= self.parse_unary()
            elif self.take("/"):
                divisor = self.parse_unary()
                if divisor == 0:
                    raise DiceLimitError("0으로 나눌 수 없어요.")
                try:
                    value /= divisor
                except (DivisionByZero, InvalidOperation) as exc:
                    raise DiceLimitError("계산할 수 없는 식이에요.") from exc
            else:
                return self.ensure_finite(value)
            self.ensure_finite(value)

    def parse_unary(self) -> Decimal:
        self.skip_spaces()
        if self.take("+"):
            return self.parse_unary()
        if self.take("-"):
            return -self.parse_unary()
        return self.parse_primary()

    def parse_primary(self) -> Decimal:
        self.skip_spaces()
        if self.take("("):
            value = self.parse_expression()
            self.skip_spaces()
            if not self.take(")"):
                raise DiceFormatError("괄호가 닫히지 않았어요.")
            return value
        number = self.read_integer()
        self.skip_spaces()
        if self.take("d") or self.take("D"):
            return self.roll_dice(number, self.read_integer())
        return Decimal(number)

    def roll_dice(self, count: int, sides: int) -> Decimal:
        if not 1 <= count <= 100:
            raise DiceLimitError("한 번에 같은 주사위는 1~100개까지 굴릴 수 있어요.")
        if not 1 <= sides <= 1_000_000:
            raise DiceLimitError("주사위 눈 수는 1~1,000,000 사이의 정수여야 해요.")
        self.total_dice += count
        if self.total_dice > 200:
            raise DiceLimitError("한 식에서 굴릴 수 있는 주사위는 총 200개까지예요.")
        values = [random.randint(1, sides) for _ in range(count)]
        self.rolls.append(f"{count}d{sides} [{', '.join(map(str, values))}]")
        return Decimal(sum(values))

    def read_integer(self) -> int:
        self.skip_spaces()
        start = self.position
        while self.position < len(self.text) and self.text[self.position].isdigit():
            self.position += 1
        if self.position == start:
            raise DiceFormatError(f"{self.position + 1}번째 위치에 숫자나 주사위 식이 필요해요.")
        value = int(self.text[start:self.position])
        if value > 10**28:
            raise DiceFormatError("숫자가 너무 커요.")
        return value

    def take(self, char: str) -> bool:
        if self.position < len(self.text) and self.text[self.position] == char:
            self.position += 1
            return True
        return False

    def skip_spaces(self) -> None:
        while self.position < len(self.text) and self.text[self.position].isspace():
            self.position += 1

    @staticmethod
    def ensure_finite(value: Decimal) -> Decimal:
        if not value.is_finite() or abs(value) > Decimal("1000000000000"):
            raise DiceLimitError("계산 결과가 너무 커요.")
        return value


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


registry = SheetRegistry()
intents = discord.Intents.none()
intents.guilds = True
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)
synced_guilds: set[int] = set()
flat_webhooks: dict[int, discord.Webhook] = {}
flat_webhook_locks: dict[int, asyncio.Lock] = {}


async def send_response(interaction: discord.Interaction, content: str, *, ephemeral: bool = False) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral)


async def get_flat_webhook(
    channel: discord.TextChannel | discord.ForumChannel | discord.VoiceChannel | discord.StageChannel,
) -> discord.Webhook:
    lock = flat_webhook_locks.setdefault(channel.id, asyncio.Lock())
    async with lock:
        webhook = flat_webhooks.get(channel.id)
        if webhook is not None:
            return webhook
        avatar_path = Path(__file__).resolve().parent / "flat.png"
        avatar = await asyncio.to_thread(avatar_path.read_bytes)
        webhooks = await channel.webhooks()
        webhook = next((item for item in webhooks if item.name == FLAT_WEBHOOK_NAME), None)
        if webhook is None:
            webhook = await channel.create_webhook(
                name=FLAT_WEBHOOK_NAME,
                avatar=avatar,
                reason="응원과 운세의 플랫 연출용 웹훅",
            )
        else:
            webhook = await webhook.edit(
                avatar=avatar,
                reason="플랫 프로필 사진 업데이트",
            )
        flat_webhooks[channel.id] = webhook
        return webhook


async def send_flat_response(interaction: discord.Interaction, content: str) -> bool:
    channel = interaction.channel
    thread: discord.Thread | None = None
    if isinstance(channel, discord.Thread):
        thread = channel
        channel = channel.parent or await bot.fetch_channel(channel.parent_id)
    if not isinstance(
        channel,
        (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel, discord.StageChannel),
    ):
        print(f"Flat webhook skipped for unsupported channel ({type(channel).__name__}).")
        return False

    sent = False
    try:
        await interaction.response.defer(thinking=True)
        webhook = await get_flat_webhook(channel)
        send_options: dict[str, Any] = {"username": FLAT_DISPLAY_NAME, "wait": True}
        if thread is not None:
            send_options["thread"] = thread
        await webhook.send(content, **send_options)
        sent = True
    except Exception as exc:
        flat_webhooks.pop(channel.id, None)
        app_manage_webhooks = getattr(interaction.app_permissions, "manage_webhooks", None)
        status = getattr(exc, "status", None)
        code = getattr(exc, "code", None)
        print(
            f"Flat webhook response failed ({type(exc).__name__}; HTTP {status}; code {code}; "
            f"app_manage_webhooks={app_manage_webhooks}; channel={channel.id})."
        )
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(content=content)
            else:
                await interaction.response.send_message(content)
        except Exception as fallback_exc:
            print(f"Flat response fallback failed ({type(fallback_exc).__name__}).")
        return True

    if sent:
        try:
            await interaction.delete_original_response()
        except Exception as exc:
            print(f"Deferred interaction cleanup failed ({type(exc).__name__}).")
    return True


async def character_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    try:
        choices = await registry.get_character_choices_for_user(interaction.user.id)
        matches = [(value, name) for value, name in choices if not current or current.casefold() in name.casefold()]
        return [app_commands.Choice(name=trim_choice_name(name), value=value) for value, name in matches[:25]]
    except Exception:
        return []


async def sheet_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    try:
        sheets = await registry.get_available_sheets()
        matches = [(sheet.spreadsheet_id, sheet.title) for sheet in sheets if not current or current.casefold() in sheet.title.casefold()]
        return [app_commands.Choice(name=trim_choice_name(title), value=sheet_id) for sheet_id, title in matches[:25]]
    except SheetError as exc:
        print(f"Spreadsheet autocomplete failed: {exc}")
        return []
    except Exception as exc:
        print(f"Spreadsheet autocomplete failed ({type(exc).__name__}).")
        return []


async def registration_character_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    # The interaction namespace uses the renamed Discord option name (Korean)
    # on some discord.py versions, and the Python parameter name on others.
    sheet_id = getattr(interaction.namespace, "sheet", None) or getattr(interaction.namespace, "시트", None)
    if not sheet_id:
        print("Character tab autocomplete skipped: selected sheet was missing from the interaction options.")
        return []
    try:
        choices = await registry.get_character_tab_choices(sheet_id)
        matches = [(value, name) for value, name in choices if not current or current.casefold() in name.casefold()]
        return [app_commands.Choice(name=trim_choice_name(name), value=value) for value, name in matches[:25]]
    except SheetError as exc:
        print(f"Character tab autocomplete failed for {sheet_id}: {exc}")
        return []
    except Exception as exc:
        print(f"Character tab autocomplete failed for {sheet_id} ({type(exc).__name__}).")
        return []


async def skill_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    character = getattr(interaction.namespace, "character", None) or getattr(interaction.namespace, "캐릭터", None)
    if not character:
        return []
    try:
        skills = await registry.get_skills(character)
        matches = [skill for skill in skills if not current or current.casefold() in skill.casefold()]
        return [app_commands.Choice(name=trim_choice_name(skill), value=skill) for skill in matches[:25]]
    except Exception:
        return []


async def roll_mode_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    modes = [("패널티 +1", "패널티+1"), ("패널티 +2", "패널티+2"), ("보너스 +1", "보너스+1"), ("보너스 +2", "보너스+2")]
    return [app_commands.Choice(name=name, value=value) for name, value in modes if not current or current.casefold() in name.casefold() or current.casefold() in value.casefold()]


@dataclass
class CombatParticipant:
    user_id: int
    player_name: str
    character_value: str
    character_name: str
    dexterity: int = 0
    strength: int = 0
    constitution: int = 0
    size: int = 0
    hp: int = 0
    max_hp: int = 0
    is_pulp: bool = False
    weapons: list[CombatWeapon] = field(default_factory=list)
    weapon_states: dict[tuple[str, str, int], tuple[int | None, bool, int | None, int]] = field(default_factory=dict)
    defended_round: int = 0
    cover_active: bool = False
    movement_choice: str = ""
    major_wound: bool = False
    temporarily_treated: bool = False
    spirit: int | None = None
    sanity: int | None = None
    starting_sanity: int | None = None
    sanity_lost: int = 0
    permanently_insane: bool = False
    madness: str = ""
    madness_long: bool = False
    madness_turns: int = 0
    madness_last_start: int = -1
    madness_last_end: int = -1
    madness_skip_end: int = -1
    madness_knockout: bool = False
    compulsive_weapon: tuple[str, str] | None = None
    fog_checked_round: int = 0
    encounter_sanity_checked: bool = False
    unconscious: bool = False
    forfeited: bool = False
    sacrificed: bool = False
    doom_defeated: bool = False
    doom_dead: bool = False
    domination_source: int | None = None
    domination_user: int | None = None
    domination_turns: int = 0
    domination_skip_end: int = -1
    domination_last_end: int = -1
    dream_asleep: bool = False
    dream_blind: bool = False
    dream_betrayal: bool = False
    dream_forbidden: tuple[str, str] | None = None
    dream_star: int = 0
    dream_last_end: int = -1
    dream_angel: bool = False
    last_used_weapon: tuple[str, str] | None = None
    status_effects: list[CombatStatusEffect] = field(default_factory=list)
    enemy_id: str = ""
    kitchen_owner: Any = None
    kitchen_control: bool = False
    kitchen_tears: bool = False
    damage_dealt: int = 0
    damage_received: int = 0
    armor: int = 0
    mana_barrier: int = 0
    mana_barrier_max: int = 40
    barrier_rebuild: bool = False
    silenced: bool = False
    guarded_round: int = 0
    enemy_skills: dict[str, int] = field(default_factory=dict)
    pattern_step: int = 0
    regeneration_used: bool = False
    recovering: bool = False
    enemy_specials: list[str] = field(default_factory=list)
    actions_left: int = 0
    action_dice_sides: int = 3
    summons_used: int = 0
    round_attack_due: int = 0
    round_attack_target: int | None = None
    round_attack_distance: int = 2
    spawn_round: int = 0
    armor_boosted: bool = False
    snared: bool = False
    hunt_target: int | None = None
    hunt_attacks_left: int = 0
    magic_points: int | None = None
    position: int = 0
    field_symbol: str = ""
    paralysis_stacks: int = 0
    paralysis_skip_end_serial: int = -1

    @property
    def build(self) -> int:
        return combat_build(self.strength, self.size)

    @property
    def paralyzed(self) -> bool:
        return self.paralysis_stacks > 0


@dataclass
class PendingCombatAttack:
    attacker_index: int
    target_index: int
    weapon_index: int
    skill_value: int
    shot_count: int
    hits: list[tuple[int, str, int]] = field(default_factory=list)
    stage: str = "rolling"
    luck_value: int | None = None
    fumble_weapon: CombatWeapon | None = None
    modifier: int = 0
    resume_turn_index: int | None = None
    remaining_targets: list[int] = field(default_factory=list)
    spell_costs: dict[str, int] = field(default_factory=dict)
    spell_deferred_costs: dict[str, str] = field(default_factory=dict)
    spell_defense_value: int = 0
    spell_defenses: dict[int, int] = field(default_factory=dict)
    spell_result: str = ""
    family_spell: str = ""
    kitchen_checked: bool = False
    kitchen_control: bool = False
    kitchen_next_hit: int = 0
    spell_paid: bool = False
    spell_donations: dict[int, int] = field(default_factory=dict)
    spell_sacrifice: int | None = None
    spell_requested_donor: int | None = None
    spell_request_serial: int = 0


@dataclass
class DreamEvent:
    kind: str
    due: int
    position: int | None = None
    damage_start: int = 0
    threshold: int = 0


@dataclass
class CombatSession:
    guild_id: int
    channel_id: int
    owner_id: int
    participants: list[CombatParticipant]
    message: discord.Message | None = None
    phase: str = "lobby"
    round_number: int = 1
    turn_index: int = 0
    turn_serial: int = 1
    initiative_logs: list[str] = field(default_factory=list)
    recent_logs: list[str] = field(default_factory=list)
    pending_attack: PendingCombatAttack | None = None
    briefing: str = ""
    last_attack: str = ""
    last_attack_events: list[str] = field(default_factory=list)
    elimination_order: list[int] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    mode: str = "개인전"
    enemy_id: str = ""
    turn_order: list[int] = field(default_factory=list)
    fog_start_round: int = 0
    fog_processed_round: int = 0
    annihilated: bool = False
    encounter_sanity_done: bool = False
    annihilation_logs: list[str] = field(default_factory=list)
    dream_hatched: bool = False
    dream_boss_turns: int = 0
    dream_last_action: int = -1
    dream_result: str = ""
    dream_events: list[DreamEvent] = field(default_factory=list)
    dream_difficulty: int = 1
    kitchen_state: Any = None
    family_spawned: bool = False
    family_last_serial: int = -1
    family_ops: list[dict[str, Any]] = field(default_factory=list)
    family_events: list[dict[str, Any]] = field(default_factory=list)
    family_mage_turns: int = 0
    family_last_spell: str = ""
    family_revenge: bool = False


class CombatLogEntry(str):
    """Keep turn identity alongside text without changing log consumers."""

    def __new__(cls, text: str, turn_serial: int):
        entry = super().__new__(cls, text)
        entry.turn_serial = turn_serial
        return entry


def append_combat_log(session: CombatSession, text: str) -> None:
    session.recent_logs.append(CombatLogEntry(text, session.turn_serial))


combat_sessions: dict[int, CombatSession] = {}
COMBAT_RECENT_LOG_LIMIT = 6

# Raid opponents use local values; they never request a Google character sheet.
RAID_ENEMIES = {
    "dummy": {"name": "연습용 허수아비", "dex": 10, "con": 100, "str": 10, "size": 50,
              "fight": 0, "dodge": 0, "gun": 0, "luck": 50},
    "chimera": {"name": "실험키메라", "dex": 55, "con": 60, "str": 60, "size": 65,
                "fight": 50, "dodge": 25, "gun": 0, "luck": 50},
    "dream": {"name": "꿈꾸는 고치", "dex": 40, "con": 100, "str": 100, "size": 200,
              "fight": 30, "dodge": 0, "gun": 0, "luck": 70, "pow": 120, "dream_attack": 80},
    "kitchen": {"name": "성난 반죽", "dex": 45, "con": 60, "str": 40, "size": 50,
                "fight": 60, "dodge": 15, "gun": 0, "luck": 50, "pow": 30},
    "hunter": {"name": "딜리아", "dex": 75, "con": 85, "str": 75, "size": 70,
               "fight": 90, "dodge": 75, "gun": 20, "luck": 76, "pow": 85},
    "mage": {"name": "디안", "dex": 50, "con": 35, "str": 45, "size": 50,
             "fight": 25, "dodge": 43, "gun": 20, "luck": 70, "pow": 95, "magic": 95},
    "minion": {"name": "실험체", "dex": 35, "con": 30, "str": 20, "size": 20,
               "fight": 35, "dodge": 15, "gun": 0, "luck": 30},
}

CHIMERA_SPECIALS = {
    "swallow": "삼키기", "poison": "독 분사", "tail": "꼬리 휩쓸기", "charge": "돌진", "burst": "폭주 분출",
}
CHIMERA_SPECIAL_DETAILS = {
    "burst": "전원에게 각각 1d6 공격 · 회피 가능, 반격 불가 · 엄폐 시 공격 패널티 +1",
    "swallow": "1d3+DB 피해 + 충격 · 근접전(격투)으로 탈출 · 유지 중 키메라는 다른 공격 불가",
    "poison": "1d3 피해 + 지속 · 매 턴 시작 1d3 피해 후 건강 판정으로 해제 · 회피 가능",
    "tail": "1d4+DB 피해 · 명중하면 대상을 반대 방향으로 한 칸 밀어냄",
    "charge": "민첩 판정으로 근거리까지 돌진 · 성공하면 1d6+DB 공격, 실패하면 이동 후 턴 종료",
}
MADNESS_LINES = {
    "심신성 장애": ("팔다리가 남의 것처럼 움직입니다.", "몸 안에서 누군가 힘줄을 잡아당깁니다.", "움직일 때마다 뼈가 뒤틀리는 느낌이 듭니다."),
    "폭력성": ("숨 쉬는 것들이 모두 적으로 보입니다.", "누군가 쓰러져야 이 소리가 멎을 것 같습니다.", "동료의 얼굴 위로 적의 얼굴이 겹쳐집니다."),
    "편집증": ("다가오는 손이 목을 조르려는 것 같습니다.", "동료들이 당신 몰래 웃고 있습니다.", "도와주겠다는 말 뒤에 살의가 들립니다."),
    "기절": ("어둠 속에서 당신의 몸이 멀어집니다.", "누군가 당신의 눈꺼풀을 안에서 누릅니다.", "깨어나야 합니다. 몸이 말을 듣지 않습니다."),
    "도주": ("등 뒤에서 무언가 입을 벌립니다.", "멈추면 잡힙니다. 당신은 알고 있습니다.", "가까이 있는 것들이 당신을 집어삼킬 겁니다."),
    "발작적 행동": ("피부 아래의 무언가를 꺼내야 합니다.", "몸 안에서 긁는 소리가 멎지 않습니다.", "당신의 손이 낯선 명령에 움직입니다."),
    "강박": ("같은 일을 반복해야 무언가 깨어나지 않습니다.", "그만두는 순간 그것이 들어옵니다.", "한 번 더. 아직 끝나지 않았습니다."),
    "감각 왜곡": ("동료의 목소리가 적의 입에서 들립니다.", "분명 적이었습니다. 눈을 깜빡이기 전까지는.", "얼굴들이 제자리를 바꿔 달라붙습니다."),
    "집중 붕괴": ("생각 사이로 낯선 목소리가 스며듭니다.", "당신의 기억을 누군가 뒤지고 있습니다.", "머릿속에서 당신 아닌 누군가가 생각합니다."),
    "떨림": ("손끝에 매달린 무언가가 팔을 흔듭니다.", "손이 떨립니다. 그림자는 움직이지 않습니다.", "손가락이 당신 뜻과 반대로 꺾이려 합니다."),
}


def combat_madness_label(member: CombatParticipant) -> str:
    if member.permanently_insane:
        return "영구 광기 · 탈락"
    if not member.madness:
        return ""
    duration = "장기 광기" if member.madness_long else f"일시적 광기 · 남은 {member.madness_turns}턴"
    return f"{member.madness} · {duration}"


def lose_combat_sanity(session: CombatSession, member: CombatParticipant, amount: int) -> int:
    if member.sanity is None:
        raise SheetError("현재 이성 값을 읽지 못했어요.")
    if member.starting_sanity is None:
        member.starting_sanity = member.sanity
    loss = min(member.sanity, max(0, amount))
    member.sanity -= loss
    member.sanity_lost += loss
    if member.sanity == 0 and not member.enemy_id:
        if not member.permanently_insane:
            member.permanently_insane = True
            member.madness = ""
            member.madness_long = False
            member.madness_turns = 0
            member.compulsive_weapon = None
            member.cover_active = False
            record_combat_elimination(session, member)
            append_combat_log(session, f"【영구 광기 · 탈락】 {member.character_name} · 이성 0")
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        return loss
    long_term = bool(member.starting_sanity and member.sanity_lost * 5 >= member.starting_sanity)
    if loss <= 0 or member.madness_long or (loss < 5 and not long_term):
        return loss
    if not member.madness:
        member.madness = random.choice(list(MADNESS_LINES))
        member.compulsive_weapon = None
        if member.madness == "기절" and not member.unconscious:
            member.unconscious = True
            member.madness_knockout = True
            member.cover_active = False
            record_combat_elimination(session, member)
    if long_term:
        member.madness_long = True
        member.madness_turns = 0
    else:
        member.madness_turns = max(member.madness_turns, random.randint(1, 10))
        if session.participants[session.turn_index] is member:
            member.madness_skip_end = session.turn_serial
    append_combat_log(session, f"【{combat_madness_label(member)}】 {member.character_name}")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    return loss


def end_combat_madness_turn(session: CombatSession, member: CombatParticipant) -> None:
    if not member.madness or member.madness_long or member.madness_last_end == session.turn_serial or member.madness_skip_end == session.turn_serial:
        return
    member.madness_last_end = session.turn_serial
    member.madness_turns -= 1
    if member.madness_turns > 0:
        return
    if member.madness_knockout:
        member.unconscious = False
        member.madness_knockout = False
    member.madness = ""
    member.compulsive_weapon = None
    append_combat_log(session, f"【일시적 광기 종료】 {member.character_name}")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]


def lock_compulsive_weapon(member: CombatParticipant, weapon: CombatWeapon) -> None:
    member.last_used_weapon = (weapon.name, weapon.skill_reference)
    if member.madness == "강박" and member.compulsive_weapon is None:
        member.compulsive_weapon = (weapon.name, weapon.skill_reference)


def compulsion_allows(member: CombatParticipant, weapon: CombatWeapon) -> bool:
    return member.madness != "강박" or member.compulsive_weapon is None or member.compulsive_weapon == (weapon.name, weapon.skill_reference)


def missing_compulsive_weapon(member: CombatParticipant) -> bool:
    return (member.madness == "강박" and member.compulsive_weapon is not None
            and not any((weapon.name, weapon.skill_reference) == member.compulsive_weapon for weapon in member.weapons))


def available_combat_weapon(session: CombatSession, index: int) -> bool:
    member = session.participants[session.turn_index]
    weapon = member.weapons[index]
    if member.silenced and is_spell_weapon(weapon):
        return False
    if member.dream_forbidden == (weapon.name, weapon.skill_reference):
        return member.madness == "강박" and member.compulsive_weapon == member.dream_forbidden
    if member.madness == "도주" or not compulsion_allows(member, weapon):
        return False
    if member.madness == "강박" and member.compulsive_weapon is not None:
        return True
    return bool(combat_targets(session, weapon))


async def redirect_madness_attack(session: CombatSession, weapon: CombatWeapon, target: int) -> int:
    current = session.participants[session.turn_index]
    if current.dream_betrayal:
        return target
    if current.madness == "폭력성":
        chosen = random.choice(combat_targets(session, weapon))
        append_combat_log(session, f"【폭력성】 대상: {session.participants[chosen].character_name}")
        return chosen
    if current.madness != "감각 왜곡":
        return target
    luck = await combat_skill_value(current, "행운")
    if luck is None:
        raise SheetError("감각 왜곡 판정에 필요한 행운 값을 읽지 못했어요.")
    roll, rolls, modifier = roll_combat_d100(current, session=session)
    succeeded = combat_success_rank(coc_combat_check_result(roll, luck)) > 0
    chosen = target
    if not succeeded:
        friends = [index for index, member in enumerate(session.participants)
                   if index != session.turn_index and not member.enemy_id and combat_is_active(member)
                   and session.mode == "레이드" and (not is_melee_weapon(weapon)
                       or combat_distance(session, session.turn_index, index) == "근거리")]
        chosen = random.choice(friends) if friends else session.turn_index
    append_combat_log(session, f"행운 {combat_roll_text(current, roll, rolls, modifier, session=session)} / {luck}\n"
                      f"【감각 왜곡 {'성공' if succeeded else '실패'}】 대상: {session.participants[chosen].character_name}")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    return chosen


BLACK_FOG_VISIONS = (
    "동료들이 당신의 시신을 묻고 있습니다.",
    "입 안에서 낯선 손이 이빨을 벌립니다.",
    "동료의 얼굴 밑에서 다른 얼굴이 꿈틀댑니다.",
    "당신의 시체가 발목을 붙잡고 끌어내립니다.",
    "눈꺼풀 안쪽을 누군가 긁고 있습니다.",
    "벌어진 가슴 안에서 당신이 비명을 지릅니다.",
    "관 뚜껑이 닫히고 얼굴 위로 흙이 쏟아집니다.",
    "뒤돌아보니 당신의 몸이 조각나 흩어져 있습니다.",
    "뒤통수에 생긴 입이 당신 대신 대답합니다.",
    "동료의 목구멍 속에서 당신이 질식하고 있습니다.",
    "얼굴 없는 당신이 당신의 얼굴을 벗겨갑니다.",
    "멎은 심장 안에서 무언가 나오려 발버둥칩니다.",
)


CHIMERA_ROUND_WARNINGS = {
    7: "통로 너머에서 철문이 하나씩 닫히는 소리가 들려요. 아직 돌아갈 수 있을까요?",
    8: "경보음이 갑자기 끊겼어요. 벽 너머에서 무언가가 천천히 움직이고 있어요.",
    9: "출구 아래로 검은 액체가 스며들어요. 이제 이곳에 남은 시간이 얼마 없어요.",
    10: "검은 안개가 실험구역을 덮쳐옵니다. 정신을 붙잡지 못하면 안개에 삼켜집니다…",
}


def make_raid_enemy(enemy_id: str) -> CombatParticipant:
    spec = RAID_ENEMIES[enemy_id]
    return CombatParticipant(0, "연습용 상대", "연습용 상대 | " + spec["name"], spec["name"], enemy_id=enemy_id)


def randomize_raid_enemy(member: CombatParticipant, player_count: int) -> None:
    if kitchen.is_enemy(member):
        kitchen.configure_enemy(member, player_count)
        return
    if member.enemy_id in {"hunter", "mage"}:
        member.enemy_skills = dict(RAID_ENEMIES[member.enemy_id])
        member.max_hp = 30 if member.enemy_id == "hunter" else 8
        member.magic_points = 17 if member.enemy_id == "hunter" else 19
        if member.enemy_id == "mage":
            member.mana_barrier = 40
        return
    if member.enemy_id == "dream":
        member.enemy_skills = dict(RAID_ENEMIES["dream"])
        member.max_hp = max(60, 30 * player_count)
        member.recovering = True
        member.dream_angel = False
        return
    if member.enemy_id != "chimera":
        return
    member.enemy_skills = {
        "dex": random.randint(25, 85), "con": random.randint(30, 90),
        "str": random.randint(30, 90), "size": random.randint(50, 120),
        "fight": random.randint(30, 75), "dodge": random.randint(10, 50),
        "luck": random.randint(20, 80), "pow": random.randint(30, 90), "gun": 0,
    }
    member.max_hp = 35 + 15 * (max(1, player_count) - 2) + random.randint(-10, 15)
    member.armor = 1
    member.pattern_step = 0
    member.regeneration_used = False
    member.recovering = False
    member.actions_left = 0
    member.action_dice_sides = 2 if player_count <= 2 else 3
    member.summons_used = 0
    member.round_attack_due = 0
    member.round_attack_target = None
    member.armor_boosted = False
    member.hunt_target = None
    member.hunt_attacks_left = 0
    member.enemy_specials = random.sample(list(CHIMERA_SPECIALS), 2)


async def combat_skill_value(member: CombatParticipant, skill: str) -> int | None:
    if not member.enemy_id:
        if skill == "정신":
            if member.spirit is None:
                member.spirit = await registry.get_skill_value(member.character_value, skill)
            return member.spirit
        if skill == "이성" and member.sanity is not None:
            return member.sanity
        return await registry.get_skill_value(member.character_value, skill)
    spec = member.enemy_skills or RAID_ENEMIES[member.enemy_id]
    key = {"민첩": "dex", "근력": "str", "건강": "con", "크기": "size", "회피": "dodge", "행운": "luck"}.get(skill)
    if skill == "정신":
        return spec.get("pow", 60 if member.enemy_id == "chimera" else 30)
    if key:
        return spec[key]
    if "근접전" in skill:
        return spec["fight"]
    if "사격" in skill:
        return spec["gun"]
    if member.enemy_id == "dream" and skill == "꿈의 침식":
        return spec["dream_attack"]
    if skill == "마법" and member.enemy_id == "mage":
        return spec["magic"]
    if skill == "생체 공격":
        return spec["fight"]
    return 20


async def combat_weapons(member: CombatParticipant, *, refresh: bool = False) -> list[CombatWeapon]:
    if kitchen.is_enemy(member):
        return kitchen.weapons(member)
    if not member.enemy_id:
        return await registry.get_combat_weapons(member.character_value, refresh=refresh)
    if member.enemy_id == "hunter":
        return [CombatWeapon("비무장", "근접전 | 격투", "1d3", damage_bonus="DB"),
                CombatWeapon("정글도", "근접전 | 격투", "1d8", damage_bonus="DB", impaling=True),
                CombatWeapon("힘줄 베기", "근접전 | 격투", "1d4", damage_bonus="DB", effects=[CombatStatusSpec(("마비",), "건강")])]
    if member.enemy_id == "mage":
        return [CombatWeapon("비무장", "근접전 | 격투", "1d3"), CombatWeapon("마력탄", "마법", "1d6")]
    if member.enemy_id == "dream":
        return [CombatWeapon("비무장 · 그림자", "근접전 | 격투", "1d4"),
                CombatWeapon("접히는 실", "꿈의 침식", "1d4"),
                CombatWeapon("날개의 잔향", "꿈의 침식", "1d6"),
                CombatWeapon("뒤늦은 그림자", "꿈의 침식", "2d4")]
    if member.enemy_id == "minion":
        return [CombatWeapon("비무장 · 물어뜯기", "근접전 | 격투", "1d3")]
    if member.enemy_id == "chimera":
        weapons = [CombatWeapon("비무장 · 발톱", "근접전 | 격투", "1d6", damage_bonus="DB"),
                   CombatWeapon("덮치기", "근접전 | 격투", "1d8", damage_bonus="DB")]
        specials = {
            "swallow": CombatWeapon("삼키기", "근접전 | 격투", "1d3", effects=[CombatStatusSpec(("충격",), "근접전")]),
            "poison": CombatWeapon("독 분사", "생체 공격", "1d3", effects=[CombatStatusSpec(("지속",), "건강")]),
            "tail": CombatWeapon("꼬리 휩쓸기", "근접전 | 격투", "1d4", knockback=True),
            "charge": CombatWeapon("돌진", "근접전 | 격투", "1d6"),
            "burst": CombatWeapon("폭주 분출", "생체 공격", "1d6"),
        }
        chosen = [specials[key] for key in member.enemy_specials]
        for weapon in chosen:
            if is_melee_weapon(weapon):
                weapon.damage_bonus = "DB"
        return weapons + chosen + [CombatWeapon("폭주 도약", "근접전 | 격투", "2d4", damage_bonus="DB")]
    return []


def combat_opponents(session: CombatSession, first: int, second: int) -> bool:
    if session.enemy_id == "hunter" and first != second:
        a, b = session.participants[first], session.participants[second]
        if a.enemy_id == "mage" or b.enemy_id == "mage":
            return True
        if a.enemy_id == "hunter" and not b.enemy_id:
            return not (session.family_spawned and any(p.enemy_id == "mage" and combat_is_present(p) for p in session.participants))
        if b.enemy_id == "hunter" and not a.enemy_id:
            return True
    return first != second and (session.mode != "레이드" or
        bool(session.participants[first].enemy_id) != bool(session.participants[second].enemy_id))


def combat_is_present(member: CombatParticipant) -> bool:
    return (member.enemy_id == "dummy" or member.hp > 0) and not member.forfeited and not member.sacrificed and not member.doom_defeated and not member.permanently_insane


def combat_is_active(member: CombatParticipant) -> bool:
    return combat_is_present(member) and not member.unconscious and not member.dream_asleep


def apply_combat_damage(target: CombatParticipant, damage: int, source: CombatParticipant, *, ignore_armor: bool = False, weapon: CombatWeapon | None = None) -> tuple[int, str]:
    raw_damage = damage
    if kitchen.enemy_kind(target) == "pot":
        return 0, "냄비는 공격 대신 불을 줄여 주세요!"
    if target.enemy_id == "mage" and target.mana_barrier > 0 and not ignore_armor:
        shield_damage = max(0, damage) * (2 if source.enemy_id == "hunter" and weapon is not None and weapon.name == "정글도" else 1)
        previous = target.mana_barrier
        target.mana_barrier = max(0, previous - shield_damage)
        target.damage_received += min(previous, shield_damage)
        if source is not target:
            source.damage_dealt += min(previous, shield_damage)
        if target.mana_barrier == 0:
            target.barrier_rebuild = True
        return 0, f"마력장벽 {previous} → {target.mana_barrier}" + (" · 【장벽 파괴】" if not target.mana_barrier else "")
    damage = max(0, damage - (0 if ignore_armor else target.armor))
    armor_text = f"장갑 {target.armor}: {raw_damage} → {damage} · " if target.armor and not ignore_armor else ""
    if target.enemy_id:
        target.damage_received += damage
        if source is not target:
            source.damage_dealt += damage
    if target.enemy_id == "dummy":
        return damage, f"누적 피해 {target.damage_received}"
    reopened = ""
    if damage > 0 and target.temporarily_treated:
        target.temporarily_treated = False
        target.major_wound = True
        reopened = " · 【상처 재발 · 중상】"
    previous_hp = target.hp
    kitchen_note = kitchen.damage_note(target, damage, weapon, source) if target.kitchen_owner is not None else ""
    target.hp = max(1 if target.enemy_id == "dream" else 0, target.hp - damage)
    broken_armor = ""
    if target.armor_boosted and raw_damage >= 5 and not ignore_armor:
        target.armor_boosted = False
        target.armor = 1
        broken_armor = " · 【강화 장갑 파괴!】"
    return damage, f"{armor_text}HP {previous_hp} → {target.hp}{' · 【전투불능】' if target.hp == 0 else ''}{broken_armor}{reopened}{kitchen_note}"


def calculate_combat_max_hp(member: CombatParticipant) -> int:
    divisor = 5 if member.is_pulp else 10
    return max(1, (member.constitution + member.size) // divisor)


def active_combat_statuses(session: CombatSession, member: CombatParticipant) -> list[CombatStatusEffect]:
    # Turn changes never expire shock; losing its active source does.
    return [effect for effect in member.status_effects
            if "충격" not in effect.spec.kinds or combat_is_active(session.participants[effect.source_index])]


def combat_is_shocked(session: CombatSession, member: CombatParticipant) -> bool:
    return any("충격" in effect.spec.kinds for effect in active_combat_statuses(session, member))


def maintaining_combat_shock(session: CombatSession | None, member: CombatParticipant) -> bool:
    if session is None or not combat_is_active(member):
        return False
    return any(
        combat_is_present(target) and any(
            "충격" in effect.spec.kinds and not effect.spec.independent_hold and session.participants[effect.source_index] is member
            for effect in active_combat_statuses(session, target)
        ) for target in session.participants
    )


def releasable_combat_statuses(session: CombatSession, member: CombatParticipant) -> list[tuple[CombatParticipant, CombatStatusEffect]]:
    source_index = next(i for i, participant in enumerate(session.participants) if participant is member)
    return [(target, effect) for target in session.participants if combat_is_present(target)
            for effect in active_combat_statuses(session, target)
            if effect.source_index == source_index and (effect.retrievable or "충격" in effect.spec.kinds)]


def roll_combat_d100(member: CombatParticipant, modifier: int = 0, *, session: CombatSession | None = None, context: str = "", weapon: CombatWeapon | None = None) -> tuple[int, list[int], int]:
    modifier -= int(member.major_wound)
    if member.kitchen_tears:
        modifier -= 1
        member.kitchen_tears = False
    modifier -= int(maintaining_combat_shock(session, member))
    if session is not None and any(effect.spec.independent_hold and session.participants[effect.source_index] is member
                                   for target in session.participants if combat_is_present(target)
                                   for effect in active_combat_statuses(session, target)):
        modifier -= 1
    modifier -= member.paralysis_stacks
    if session is not None and context == "defense" and member.guarded_round > 0:
        modifier += 1
    if member.dream_blind and context in {"attack", "spell_attack"}:
        modifier -= 1
    if member.madness == "심신성 장애" and context in {"attack", "defense", "spell_attack"}:
        modifier -= 1
    if member.madness == "떨림" and context == "attack" and weapon is not None and is_projectile_weapon(weapon):
        modifier -= 1
    if member.madness == "집중 붕괴" and context in {"spirit", "spell_attack"}:
        modifier -= 1
    rolls = [random.randint(1, 100) for _ in range(abs(modifier) + 1)]
    return (min(rolls) if modifier > 0 else max(rolls)), rolls, modifier


def combat_roll_text(member: CombatParticipant, roll: int, rolls: list[int], modifier: int, *, session: CombatSession | None = None) -> str:
    mode = f" · 보너스 +{modifier}" if modifier > 0 else f" · 패널티 +{-modifier}" if modifier < 0 else ""
    selected = f" → {roll}" if len(rolls) > 1 else ""
    reasons = []
    if member.major_wound:
        reasons.append("중상")
    if maintaining_combat_shock(session, member):
        reasons.append("충격 유지")
    if member.paralyzed:
        reasons.append(f"마비 {member.paralysis_stacks}")
    source = f" ({', '.join(reasons)})" if reasons else ""
    return f"1d100 [{', '.join(map(str, rolls))}]{selected}{mode}{source}"



def combat_success_rank(result: str) -> int:
    return {"대실패": 0, "실패": 0, "보통 성공": 1, "어려운 성공": 2, "극단적 성공": 3, "대성공": 4}[result]


def status_escape_label(spec: CombatStatusSpec) -> str:
    suffix = {1: "", 2: " 어려움", 3: " 극단"}[spec.escape_difficulty]
    return spec.escape_skill + suffix


def combat_spell_summary(weapon: CombatWeapon) -> str:
    prefix = f"대가 {weapon.spell_cost_text or '없음'}"
    if weapon.damage.strip() == "지배":
        return prefix + " · 지배 1턴 · 근거리"
    if weapon.damage.strip() == "멸망":
        return prefix + " · 멸망"
    return prefix + (" · 건강 판정으로 저항" if weapon.health_resisted_spell else "") + f" · 피해 {weapon.damage}" + (f" + 지속 피해 {weapon.damage}" if any("지속" in effect.kinds for effect in weapon.effects) else "")


def is_spell_weapon(weapon: CombatWeapon) -> bool:
    return weapon.skill_reference.strip() == "주문"


def spell_mana_sources(session: CombatSession, *, corpses: bool = False) -> list[int]:
    caster = session.participants[session.turn_index]
    if corpses:
        return [i for i, member in enumerate(session.participants) if not member.enemy_id
                and member is not caster and (member.hp <= 0 or member.permanently_insane) and not member.forfeited and not member.sacrificed
                and (member.magic_points or 0) > 0]
    return [i for i, member in enumerate(session.participants) if not member.enemy_id
            and member is not caster and session.mode == "레이드" and combat_is_active(member)
            and (member.magic_points or 0) > 0]


def spell_funding_hp(session: CombatSession, attack: PendingCombatAttack) -> int:
    caster = session.participants[attack.attacker_index]
    corpse_mp = (session.participants[attack.spell_sacrifice].magic_points or 0) if attack.spell_sacrifice is not None else 0
    return max(0, attack.spell_costs.get("마력", 0) - sum(attack.spell_donations.values()) - (caster.magic_points or 0) - corpse_mp)


def spell_funding_prompt(session: CombatSession) -> str:
    attack = session.pending_attack
    if attack is None:
        return ""
    weapon = session.participants[attack.attacker_index].weapons[attack.weapon_index]
    text = "주문 대가: " + (weapon.spell_cost_text or "없음")
    if attack.spell_donations:
        text += "\n마력 제공: " + " · ".join(f"{session.participants[i].character_name} {amount}" for i, amount in attack.spell_donations.items())
    if attack.spell_sacrifice is not None:
        corpse = session.participants[attack.spell_sacrifice]
        text += f"\n제물: {corpse.character_name} · 남은 마력 {corpse.magic_points} 전부"
    hp = spell_funding_hp(session, attack)
    return text + (f"\n마력이 {hp} 부족해요. 대신 HP {hp}을 소모해서 시전할까요?" if hp else "\n시전할까요?")


def roll_spell_costs(text: str, deferred: dict[str, str] | None = None) -> dict[str, int]:
    costs = {}
    for item in re.split(r"[,，;；]", text.replace("：", ":")):
        if not item.strip():
            continue
        resource, sep, formula = item.partition(":")
        resource = resource.strip()
        formula = formula.strip().lower().replace(" ", "")
        if (not sep or resource not in {"마력", "이성", "정신"} or resource in costs
                or not re.fullmatch(r"(?:\d+|\d{1,2}d\d{1,3})(?:[+]\d+)?", formula)):
            raise SheetError("주문 대가는 탄약 칸에 '마력:8, 이성:1d6'처럼 적어 주세요.")
        dice = re.match(r"(\d+)d(\d+)", formula)
        if dice and (int(dice.group(1)) < 1 or int(dice.group(2)) < 1):
            raise SheetError("주문 대가의 주사위 개수와 면 수는 1 이상이어야 해요.")
        if deferred is not None and resource != "마력" and "d" in formula:
            deferred[resource] = formula
            costs[resource] = 0
        else:
            costs[resource] = roll_damage_formula(formula)[0]
    return costs


def combat_is_controlled(session: CombatSession, index: int) -> bool:
    member = session.participants[index]
    return (member.domination_source is not None and member.domination_turns > 0
            and combat_is_active(session.participants[member.domination_source]))


def combat_actor_user(session: CombatSession, member: CombatParticipant) -> int:
    if member is session.participants[session.turn_index] and combat_is_controlled(session, session.turn_index):
        source = session.participants[member.domination_source]
        return member.domination_user if member.domination_user is not None else source.user_id
    return member.user_id


def end_combat_domination_turn(session: CombatSession, member: CombatParticipant) -> None:
    if member.domination_source is None or member.domination_skip_end == session.turn_serial or member.domination_last_end == session.turn_serial:
        return
    member.domination_last_end = session.turn_serial
    member.domination_turns -= 1
    if member.domination_turns <= 0:
        member.domination_source = member.domination_user = None
        append_combat_log(session, f"【지배 해제】 {member.character_name}")
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]


def apply_combat_domination(session: CombatSession, attack: PendingCombatAttack) -> None:
    caster = session.participants[attack.attacker_index]
    target = session.participants[attack.target_index]
    if target.enemy_id in {"chimera", "dream"} or (target.enemy_id == "mage" and target.mana_barrier > 0):
        append_combat_log(session, f"【지배 면역】 {target.character_name}")
        session.last_attack_events.append(f"{target.character_name} · 지배 면역")
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        return
    if not combat_is_active(caster):
        append_combat_log(session, "【지배 실패】 시전자가 지배를 유지할 수 없어요.")
        return
    target.domination_user = combat_actor_user(session, caster)
    target.domination_source = attack.attacker_index
    target.domination_turns = 1
    target.domination_skip_end = session.turn_serial if session.turn_index == attack.target_index else -1
    target.domination_last_end = -1
    append_combat_log(session, f"【지배】 {target.character_name}의 다음 차례는 {caster.character_name}이 지시해요.")
    session.last_attack_events.append(f"{target.character_name} · 1턴 지배")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]


def combat_distance(session: CombatSession, first: int, second: int) -> str:
    gap = abs(session.participants[first].position - session.participants[second].position)
    close_gap = 1 if session.mode == "레이드" else 0
    return "근거리" if gap <= close_gap else "보통거리" if gap == close_gap + 1 else "먼 거리"


def move_combat_position(session: CombatSession, mover: int, target: int, direction: int, *, adjacent: bool = False) -> None:
    member, other = session.participants[mover], session.participants[target]
    delta = other.position - member.position
    sign = 1 if delta >= 0 else -1
    if adjacent:
        close_gap = 1 if session.mode == "레이드" else 0
        member.position = other.position - sign * close_gap
    else:
        member.position += sign * (-direction)
    separate_combat_boss_position(session)


def separate_combat_boss_position(session: CombatSession) -> None:
    if session.mode != "레이드":
        return
    allied_hunter = session.enemy_id == "hunter" and any(p.enemy_id == "mage" and combat_is_present(p) for p in session.participants)
    boss_positions = {member.position for member in session.participants
                      if member.enemy_id and member.enemy_id != "minion" and not kitchen.is_enemy(member) and combat_is_active(member)
                      and not (allied_hunter and member.enemy_id == "hunter")}
    for member in session.participants:
        if not member.enemy_id and combat_is_present(member) and member.position in boss_positions:
            member.position -= 1


def initialize_combat_field(session: CombatSession) -> None:
    player_number = 0
    for member in session.participants:
        if member.enemy_id:
            member.position = 2
            member.field_symbol = "◎" if member.enemy_id != "minion" else "ⓐ"
        else:
            member.field_symbol = chr(ord("①") + player_number)
            member.position = 0 if session.mode == "레이드" else player_number % 2
            player_number += 1


def combat_hp_bar(member: CombatParticipant) -> str:
    filled = min(5, max(0, (member.hp * 5 + member.max_hp - 1) // member.max_hp)) if member.max_hp else 0
    return "●" * filled + "○" * (5 - filled)


def render_combat_field(session: CombatSession) -> str:
    members = [member for member in session.participants if combat_is_present(member)]
    if not members:
        return "--------\n참가자 없음\n--------"
    hazards = {event.position for event in session.dream_events if event.kind == "pit" and event.position is not None}
    hazards.update(event["position"] for event in session.family_events if event["kind"] == "pit")
    marked = [session.participants[event["target"]] for event in session.family_events if event["kind"] == "mark"]
    marked_ids = {id(member) for member in marked}
    empty_marks = {member.position for member in marked if not combat_is_present(member)}
    coordinates = [member.position for member in members] + list(hazards) + list(empty_marks)
    positions = range(max(coordinates), min(coordinates) - 1, -1)
    current = session.participants[session.turn_index]
    lines = [" ".join(
        member.field_symbol + ("※" if id(member) in marked_ids else "") + (" ◀" if member is current else "")
        for member in members if member.position == position
    ) + (" ×" if position in hazards else "") + (" ※" if position in empty_marks else "") for position in positions]
    return "--------\n" + "\n".join(lines) + ("\n※ 검은 낙인" if marked else "") + "\n--------"


def combat_targets(session: CombatSession, weapon: CombatWeapon | None = None) -> list[int]:
    current = session.participants[session.turn_index]
    betrayal = current.dream_betrayal and not (weapon is not None and weapon.area)
    broaden = (betrayal or current.madness == "폭력성" or combat_is_controlled(session, session.turn_index)
               or (weapon is not None and weapon.area))
    close_only = weapon is not None and (is_melee_weapon(weapon) or (is_spell_weapon(weapon) and weapon.damage.strip() == "지배"))
    return [index for index, member in enumerate(session.participants)
            if index != session.turn_index and combat_is_active(member) and kitchen.enemy_kind(member) != "pot"
            and (broaden or combat_opponents(session, session.turn_index, index))
            and (not betrayal or (not member.enemy_id and not current.enemy_id))
            and (not close_only or combat_distance(session, session.turn_index, index) == "근거리")]


def render_combat_session(session: CombatSession, prompt: str | None = None) -> str:
    def plain_text(value: str) -> str:
        return value.replace("`", "").replace("**", "")

    if session.phase == "combat":
        order = session.turn_order or list(range(len(session.participants)))
        roster_members = [session.participants[i] for i in order]
        roster_members += [member for i, member in enumerate(session.participants) if i not in order]
        roster = "\n".join(
            (f"{member.field_symbol} {member.character_name}(누적 피해 {member.damage_received} · HP 없음)" if member.enemy_id == "dummy" else
            f"{member.field_symbol} {member.character_name} · {'불 줄이기 필요' if session.kitchen_state.pot_warning else '약불로 조리 중'}" if kitchen.enemy_kind(member) == "pot" else
            f"{'▶ ' if member is session.participants[session.turn_index] else ''}{member.field_symbol} {member.character_name} · 민첩 {member.dexterity}\n"
            f"{combat_hp_bar(member)} HP {member.hp}/{member.max_hp}"
            f"{' · 장갑 ' + str(member.armor) if member.armor else ''}"
            f"{' · 마력장벽 ' + str(member.mana_barrier) if member.enemy_id == 'mage' else ''}"
            f"{' · 침묵' if member.silenced else ''}"
            f"{' · 반격 태세' if member.guarded_round > 0 else ''}"
            f"{' · 마력 ' + str(member.magic_points) if member.magic_points is not None else ''}"
            f"{' · 이성 ' + str(member.sanity) if member.sanity is not None else ''}"
            f"{' · 크기 ' + str(member.size) + ' · 체구 ' + str(member.build) if member.enemy_id == 'chimera' else ''}"
            f"{' · 상태이상 면역' if member.enemy_id in {'chimera', 'dream'} else ''}"
            f"{' · 남은 행동 ' + str(member.actions_left) + '회' if member.enemy_id == 'chimera' and member is session.participants[session.turn_index] and member.actions_left else ''}"
            f"{' · ' + str(member.spawn_round) + '라운드부터 행동' if member.spawn_round > session.round_number else ''}"
            f"{' · 특수기 ' + '·'.join(CHIMERA_SPECIALS[key] for key in member.enemy_specials) if member.enemy_specials else ''}"
            f"{' · 재생 후 회복 중' if member.recovering else ''}"
            f"{' · 독액에 발 묶임(이동 패널티 +1)' if member.snared else ''}"
            f"{' · 마비 ' + str(member.paralysis_stacks) + '중첩(패널티 +' + str(member.paralysis_stacks) + ')' if member.paralyzed else ''}"
            f"{' · 엄폐 중' if member.cover_active and combat_is_active(member) else ''}"
            f"{' · 【' + combat_madness_label(member) + '】' if member.madness or member.permanently_insane else ''}"
            f"{' · 지배 1턴' if member.domination_source is not None else ''}"
            f"{' · 꿈에 잠김' if member.dream_asleep else ''}"
            f"{' · 눈가리개' if member.dream_blind else ''}"
            f"{' · 뒤바뀐 얼굴(동료 공격)' if member.dream_betrayal else ''}"
            f"{' · 종이별' if member.dream_star else ''}"
            f"{' · 잊힌 동작' if member.dream_forbidden else ''}"
            f"{' · 중상' if member.major_wound else ' · 임시처치' if member.temporarily_treated else ''}"
            f"{' · 충격 유지' if maintaining_combat_shock(session, member) else ''}"
            f"{' · 충격' if combat_is_shocked(session, member) and combat_is_active(member) else ''}"
            f"{' · 지속' if combat_is_active(member) and any('지속' in effect.spec.kinds for effect in active_combat_statuses(session, member)) else ''}"
            f"{' · 기권' if member.forfeited else ' · 제물' if member.sacrificed else ' · 기절' if member.unconscious else ' · 손질 완료' if kitchen.is_enemy(member) and member.hp <= 0 else ' · 전투불능' if member.hp <= 0 else ''}")
            for member in roster_members
        )
    else:
        roster = "\n".join(
            f"{index}. {member.character_value.partition('|')[0].strip()} | {member.character_name}"
            for index, member in enumerate(session.participants, start=1)
        )
    roster = roster or "참가자 없음"
    if session.phase == "lobby":
        players = sum(not member.enemy_id for member in session.participants)
        enemy = ""
        if session.mode == "레이드":
            enemy = ("\n상대: 연습용 허수아비 · HP·공격·회피·반격 없음\n모집자가 훈련 종료를 눌러 마칠 수 있어요."
                     if session.enemy_id == "dummy" else
                     "\n상대: 실험키메라 · 장갑 1 · 상태이상 면역\n시작 시 능력치·특수기 2개를 무작위로 정해요.\n10라운드부터 검은 안개 · 정신 판정 실패 시 피해")
        if session.enemy_id == "kitchen":
            enemy = "\n레레의 완벽한 식사 · 해물 크림 파스타 만들기\n조리 진행도 0% · 재료 상태 100점 · 공격·손질·불 조절로 협동해 주세요!"
        if session.enemy_id == "hunter":
            enemy = "\n상대: 루베랄드의 칼날과 광기 · 라운드 제한 없음\n3라운드 종료 후 디안 난입 · 두 명 모두 쓰러뜨리면 승리"
        if session.enemy_id == "dream":
            enemy = "\n상대: 꿈꾸는 고치 · 2인 이상 · 상태이상 면역\n고치 3라운드 후 부화 · 총 12라운드 생존\n요정 장난 30% 추가 등장"
        body = f"모의전투 모집 중 · {session.mode}\n참가자 {players}/8{enemy}\n{roster}\n\n참여 버튼을 눌러 캐릭터를 선택해 주세요."
        return f"```text\n{body}\n```"

    current = session.participants[session.turn_index]
    sections = [
        f"모의전투 · {session.mode} | {session.round_number}라운드"
        + (f" / {session.fog_start_round}라운드부터 검은 안개" if session.fog_start_round else "") + "\n"
        f"행동 순서\n{roster}"
    ]
    if session.fog_start_round and session.round_number >= session.fog_start_round:
        penalty = min(2, session.round_number - session.fog_start_round)
        sections.append(f"【검은 안개】 정신 판정 {'패널티 +' + str(penalty) if penalty else '일반 굴림'} · 실패 시 3d4 피해")
    elif session.fog_start_round and session.round_number in CHIMERA_ROUND_WARNINGS:
        sections.append("【실험구역 경고】\n" + CHIMERA_ROUND_WARNINGS[session.round_number])
    for enemy in session.participants:
        if enemy.hunt_target is not None and combat_is_active(enemy):
            target = session.participants[enemy.hunt_target]
            if combat_is_active(target):
                sections.append(f"【집요한 추격】 {target.character_name} · 남은 집중 공격 {enemy.hunt_attacks_left}회\n엄폐에 성공하면 키메라의 시선을 끊을 수 있어요.")
        if enemy.round_attack_target is not None and combat_is_active(enemy):
            target = session.participants[enemy.round_attack_target]
            if combat_is_active(target):
                sections.append(f"【폭주 도약 준비】 {target.character_name}에게 시선 고정\n{enemy.round_attack_due}라운드 키메라 차례 시작에 덮쳐옵니다!\n거리를 넓히면 공격 패널티 +1 · 회피·반격 가능")
    if session.enemy_id == "dream":
        sections.append(f"꿈속 · {'검은 천사' if session.dream_hatched else '꿈꾸는 고치'} · 12라운드 끝까지 버티기")
        for event in session.dream_events:
            if event.kind == "pit":
                sections.append("【바닥 없는 자리】 다음 보스 차례 전 × 위치에서 이동")
            else:
                title = "두드리는 소리" if event.kind == "pulse" else "눈꺼풀 아래"
                remaining = max(0, event.threshold - (dream_boss(session).damage_received - event.damage_start))
                sections.append(f"【{title}】 다음 보스 차례 전 {remaining} 피해 더 주면 {'취소' if event.kind == 'pulse' else '약화'}")
    if session.enemy_id == "kitchen" and session.kitchen_state is not None:
        sections.append(kitchen.status(session))
    if session.enemy_id == "hunter":
        mage = next((p for p in session.participants if p.enemy_id == "mage"), None)
        sections.append("디안 등장 전 · 딜리아의 체력을 남겨두면 후반에 도움을 받아요." if mage is None else
                        "딜리아가 디안과 교전 중 · 공투 중에도 딜리아를 공격할 수 있어요." if combat_is_present(mage) else "디안 탈락 · 딜리아와 마지막 결전")
        for event in session.family_events:
            sections.append(f"【{event['name']} 예고】 다음 디안 차례에 발동 · " +
                            (f"{session.participants[event['target']].field_symbol}※ {session.participants[event['target']].character_name}에게서 떨어지세요." if event['kind'] == 'mark' else f"위치 {event['position']}에서 이동하세요."))
    if current.dream_betrayal:
        sections.append("【뒤바뀐 얼굴】 근거리의 가장 가까운 동료에게 자동 맨손 공격 · 동료가 없으면 해제")
    if session.initiative_logs:
        sections.append("선공 동률 판정\n" + "\n".join(plain_text(entry) for entry in session.initiative_logs[-2:]))
    sections.append("")
    log_section_index = len(sections) - 1
    sections.append(render_combat_field(session))
    if prompt:
        sections.append(prompt)
    briefing = session.briefing or f"{current.character_name}의 턴이에요!"
    if combat_is_controlled(session, session.turn_index):
        source = session.participants[current.domination_source]
        briefing += f" {source.character_name}이 지시하는 차례예요."
    footer = f"현재 상황\n{briefing}"
    visible_logs = session.recent_logs[:]
    while True:
        entries = []
        previous_turn = None
        for entry in visible_logs:
            turn = getattr(entry, "turn_serial", None)
            if entries and turn != previous_turn:
                entries.append("")
            entries.append("- " + plain_text(entry).replace("\n", "\n  "))
            previous_turn = turn
        logs = "\n".join(entries) if entries else "- 기록 없음"
        sections[log_section_index] = f"최근 기록\n{logs}"
        body = "\n\n".join([*sections, footer])
        if len(body) <= 1850 or not visible_logs:
            break
        visible_logs.pop(0)
    if len(body) > 1850:
        body = body[:1850 - len(footer) - 5] + "\n\n" + footer
    return f"```text\n{body}\n```"


def record_combat_elimination(session: CombatSession, member: CombatParticipant) -> None:
    if not combat_is_active(member):
        source = next(index for index, item in enumerate(session.participants) if item is member)
        released = False
        for target in session.participants:
            remaining = [effect for effect in target.status_effects
                         if not (effect.source_index == source and "충격" in effect.spec.kinds)]
            released = released or len(remaining) != len(target.status_effects)
            target.status_effects = remaining
            if target.domination_source == source:
                target.domination_source = target.domination_user = None
                target.domination_turns = 0
        if released:
            append_combat_log(session, f"【충격 해제】 {member.character_name}의 구속이 풀렸어요.")
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    if combat_is_present(member):
        return
    index = next(index for index, item in enumerate(session.participants) if item is member)
    if index not in session.elimination_order:
        session.elimination_order.append(index)


def render_combat_ranking(session: CombatSession) -> str:
    if session.mode == "레이드":
        lines = [f"{member.character_name} · 입힌 피해 {member.damage_dealt} · HP {member.hp}{' · 기권' if member.forfeited else ' · 제물' if member.sacrificed else ' · 영구 광기 · 탈락' if member.permanently_insane else ' · 기절' if member.unconscious else ''}"
                 for member in session.participants if not member.enemy_id]
        return "참가자 결과\n" + "\n".join(lines)
    active = sorted((member for member in session.participants if combat_is_active(member)), key=lambda member: member.hp, reverse=True)
    unconscious = [member for member in session.participants if combat_is_present(member) and member.unconscious]
    unconscious.sort(key=lambda member: -member.hp)
    eliminated = [session.participants[index] for index in reversed(session.elimination_order)
                  if not combat_is_present(session.participants[index])]
    eliminated += [member for member in session.participants if not combat_is_present(member)
                   and not any(member is item for item in eliminated)]
    all_draw = len(session.participants) > 1 and not active and len({member.hp for member in session.participants}) == 1
    lines = []
    for member in active:
        rank = next(index + 1 for index, item in enumerate(active) if item.hp == member.hp)
        tied = sum(item.hp == member.hp for item in active) > 1
        lines.append(f"{'공동 ' if tied else ''}{rank}위 {member.character_name} · HP {member.hp}")
    for position, member in enumerate(unconscious, start=len(active) + 1):
        lines.append(f"{position}위 {member.character_name} · HP {member.hp} · 기절")
    for position, member in enumerate(eliminated, start=len(active) + len(unconscious) + 1):
        rank = "공동 1위" if all_draw else f"{position}위"
        state = "기권" if member.forfeited else "제물" if member.sacrificed else "영구 광기 · 탈락" if member.permanently_insane else "HP 0 · 탈락"
        lines.append(f"{rank} {member.character_name} · {state}")
    return "최종 순위\n" + "\n".join(lines)


def render_combat_winner(session: CombatSession) -> str:
    if session.enemy_id == "kitchen":
        return kitchen.ending(session)
    if session.enemy_id == "dream":
        return render_dream_ending(session)
    if session.annihilated:
        return render_combat_annihilation(session)
    survivors = [member for member in session.participants if combat_is_active(member)]
    if (len(session.participants) > 1 and len({member.hp for member in session.participants}) == 1
            and (not survivors or len(survivors) == len(session.participants))):
        names = ", ".join(member.character_name for member in session.participants)
        outcome = f"{names} 무승부 · HP {session.participants[0].hp}"
    else:
        if not survivors:
            outcome = "승자 없음 · 모든 캐릭터 전투 탈락"
        else:
            highest_hp = max(member.hp for member in survivors)
            winners = [member for member in survivors if member.hp == highest_hp]
            names = ", ".join(member.character_name for member in winners)
            result = "공동 승리" if len(winners) > 1 else "승리"
            outcome = f"{names} {result} · HP {highest_hp}/{winners[0].max_hp}"
    if session.mode == "레이드":
        total = sum(member.damage_received for member in session.participants if member.enemy_id)
        if session.enemy_id == "dummy":
            outcome = f"허수아비 훈련 종료 · 총 {total} 데미지!"
        else:
            players = any(not member.enemy_id for member in survivors)
            enemies = (not session.family_spawned or any(member.enemy_id in {"hunter", "mage"} for member in survivors)) if session.enemy_id == "hunter" else any(member.enemy_id == "chimera" for member in survivors)
            outcome = ("레이드 성공! 참가자 팀의 승리!" if players and not enemies else
                       "무승부 · 양쪽 모두 전투 탈락" if not players and not enemies else
                       "레이드 중단" if players and enemies else "레이드 실패 · 참가자 모두 전투 탈락")
            outcome += f" · 총 {total} 데미지"
    ranking = render_combat_ranking(session)
    summary_budget = max(0, 1850 - len(outcome) - len(ranking))
    if session.last_attack:
        events = session.last_attack_events[-4:]
        while True:
            details = "\n".join(events) or "피해 적용 전에 전투를 종료했어요."
            summary = f"마지막 공격\n{session.last_attack}\n{details}"
            if len(summary) <= summary_budget or len(events) <= 1:
                break
            events.pop(0)
        if len(summary) > summary_budget:
            summary = summary[:max(0, summary_budget - 3)] + "..."
    else:
        summary = "공격 없이 전투를 종료했어요."
    return f"```text\n전투 종료\n\n{summary}\n\n{outcome}\n\n{ranking}\n```"


def render_combat_annihilation(session: CombatSession) -> str:
    results = []
    for member in session.participants:
        state = "사망" if member.doom_dead else "패배" if member.doom_defeated else f"생존 · HP {member.hp}" if combat_is_present(member) else "이전 탈락"
        results.append(f"{member.character_name} · {state}")
    logs = session.annihilation_logs[:]
    title = "전투 종료 · 멸망\n망각의 파도가 모든 것을 삼켰습니다. 전장은 멸망했습니다."
    while True:
        details = "\n".join(logs)
        body = title + "\n\n" + details + "\n\n최후의 상태\n" + "\n".join(results)
        if len(body) <= 1850 or not logs:
            return "```text\n" + body[:1850] + "\n```"
        logs.pop(0)


async def resolve_combat_annihilation(session: CombatSession, caster: CombatParticipant) -> None:
    if session.annihilated:
        return
    session.annihilated = True
    session.annihilation_logs = session.last_attack_events[:]
    for member in session.participants:
        if not combat_is_present(member) and member is not caster:
            continue
        if member.size <= 100:
            member.hp = 0
            member.doom_defeated = True
            text = f"【멸망 · 패배】 {member.character_name} · 크기 {member.size}"
        else:
            roll, rolls, modifier = roll_combat_d100(member, session=session)
            result = coc_combat_check_result(roll, member.constitution)
            if combat_success_rank(result):
                damage = (member.max_hp + 1) // 2
                damage, health = apply_combat_damage(member, damage, caster, ignore_armor=True)
                member.doom_dead = member.hp <= 0
                member.doom_defeated = member.doom_dead
                outcome = f"최대 HP 절반 · {damage} 피해 · {health}"
            else:
                member.hp = 0
                member.doom_dead = member.doom_defeated = True
                outcome = "사망"
            text = (f"{member.character_name} · 건강 {combat_roll_text(member, roll, rolls, modifier, session=session)} / {member.constitution}\n"
                    f"【{result}】 {outcome}")
        member.cover_active = False
        record_combat_elimination(session, member)
        session.annihilation_logs.append(text)
    session.phase = "finished"
    session.pending_attack = None
    combat_sessions.pop(session.channel_id, None)
    await session.message.edit(content=render_combat_winner(session), view=None)


async def finish_combat_if_decided(session: CombatSession) -> bool:
    if session.enemy_id == "kitchen":
        return await kitchen.finish_if_decided(session)
    if session.enemy_id == "dream":
        await maybe_hatch_dream(session)
        players = any(not member.enemy_id and combat_is_active(member) for member in session.participants)
        if players and not session.dream_result and not session.annihilated:
            return False
        if not players and not session.dream_result:
            session.dream_result = "failure"
        session.phase = "finished"
        session.pending_attack = None
        combat_sessions.pop(session.channel_id, None)
        if session.message is not None:
            await session.message.edit(content=render_dream_ending(session), view=None)
        return True
    survivors = [member for member in session.participants if combat_is_active(member)]
    if session.enemy_id == "hunter":
        update_family_alliance(session)
        if any(not p.enemy_id for p in survivors) and (not session.family_spawned or any(p.enemy_id in {"hunter", "mage"} and combat_is_present(p) for p in session.participants)):
            return False
    elif session.mode == "레이드":
        boss_type = "chimera" if session.enemy_id == "chimera" else "dummy"
        if any(not member.enemy_id for member in survivors) and any(member.enemy_id == boss_type for member in survivors):
            return False
    elif len(survivors) > 1:
        return False
    combat_sessions.pop(session.channel_id, None)
    session.phase = "finished"
    session.pending_attack = None
    if session.message is not None:
        await session.message.edit(content=render_combat_winner(session), view=None)
    return True


def coc_combat_check_result(roll: int, skill_value: int) -> str:
    if roll == 1:
        return "대성공"
    if (skill_value < 50 and roll >= 95) or (skill_value >= 50 and roll == 100):
        return "대실패"
    if roll <= skill_value // 5:
        return "극단적 성공"
    if roll <= skill_value // 2:
        return "어려운 성공"
    if roll <= skill_value:
        return "보통 성공"
    return "실패"


def resolve_tied_initiative(
    participants: list[CombatParticipant],
    dexterity: int,
    logs: list[str],
    attempt: int = 1,
) -> list[CombatParticipant]:
    if len(participants) <= 1:
        return participants

    ranked: dict[int, list[CombatParticipant]] = {}
    labels = {
        "대실패": 0,
        "실패": 1,
        "보통 성공": 2,
        "어려운 성공": 3,
        "극단적 성공": 4,
        "대성공": 5,
    }
    roll_details: list[str] = []
    for participant in participants:
        roll, rolls, modifier = roll_combat_d100(participant)
        result = coc_combat_check_result(roll, dexterity)
        ranked.setdefault(labels[result], []).append(participant)
        roll_details.append(f"{participant.character_name} `{combat_roll_text(participant, roll, rolls, modifier)}` {result}")

    retry_label = "동률 재굴림" if attempt > 1 else "동률 판정"
    logs.append(f"민첩 {dexterity} {retry_label} {attempt}차: " + " · ".join(roll_details))

    ordered: list[CombatParticipant] = []
    for rank in sorted(ranked, reverse=True):
        same_result = ranked[rank]
        if len(same_result) == 1:
            ordered.extend(same_result)
        else:
            ordered.extend(resolve_tied_initiative(same_result, dexterity, logs, attempt + 1))
    return ordered


def sort_combat_initiative(participants: list[CombatParticipant]) -> tuple[list[CombatParticipant], list[str]]:
    by_dexterity: dict[int, list[CombatParticipant]] = {}
    for participant in participants:
        by_dexterity.setdefault(participant.dexterity, []).append(participant)

    ordered: list[CombatParticipant] = []
    tie_logs: list[str] = []
    for dexterity in sorted(by_dexterity, reverse=True):
        group = by_dexterity[dexterity]
        if len(group) == 1:
            ordered.extend(group)
        else:
            ordered.extend(resolve_tied_initiative(group, dexterity, tie_logs))
    return ordered, tie_logs


def is_projectile_weapon(weapon: CombatWeapon) -> bool:
    reference = f"{weapon.skill_reference} {weapon.name}".casefold()
    return "사격" in reference or "투척" in reference


def is_firearm_weapon(weapon: CombatWeapon) -> bool:
    return "사격" in weapon.skill_reference.casefold()


def is_melee_weapon(weapon: CombatWeapon) -> bool:
    return "근접전" in weapon.skill_reference.casefold()


def advance_combat_turn(session: CombatSession) -> None:
    if not session.participants:
        session.turn_index = 0
        return
    order = session.turn_order or list(range(len(session.participants)))
    position = order.index(session.turn_index)
    for _ in range(len(session.participants) * 2):
        position += 1
        if position >= len(order):
            if session.enemy_id == "dream" and session.round_number >= 12:
                session.dream_result = "success" if any(not p.enemy_id and combat_is_active(p) for p in session.participants) else "failure"
                return
            session.round_number += 1
            if session.enemy_id == "kitchen":
                kitchen.process_round(session)
            if session.enemy_id == "hunter" and session.round_number >= 4 and not session.family_spawned:
                spawn_family_mage(session)
            if session.fog_start_round and session.round_number in CHIMERA_ROUND_WARNINGS:
                append_combat_log(session, "【실험구역 경고】 " + CHIMERA_ROUND_WARNINGS[session.round_number])
                session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            # Appended reinforcements enter initiative next round. Existing
            # participant indexes stay stable for distances and status sources.
            if session.turn_order:
                order = sorted(range(len(session.participants)), key=lambda i: -session.participants[i].dexterity)
                session.turn_order = order
            position = 0
        session.turn_index = order[position]
        if combat_is_present(session.participants[session.turn_index]):
            session.turn_serial += 1
            session.participants[session.turn_index].cover_active = False
            session.participants[session.turn_index].movement_choice = ""
            return


def merge_combat_weapons(member: CombatParticipant, incoming: list[CombatWeapon]) -> None:
    def keyed(weapons: list[CombatWeapon]):
        counts: dict[tuple[str, str], int] = {}
        for weapon in weapons:
            identity = (" ".join(weapon.name.split()).casefold(), normalize_weapon_skill_reference(weapon.skill_reference).casefold())
            occurrence = counts.get(identity, 0)
            counts[identity] = occurrence + 1
            yield (*identity, occurrence), weapon

    states = dict(member.weapon_states)
    for key, weapon in keyed(member.weapons):
        states[key] = (weapon.ammo, weapon.broken, weapon.ammo_capacity, weapon.reload_count)
    for key, weapon in keyed(incoming):
        if key in states:
            ammo, broken, capacity, reload_count = states[key]
            # Unknown ammo has never been spent. Recover it from a successful
            # sheet read, while preserving a real zero from depleted weapons.
            if ammo is not None or weapon.ammo is None:
                weapon.ammo = ammo
                if capacity is not None:
                    weapon.ammo_capacity = capacity
            weapon.broken = broken
            weapon.reload_count = reload_count
        states[key] = (weapon.ammo, weapon.broken, weapon.ammo_capacity, weapon.reload_count)
    member.weapons = incoming
    member.weapon_states = states


async def refresh_combat_turn_weapons(session: CombatSession) -> None:
    member = session.participants[session.turn_index]
    try:
        incoming = await combat_weapons(member, refresh=True)
        merge_combat_weapons(member, incoming)
    except Exception as exc:
        print(f"Combat turn weapon refresh failed ({type(exc).__name__}).")
        session.briefing += " 무기 갱신에 실패해 기존 목록으로 진행해요. 다음 차례에 다시 갱신할게요."


async def process_combat_black_fog(session: CombatSession) -> bool:
    if (not session.fog_start_round or session.round_number < session.fog_start_round
            or session.fog_processed_round == session.round_number):
        return False
    players = [member for member in session.participants if not member.enemy_id and combat_is_present(member)]
    # Read every missing POW value before rolling so retry never rerolls a completed check.
    try:
        for member in players:
            if member.spirit is None:
                member.spirit = await combat_skill_value(member, "정신")
                if member.spirit is None:
                    raise SheetError("정신 값을 찾지 못했어요.")
    except Exception as exc:
        print(f"Combat black fog read failed ({type(exc).__name__}).")
        session.briefing = "정신 값을 읽지 못했어요. 검은 안개 판정을 다시 시도해 주세요."
        await publish_combat_panel(session, CombatFogRetryView(session))
        return True
    penalty = min(2, session.round_number - session.fog_start_round)
    boss = next(member for member in session.participants if member.enemy_id == "chimera")
    if not combat_is_active(boss):
        return await finish_combat_if_decided(session)
    for member in players:
        if member.fog_checked_round == session.round_number:
            continue
        member.fog_checked_round = session.round_number
        roll, rolls, modifier = roll_combat_d100(member, -penalty, session=session, context="spirit")
        result = coc_combat_check_result(roll, member.spirit)
        success = result not in {"실패", "대실패"}
        vision = random.choice(BLACK_FOG_VISIONS)
        log = (f"{member.character_name} · 검은 안개\n{vision}\n"
               f"{combat_roll_text(member, roll, rolls, modifier, session=session)} / {member.spirit} 【{result}】")
        if success:
            log += "\n【안개를 버텨냈어요 · 피해 없음】"
            damage = 0
        else:
            raw_damage, detail = roll_damage_formula("3d4")
            damage, health = apply_combat_damage(member, raw_damage, boss)
            log += f"\n피해 {detail}\n【검은 안개 · {damage} 피해】 {health}"
            session.last_attack = f"검은 안개 → {member.character_name}"
            session.last_attack_events = [f"정신 판정 실패 · {damage} 피해 · {health}"]
        append_combat_log(session, log)
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        session.briefing = "검은 안개가 덮쳐옵니다… 참가자들의 정신 판정을 진행합니다."
        await session.message.edit(content=render_combat_session(session), view=None)
        await asyncio.sleep(0.7)
        if damage:
            await check_combat_major_wound(session, member, damage)
    session.fog_processed_round = session.round_number
    if await finish_combat_if_decided(session):
        return True
    current = session.participants[session.turn_index]
    session.briefing = f"검은 안개 판정이 끝났어요. {current.character_name}의 턴이에요!"
    return False


async def process_chimera_encounter_sanity(session: CombatSession) -> bool:
    if session.enemy_id != "chimera" or session.encounter_sanity_done:
        return False
    for member in session.participants:
        if member.enemy_id or member.encounter_sanity_checked:
            continue
        if member.sanity is None:
            member.sanity = await combat_skill_value(member, "이성")
            if member.sanity is None:
                raise SheetError("키메라 조우 판정에 필요한 이성 값을 읽지 못했어요.")
        if member.starting_sanity is None:
            member.starting_sanity = member.sanity
        previous = member.sanity
        roll, rolls, modifier = roll_combat_d100(member, session=session)
        succeeded = combat_success_rank(coc_combat_check_result(roll, previous)) > 0
        formula = "1d3" if succeeded else "1d8"
        amount, detail = roll_damage_formula(formula)
        loss = lose_combat_sanity(session, member, amount)
        member.encounter_sanity_checked = True
        # This check happens before the first full turn, so that turn counts.
        member.madness_skip_end = -1
        outcome = "성공" if succeeded else "실패"
        text = (f"{member.character_name} · 키메라 조우 이성 판정\n"
                f"{combat_roll_text(member, roll, rolls, modifier, session=session)} / {previous} 【{outcome}】\n"
                f"이성 손실 {detail} · 이성 {previous} → {member.sanity}")
        append_combat_log(session, text)
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        session.last_attack = "실험키메라 조우 · 이성 판정"
        session.last_attack_events.append(f"{member.character_name} · 이성 -{loss}" + (f" · {member.madness}" if member.madness else ""))
        session.briefing = "실험키메라를 마주했어요… 전원의 이성 판정을 진행해요."
        await session.message.edit(content=render_combat_session(session), view=None)
        await asyncio.sleep(0.7)
    session.encounter_sanity_done = True
    if await finish_combat_if_decided(session):
        return True
    session.briefing = f"이성 판정이 끝났어요. {session.participants[session.turn_index].character_name}의 턴이에요!"
    return False


DREAM_ANGEL_PATTERNS = ("wings", "eye", "forget", "wings", "eye", "forget", "sleep", "drain", "faces", "eye", "sleep", "false_awakening")


def dream_players(session: CombatSession, *, active: bool = False) -> list[CombatParticipant]:
    return [p for p in session.participants if not p.enemy_id and (combat_is_active(p) if active else combat_is_present(p))]


def dream_boss(session: CombatSession) -> CombatParticipant:
    return next(p for p in session.participants if p.enemy_id == "dream")


def render_dream_ending(session: CombatSession) -> str:
    ending = ("천사가 다시 고치에 잠깁니다. 정신을 차려보니 손 안에 꽃 한송이만 남아있습니다."
              if session.dream_result == "success" else
              "꿈이 당신들을 삼킵니다. 비명을 삼키며 깨어났습니다.")
    return "```text\n꿈꾸는 고치 · 종료\n" + ending + "\n\n" + render_combat_ranking(session)[:1400] + "\n```"


async def maybe_hatch_dream(session: CombatSession) -> None:
    if session.enemy_id != "dream" or session.dream_hatched or session.annihilated:
        return
    boss = dream_boss(session)
    if boss.hp * 2 > boss.max_hp and session.round_number <= 3:
        return
    session.dream_hatched = boss.dream_angel = True
    boss.character_name = "검은 천사"
    boss.hp = boss.max_hp = 9999 + 1000 * session.dream_difficulty
    boss.strength, boss.size, boss.constitution = 120, 220, 120
    boss.enemy_skills.update(str=120, size=220, con=120, pow=120, dodge=40)
    append_combat_log(session, "고치가 갈라집니다. 검은 천사가 눈을 뜹니다.")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]


async def dream_log(session: CombatSession, text: str) -> None:
    append_combat_log(session, text)
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    session.briefing = "꿈이 흔들립니다."
    await session.message.edit(content=render_combat_session(session), view=None)
    await asyncio.sleep(0.7)


async def dream_mental_wave(session: CombatSession, label: str, formula: str, *, sanity_check: bool = False) -> None:
    for member in dream_players(session):
        value = member.sanity if sanity_check else await combat_skill_value(member, "정신")
        if value is None:
            raise SheetError(f"{member.character_name}의 판정 값을 읽지 못했어요.")
        roll, rolls, modifier = roll_combat_d100(member, 0 if sanity_check else -1, session=session, context="" if sanity_check else "spirit")
        success = combat_success_rank(coc_combat_check_result(roll, value)) > 0
        text = f"{member.character_name} · {label}\n{combat_roll_text(member, roll, rolls, modifier, session=session)} / {value} 【{'성공' if success else '실패'}】"
        if not success:
            amount, detail = roll_damage_formula(formula)
            previous = member.sanity
            loss = lose_combat_sanity(session, member, amount)
            text += f"\n이성 손실 {detail} · 이성 {previous} → {member.sanity}"
            session.last_attack = label
            session.last_attack_events.append(f"{member.character_name} · 이성 -{loss}")
        await dream_log(session, text)


async def dream_due_events(session: CombatSession) -> None:
    boss = dream_boss(session)
    for event in session.dream_events[:]:
        if event.due > session.dream_boss_turns:
            continue
        session.dream_events.remove(event)
        if event.kind == "pit":
            for member in dream_players(session):
                if member.position != event.position:
                    continue
                raw, detail = roll_damage_formula("2d6")
                damage, health = apply_combat_damage(member, raw, boss)
                session.last_attack = "바닥 없는 자리"
                session.last_attack_events = [f"{member.character_name} · {damage} 피해 · {health}"]
                await dream_log(session, f"{detail}\n【바닥 없는 자리 · {damage} 피해】 {member.character_name} · {health}")
                await check_combat_major_wound(session, member, damage)
        elif event.kind in {"pulse", "eye"}:
            countered = boss.damage_received - event.damage_start >= event.threshold
            if event.kind == "pulse" and countered:
                await dream_log(session, "【두드림 중단】 꿈속의 소리가 멎습니다.")
            else:
                formula = "1d3" if countered else "1d8"
                await dream_mental_wave(session, "눈꺼풀 아래" if event.kind == "eye" else "안에서 두드리는 소리", formula)


async def dream_fairy_trick(session: CombatSession) -> None:
    players = dream_players(session, active=True)
    if not players or random.random() >= 0.30:
        return
    kind = random.choice(("swap", "blind", "star"))
    member = random.choice(players)
    if kind == "swap":
        if len(players) > 1:
            first, second = random.sample(players, 2)
            if first.position != second.position:
                first.position, second.position = second.position, first.position
            else:
                first.position += random.choice((-1, 1))
        else:
            member.position += random.choice((-1, 1))
        separate_combat_boss_position(session)
        await dream_log(session, "【자리 바꾸기】 소녀가 자리를 바꿔놓습니다.\n“어라? 아까는 저쪽에 있었는데!”")
    elif kind == "blind":
        member.dream_blind = True
        await dream_log(session, f"【눈 가리기】 {member.character_name} · 다음 공격 패널티 +1\n“누구게?” · 근거리 동료가 도움을 줄 수 있어요.")
    else:
        member.dream_star = random.randint(1, 4)
        await dream_log(session, f"【작은 선물】 {member.character_name}의 손에 종이별이 들립니다.\n“선물이야. 꼭 쥐고 있어!” · 턴 종료 전 버리면 이성 손실을 막아요.")


async def take_dream_turn(session: CombatSession) -> None:
    if session.dream_last_action == session.turn_serial:
        return
    session.dream_last_action = session.turn_serial
    session.dream_boss_turns += 1
    await publish_combat_panel(session, None)
    await dream_due_events(session)
    if await finish_combat_if_decided(session):
        return
    await maybe_hatch_dream(session)
    boss = dream_boss(session)
    players = dream_players(session, active=True)
    if not players:
        await finish_combat_if_decided(session)
        return
    # Bound casters still get an escape attempt; holding someone prevents another attack.
    if combat_is_shocked(session, boss):
        effect = next(e for e in active_combat_statuses(session, boss) if "충격" in e.spec.kinds)
        await attempt_combat_status_escape(session, boss, effect)
        await CombatView(session).complete_attack_turn(f"{with_particle(boss.character_name, '가', '이')} 꿈에 묶여 있습니다.")
        return
    if maintaining_combat_shock(session, boss):
        await CombatView(session).complete_attack_turn("꿈이 멈춰 있습니다.")
        return
    physical_weapon = None
    physical_all = False
    threshold = 8 + 4 * session.dream_difficulty
    if not session.dream_hatched:
        pattern = {1: "fold", 2: "pit", 3: "pulse"}.get(session.round_number, "pulse")
    else:
        pattern = DREAM_ANGEL_PATTERNS[min(11, session.round_number - 1)]
    if pattern == "fold":
        positions = sorted({p.position for p in players})
        destination = positions[0] if len(positions) > 1 else boss.position - 1
        for p in players:
            p.position = destination
        physical_weapon, physical_all = 1, True
        await dream_log(session, "【접히는 꿈】 겹쳐진 꿈의 실이 몸을 조입니다.\n전원 1d4 공격 · 회피 가능")
    elif pattern == "pit":
        position = random.choice(players).position
        session.dream_events.append(DreamEvent("pit", session.dream_boss_turns + 1, position=position))
        await dream_log(session, "【바닥 없는 자리】 × 위치가 무너지기 시작합니다.\n다음 보스 차례 전에 × 위치에서 이동하세요.")
    elif pattern in {"pulse", "eye"}:
        session.dream_events.append(DreamEvent(pattern, session.dream_boss_turns + 1,
                                             damage_start=boss.damage_received, threshold=threshold))
        title = "안에서 두드리는 소리" if pattern == "pulse" else "눈꺼풀 아래"
        await dream_log(session, f"【{title}】 정신 공격이 다가옵니다.\n다음 보스 차례 전 {threshold} 피해를 주면 {'취소' if pattern == 'pulse' else '약화'}돼요.")
    elif pattern == "wings":
        for p in players:
            move_combat_position(session, session.participants.index(p), session.turn_index, 1)
        physical_weapon, physical_all = 2, True
        await dream_log(session, "【잠든 날개의 움직임】 모두 한 칸 밀려납니다.\n전원 1d6 공격 · 회피 가능")
    elif pattern == "forget":
        for p in players:
            p.dream_forbidden = p.last_used_weapon
        physical_weapon = 3
        await dream_log(session, "【잊힌 동작】 마지막 무기·주문을 잊어버립니다.\n다음 차례는 다른 행동 · 그림자가 한 명을 공격해요. 2d4 · 회피 가능")
    elif pattern == "faces":
        target = random.choice(players)
        value = await combat_skill_value(target, "정신")
        if value is None:
            raise SheetError("뒤바뀐 얼굴 판정에 필요한 정신 값을 읽지 못했어요.")
        roll, rolls, modifier = roll_combat_d100(target, session=session, context="spirit")
        succeeded = combat_success_rank(coc_combat_check_result(roll, value)) > 0
        target.dream_betrayal = not succeeded
        physical_weapon = 3
        await dream_log(session, f"【뒤바뀐 얼굴】 {target.character_name} · 정신 {combat_roll_text(target, roll, rolls, modifier, session=session)} / {value} 【{'성공' if succeeded else '실패'}】\n"
                        + ("동료의 얼굴이 제자리로 돌아옵니다." if succeeded else "다음 차례, 가장 가까운 근거리 동료를 자동 맨손 공격 · 없으면 해제")
                        + "\n그림자 2d4 공격 · 회피 가능")
    elif pattern == "sleep":
        target = random.choice(players)
        target.dream_asleep = True
        target.cover_active = False
        record_combat_elimination(session, target)
        await dream_log(session, f"【꿈에 잠기는 몸】 {target.character_name}이 잠에 빠집니다.\n근거리 동료가 도움을 주면 깨어나요.")
    elif pattern == "drain":
        target = random.choice(players)
        amount, _ = roll_damage_formula("2d4")
        index = session.participants.index(target)
        session.pending_attack = PendingCombatAttack(session.turn_index, index, 0, 0, 1, stage="defense")
        session.briefing = f"【비어가는 윤곽】 {target.character_name} · 잃을 자원 {amount} 선택"
        await session.message.edit(content=render_combat_session(session), view=DreamResourceView(session, amount))
        return
    elif pattern == "false_awakening":
        await dream_log(session, "【거짓 각성】 익숙한 풍경이 다시 찢어집니다.")
        await dream_mental_wave(session, "거짓 각성 · 이성", "1d8", sanity_check=True)
    if await finish_combat_if_decided(session):
        return
    await dream_fairy_trick(session)
    if physical_weapon is not None:
        targets = [i for i, p in enumerate(session.participants) if not p.enemy_id and combat_is_active(p)]
        if targets:
            if not physical_all:
                targets = [random.choice(targets)]
            first, *rest = targets
            modifier = -1 if session.participants[first].cover_active else 0
            await begin_raid_attack(session, session.turn_index, first, physical_weapon, modifier=modifier, remaining_targets=rest)
            return
    await CombatView(session).complete_attack_turn("꿈의 흔들림이 잦아듭니다.")


async def end_dream_player_turn(session: CombatSession, member: CombatParticipant) -> None:
    if member.enemy_id or member.dream_last_end == session.turn_serial:
        return
    member.dream_last_end = session.turn_serial
    member.dream_blind = False
    member.dream_betrayal = False
    member.dream_forbidden = None
    if member.dream_star:
        amount = member.dream_star
        member.dream_star = 0
        previous = member.sanity
        loss = lose_combat_sanity(session, member, amount)
        append_combat_log(session, f"【종이별 · 이성 -{loss}】 {member.character_name} · {previous} → {member.sanity}")
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]


async def resolve_dream_betrayal(session: CombatSession) -> bool:
    member = session.participants[session.turn_index]
    if not member.dream_betrayal or not combat_is_active(member):
        return False
    if combat_is_shocked(session, member) or pending_combat_status_check(session, member):
        return False
    targets = [i for i, other in enumerate(session.participants)
               if i != session.turn_index and not other.enemy_id and combat_is_active(other)
               and combat_distance(session, session.turn_index, i) == "근거리"]
    if not targets:
        member.dream_betrayal = False
        append_combat_log(session, f"【뒤바뀐 얼굴 해제】 {member.character_name} · 근거리 동료 없음")
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        session.briefing = f"가까이에 동료가 없어 환영이 풀렸어요. {member.character_name}의 턴이에요!"
        return False
    if maintaining_combat_shock(session, member):
        await CombatView(session).complete_attack_turn("구속 유지 중이라 맨손 공격을 하지 못했어요.")
        return True
    nearest = min(abs(session.participants[i].position - member.position) for i in targets)
    target = random.choice([i for i in targets if abs(session.participants[i].position - member.position) == nearest])
    try:
        index = next((i for i, weapon in enumerate(member.weapons)
                      if "비무장" in weapon.name and is_melee_weapon(weapon)), None)
        if index is None:
            raise SheetError("시트에서 비무장 무기를 찾지 못했어요.")
        weapon = member.weapons[index]
        skill = await combat_skill_value(member, normalize_weapon_skill_reference(weapon.skill_reference))
        if skill is None:
            raise SheetError("맨손 공격 기능치를 읽지 못했어요.")
    except Exception as exc:
        print(f"Dream forced unarmed attack read failed ({type(exc).__name__}).")
        session.briefing = "맨손 공격 값을 읽지 못했어요. 자동 공격을 다시 시도해 주세요."
        await publish_combat_panel(session, CombatView(session))
        return True
    member.dream_betrayal = False
    session.pending_attack = PendingCombatAttack(session.turn_index, target, index, skill, 1, fumble_weapon=weapon)
    lock_compulsive_weapon(member, weapon)
    session.last_attack = f"{member.character_name} → {session.participants[target].character_name} · 뒤바뀐 얼굴 · 맨손 공격"
    session.last_attack_events = []
    append_combat_log(session, session.last_attack)
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    await publish_combat_panel(session, None)
    await CombatView(session).process_pending_attack()
    return True


async def repost_combat_turn(session: CombatSession) -> None:
    # A stationary dummy has no player controls. Its turn still ticks ongoing
    # damage and escape checks before moving on, using the same round clock.
    while True:
        if session.enemy_id == "dream":
            if await finish_combat_if_decided(session):
                return
        if await process_combat_black_fog(session):
            return
        previous_round = session.round_number
        if await prepare_combat_status_turn(session):
            return
        if session.round_number != previous_round:
            continue
        if await trigger_round_raid_attack(session):
            return
        current = session.participants[session.turn_index]
        if await resolve_family_domination(session):
            return
        if await resolve_dream_betrayal(session):
            return
        if not current.enemy_id or combat_is_controlled(session, session.turn_index):
            if current.enemy_id:
                current.actions_left = 1
            break
        if kitchen.is_enemy(current):
            await kitchen.take_turn(session)
            return
        if current.enemy_id in {"hunter", "mage"}:
            await publish_combat_panel(session, None)
            await take_family_turn(session)
            return
        if current.enemy_id == "dream":
            await take_dream_turn(session)
            return
        if current.enemy_id in {"chimera", "minion"}:
            await publish_combat_panel(session, None)
            await take_chimera_turn(session)
            return
        for effect in active_combat_statuses(session, current)[:]:
            if "충격" in effect.spec.kinds:
                await attempt_combat_status_escape(session, current, effect)
        advance_combat_turn(session)
        session.briefing = f"{session.participants[session.turn_index].character_name}의 턴이에요!"
        await refresh_combat_turn_weapons(session)
    await publish_combat_panel(session, CombatView(session))


async def publish_combat_panel(session: CombatSession, view: discord.ui.View | None) -> None:
    previous = session.message
    if previous is None:
        raise RuntimeError("Combat message is missing")
    # Use the bot-authenticated message endpoint even for an old slash-command response.
    old_message = previous.channel.get_partial_message(previous.id)
    content = render_combat_session(session)
    try:
        new_message = await previous.channel.send(
            content, view=view, allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.HTTPException, OSError) as exc:
        print(f"Combat panel repost failed ({type(exc).__name__}).")
        session.message = await old_message.edit(content=content, view=view)
        return
    session.message = new_message
    try:
        await old_message.delete()
    except discord.NotFound:
        pass
    except (discord.HTTPException, OSError) as exc:
        print(f"Old combat panel deletion failed ({type(exc).__name__}).")
        try:
            await old_message.edit(content="전투창이 아래의 새 메시지로 이동했어요.", view=None)
        except (discord.HTTPException, OSError):
            pass


async def show_raid_event(session: CombatSession, text: str) -> None:
    append_combat_log(session, text)
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    await session.message.edit(content=render_combat_session(session), view=None)
    await asyncio.sleep(0.7)


async def begin_raid_attack(session: CombatSession, enemy_index: int, target_index: int, weapon_index: int,
                            *, modifier: int = 0, resume_turn_index: int | None = None, remaining_targets: list[int] | None = None) -> None:
    enemy = session.participants[enemy_index]
    if enemy.hunt_target == target_index and enemy.hunt_attacks_left:
        enemy.hunt_attacks_left -= 1
        if not enemy.hunt_attacks_left:
            enemy.hunt_target = None
    weapon = enemy.weapons[weapon_index]
    session.turn_index = enemy_index
    skill = await combat_skill_value(enemy, normalize_weapon_skill_reference(weapon.skill_reference))
    session.pending_attack = PendingCombatAttack(
        enemy_index, target_index, weapon_index, skill or 0, 1,
        fumble_weapon=enemy.weapons[0], modifier=modifier, resume_turn_index=resume_turn_index,
        remaining_targets=list(remaining_targets or []),
    )
    session.last_attack = f"{enemy.character_name} → {session.participants[target_index].character_name} · {weapon.name}"
    session.last_attack_events = []
    session.briefing = session.last_attack + " 판정 중이에요."
    await CombatView(session).process_pending_attack()


async def trigger_round_raid_attack(session: CombatSession) -> bool:
    for enemy_index, enemy in enumerate(session.participants):
        target_index = enemy.round_attack_target
        if (target_index is None or session.round_number < enemy.round_attack_due
                or session.turn_index != enemy_index):
            continue
        enemy.round_attack_target = None
        if not combat_is_active(enemy) or not combat_is_active(session.participants[target_index]):
            continue
        if combat_is_controlled(session, enemy_index):
            await show_raid_event(session, "【지배】 키메라의 예고 공격이 취소됐어요.")
            continue
        if combat_is_shocked(session, enemy) or maintaining_combat_shock(session, enemy):
            await show_raid_event(session, "【예고 공격 취소】 키메라가 충격에 묶여 도약하지 못했어요.")
            continue
        gap = abs(enemy.position - session.participants[target_index].position)
        modifier = -1 if gap > enemy.round_attack_distance else 0
        resume = session.turn_index
        await publish_combat_panel(session, None)
        await show_raid_event(session, f"【폭주 도약 발동】\n키메라가 땅을 박차고 {session.participants[target_index].character_name}에게 덮쳐듭니다!"
                              + (" · 거리 벌리기 패널티 +1" if modifier else ""))
        move_combat_position(session, enemy_index, target_index, -1, adjacent=True)
        weapon_index = next(i for i, weapon in enumerate(enemy.weapons) if weapon.name == "폭주 도약")
        await begin_raid_attack(session, enemy_index, target_index, weapon_index, modifier=modifier, resume_turn_index=resume)
        return True
    return False


async def summon_raid_minion(session: CombatSession, summoner: CombatParticipant) -> None:
    summoner.summons_used += 1
    minion = make_raid_enemy("minion")
    minion.character_name = f"실험체 {summoner.summons_used}"
    spec = RAID_ENEMIES["minion"]
    minion.dexterity, minion.constitution = spec["dex"], spec["con"]
    minion.strength, minion.size = spec["str"], spec["size"]
    minion.hp = minion.max_hp = 6
    minion.spawn_round = session.round_number + 1
    minion.weapons = await combat_weapons(minion)
    # Freeze this round's order before appending the reinforcement.
    if not session.turn_order:
        session.turn_order = list(range(len(session.participants)))
    minion.position = summoner.position
    minion.field_symbol = chr(ord("ⓐ") + summoner.summons_used - 1)
    session.participants.append(minion)
    await show_raid_event(session,
        f"【실험체 소환】 {minion.character_name} · HP 6 · 민첩 35 · 근접전 35 · 피해 1d3\n"
        f"다음 라운드부터 행동 · 소환 {summoner.summons_used}/2")


async def choose_raid_target(session: CombatSession, enemy: CombatParticipant, candidates: list[int]) -> int:
    if enemy.hunt_target is not None:
        target = session.participants[enemy.hunt_target]
        if not combat_is_active(target) or target.cover_active:
            enemy.hunt_target = None
            enemy.hunt_attacks_left = 0
            await show_raid_event(session, "【추격 해제】 키메라가 목표를 놓치고 다른 곳으로 고개를 돌려요.")
        elif enemy.hunt_target in candidates:
            return enemy.hunt_target
    return random.choice(candidates)


async def take_chimera_turn(session: CombatSession, *, continuation: bool = False) -> None:
    enemy_index = session.turn_index
    enemy = session.participants[enemy_index]
    if not continuation:
        enemy.recovering = False
        if enemy.armor_boosted:
            enemy.armor_boosted = False
            enemy.armor = 1
            await show_raid_event(session, "【장갑 탈락】 굳었던 생체 장갑이 벗겨져요. 장갑 1로 돌아왔어요.")
        enemy.actions_left = random.randint(1, enemy.action_dice_sides) if enemy.enemy_id == "chimera" else 1
        if enemy.enemy_id == "chimera":
            await show_raid_event(session, f"행동 주사위 1d{enemy.action_dice_sides} [{enemy.actions_left}]\n【연속 행동】 이번 턴 {enemy.actions_left}회")
    shock = next((effect for effect in active_combat_statuses(session, enemy) if "충격" in effect.spec.kinds), None)
    if shock is not None:
        enemy.actions_left = 0
        await attempt_combat_status_escape(session, enemy, shock)
        await CombatView(session).complete_attack_turn("실험체가 충격에서 벗어나려고 몸부림쳤어요.")
        return
    if maintaining_combat_shock(session, enemy):
        enemy.actions_left = 0
        await CombatView(session).complete_attack_turn("키메라가 충격을 유지하고 있어요.")
        return
    targets = combat_targets(session)
    if not targets:
        await finish_combat_if_decided(session)
        return
    if enemy.enemy_id == "chimera" and enemy.hp * 2 <= enemy.max_hp and not enemy.regeneration_used:
        enemy.regeneration_used = True
        enemy.recovering = True
        healing = random.randint(1, 6)
        previous_hp = enemy.hp
        enemy.hp = min(enemy.max_hp, enemy.hp + healing)
        await show_raid_event(session, f"재생 주사위 1d6 [{healing}]\n【불안정한 재생】 HP {previous_hp} → {enemy.hp}")
    step = enemy.pattern_step if enemy.enemy_id == "chimera" else 0
    if enemy.enemy_id == "chimera":
        enemy.pattern_step = (step + 1) % 9
    if step == 6:
        enemy.armor_boosted = True
        enemy.armor = 3
        await show_raid_event(session, "【장갑 강화】 장갑 3 · 다음 자기 턴까지 · 피해 5 이상으로 파괴")
    if step == 8:
        highest = max(session.participants[i].damage_dealt for i in targets)
        enemy.hunt_target = random.choice([i for i in targets if session.participants[i].damage_dealt == highest])
        enemy.hunt_attacks_left = 2
        await show_raid_event(session, f"【집요한 추격】 키메라가 {with_particle(session.participants[enemy.hunt_target].character_name, '를', '을')} 노려요!\n두 번의 공격을 집중 · 엄폐 성공으로 시선 끊기 가능")
    if step == 5 and enemy.round_attack_target is None:
        enemy.round_attack_target = random.choice(targets)
        enemy.round_attack_due = session.round_number + 1
        enemy.round_attack_distance = abs(enemy.position - session.participants[enemy.round_attack_target].position)
        await show_raid_event(session,
            f"【폭주 도약 준비】\n키메라가 몸을 낮추고 {session.participants[enemy.round_attack_target].character_name}에게 시선을 고정합니다.\n"
            f"다음 키메라 차례가 시작되면 덮쳐옵니다! · 거리를 벌리면 공격 패널티 +1")
    if step == 2:
        target_index = await choose_raid_target(session, enemy, targets)
        move_combat_position(session, enemy_index, target_index, -1, adjacent=True)
        await show_raid_event(session, f"【도약 공격】 키메라가 {session.participants[target_index].character_name}에게 바로 덮쳐요!")
        await begin_raid_attack(session, enemy_index, target_index, 1)
        return
    if step == 4 and enemy.summons_used < 2:
        await summon_raid_minion(session, enemy)
        await CombatView(session).complete_attack_turn("키메라가 실험체를 불러냈어요!")
        return
    special_slot = 0 if step == 3 else 1 if step == 7 else None
    special = enemy.enemy_specials[special_slot] if special_slot is not None and len(enemy.enemy_specials) > special_slot else ""
    weapon_index = 2 + special_slot if special else 0
    if special:
        await show_raid_event(session, f"【특수기 · {CHIMERA_SPECIALS[special]}】\n{CHIMERA_SPECIAL_DETAILS[special]}")
        if special == "burst":
            # Each defender responds separately; the whole queue costs one action.
            target_index, *remaining = targets
            modifier = -1 if session.participants[target_index].cover_active else 0
            await begin_raid_attack(session, enemy_index, target_index, weapon_index,
                                    modifier=modifier, remaining_targets=remaining)
            return
        if special == "poison":
            await begin_raid_attack(session, enemy_index, await choose_raid_target(session, enemy, targets), weapon_index)
            return
    close_targets = [index for index in targets if combat_distance(session, enemy_index, index) == "근거리"]
    candidates = targets if enemy.hunt_target in targets else close_targets or targets
    target_index = await choose_raid_target(session, enemy, candidates)
    close_targets = [target_index] if combat_distance(session, enemy_index, target_index) == "근거리" else []
    if not close_targets:
        roll, rolls, modifier = roll_combat_d100(enemy, session=session)
        move_combat_position(session, enemy_index, target_index, -1, adjacent=special == "charge")
        distance = combat_distance(session, enemy_index, target_index)
        enemy.movement_choice = "move"
        success = coc_combat_check_result(roll, enemy.dexterity) not in {"실패", "대실패"}
        await show_raid_event(session,
            f"민첩 주사위 {combat_roll_text(enemy, roll, rolls, modifier, session=session)} / {enemy.dexterity}\n"
            f"【접근 {'성공' if success else '실패'}】 {enemy.character_name} → {session.participants[target_index].character_name} · {distance}")
        if not success or distance != "근거리":
            await CombatView(session).complete_attack_turn("실험체가 다가왔지만 공격하지 못했어요.")
            return
    await begin_raid_attack(session, enemy_index, target_index, weapon_index)


def roll_damage_formula(formula: str) -> tuple[int, str]:
    """Roll only the weapon's listed damage dice, without adding a damage bonus."""
    formula, _ = parse_combat_statuses(formula)
    cleaned = re.sub(r"\(\s*치\s*\)", "", formula, flags=re.IGNORECASE).strip()
    if not cleaned or cleaned.casefold() in {"미기재", "충격", "-"}:
        return 0, cleaned or "미기재"
    tokens = re.findall(r"[+-]?\s*(?:\d+\s*[dD]\s*\d+|\d+)", cleaned)
    if not tokens or "".join(tokens).replace(" ", "").casefold() != cleaned.replace(" ", "").casefold():
        return 0, cleaned
    total = 0
    details: list[str] = []
    for token in tokens:
        compact = token.replace(" ", "")
        sign = -1 if compact.startswith("-") else 1
        term = compact.lstrip("+-")
        dice_match = re.fullmatch(r"(\d*)[dD](\d+)", term)
        if dice_match:
            count = int(dice_match.group(1) or "1")
            sides = int(dice_match.group(2))
            if count < 1 or sides < 1:
                return 0, cleaned
            rolls = [random.randint(1, sides) for _ in range(count)]
            total += sign * sum(rolls)
            details.append(("-" if sign < 0 else "+") + f"{count}d{sides} [{', '.join(map(str, rolls))}]")
        else:
            value = int(term)
            total += sign * value
            details.append(("-" if sign < 0 else "+") + str(value))
    return total, " ".join(details).lstrip("+")


def maximum_damage_formula(formula: str) -> int:
    formula, _ = parse_combat_statuses(formula)
    cleaned = re.sub(r"\(\s*치\s*\)", "", formula, flags=re.IGNORECASE).replace(" ", "")
    tokens = re.findall(r"[+-]?(?:\d*[dD]\d+|\d+)", cleaned)
    if not tokens or "".join(tokens).casefold() != cleaned.casefold():
        return 0
    total = 0
    for token in tokens:
        sign = -1 if token.startswith("-") else 1
        term = token.lstrip("+-")
        dice = re.fullmatch(r"(\d*)[dD](\d+)", term)
        total += sign * (int(dice.group(1) or "1") * int(dice.group(2)) if dice else int(term))
    return total


def combat_build(strength: int, size: int) -> int:
    combined = strength + size
    if combined <= 64:
        return -2
    if combined <= 84:
        return -1
    if combined <= 124:
        return 0
    if combined <= 164:
        return 1
    if combined <= 204:
        return 2
    return 3 + (combined - 205) // 80


def damage_bonus_formula(strength: int, size: int) -> str:
    combined = strength + size
    if combined <= 64:
        return "-2"
    if combined <= 84:
        return "-1"
    if combined <= 124:
        return "0"
    if combined <= 164:
        return "1d4"
    if combined <= 204:
        return "1d6"
    if combined <= 284:
        return "2d6"
    if combined <= 364:
        return "3d6"
    if combined <= 444:
        return "4d6"
    return "5d6"


def roll_weapon_damage(weapon: CombatWeapon, strength: int, size: int, critical: bool = False) -> tuple[int, str]:
    base_damage, base_detail = roll_damage_formula(weapon.damage)
    bonus_spec = re.sub(r"\s+", "", weapon.damage_bonus).casefold()
    half_bonus = bonus_spec.endswith("/2")
    bonus_formula = bonus_spec[:-2] if half_bonus else bonus_spec
    if bonus_formula == "db":
        bonus_formula = damage_bonus_formula(strength, size)
    elif not re.fullmatch(r"[+-]?(?:\d+d\d+|\d+)(?:[+-](?:\d+d\d+|\d+))*", bonus_formula):
        bonus_formula = ""
    if bonus_formula:
        bonus_damage, bonus_detail = roll_damage_formula(bonus_formula)
    else:
        bonus_damage, bonus_detail = 0, "없음"
    if half_bonus and bonus_formula:
        bonus_damage //= 2
        bonus_detail = f"({bonus_detail})/2"
    maximum = maximum_damage_formula(weapon.damage) if critical and weapon.impaling else 0
    if maximum:
        total = maximum + base_damage + bonus_damage
        detail = f"최대 {maximum} + {base_detail} + DB {bonus_detail}"
    else:
        total = base_damage + bonus_damage
        detail = f"{base_detail} + DB {bonus_detail}"
    if not bonus_formula or bonus_formula == "0":
        detail = detail.rsplit(" + DB ", 1)[0]
    return max(0, total), detail


async def check_combat_major_wound(session: CombatSession, member: CombatParticipant, damage: int) -> None:
    record_combat_elimination(session, member)
    if member.enemy_id:
        return  # A training dummy cannot lose consciousness; destroy its HP.
    if damage <= 0 or member.max_hp <= 0 or damage * 2 < member.max_hp:
        return
    roll, rolls, modifier = roll_combat_d100(member, session=session)
    dice_text = combat_roll_text(member, roll, rolls, modifier, session=session)
    result = coc_combat_check_result(roll, member.constitution)
    succeeded = result not in {"실패", "대실패"}
    member.major_wound = True
    if not succeeded:
        member.madness_knockout = False
        member.unconscious = True
        member.cover_active = False
        record_combat_elimination(session, member)
    status = "중상 · 이후 모든 판정에 패널티 +1" if succeeded else "중상 · 기절(응급처치로 회복 가능)"
    if member.hp <= 0:
        status = "중상 · HP 0으로 전투 탈락"
    append_combat_log(session,
        f"건강 주사위 {dice_text} / {member.constitution}\n"
        f"【건강 {'성공' if succeeded else '실패'} · {status}】 {member.character_name}"
    )
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    session.last_attack_events.append(
        f"{member.character_name}의 중상 건강 판정 {'성공' if succeeded else '실패'}! {status}."
    )
    session.briefing = f"{member.character_name}의 중상 건강 판정 {'성공' if succeeded else '실패'}! {status}."
    await session.message.edit(content=render_combat_session(session), view=None)
    await asyncio.sleep(0.7)


def apply_combat_weapon_statuses(session: CombatSession, attacker: CombatParticipant, target: CombatParticipant, weapon: CombatWeapon) -> None:
    if target.enemy_id in {"chimera", "dream"} or (target.enemy_id == "mage" and target.mana_barrier > 0):
        if weapon.effects:
            labels = "·".join(dict.fromkeys(kind for spec in weapon.effects for kind in spec.kinds))
            text = f"【상태이상 면역】 {target.character_name} · {labels}"
            append_combat_log(session, text)
            session.last_attack_events.append(text)
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        return
    source_index = next(index for index, member in enumerate(session.participants) if member is attacker)
    for spec in weapon.effects:
        if "마비" in spec.kinds:
            target.paralysis_stacks = min(2, target.paralysis_stacks + 1)
            target.paralysis_skip_end_serial = session.turn_serial if session.participants[session.turn_index] is target else -1
            text = f"【마비 {target.paralysis_stacks}중첩】 {target.character_name} · 다음 자기 차례 종료까지 모든 판정 패널티 +{target.paralysis_stacks}"
            append_combat_log(session, text)
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            session.last_attack_events.append(text)
            remaining = tuple(kind for kind in spec.kinds if kind != "마비")
            if not remaining:
                continue
            spec = replace(spec, kinds=remaining)
        retrievable = "충격" in spec.kinds
        if "충격" in spec.kinds and not combat_is_active(attacker):
            continue
        target.status_effects = [effect for effect in active_combat_statuses(session, target)
                                 if not (effect.source_index == source_index and effect.weapon.name == weapon.name
                                         and set(effect.spec.kinds) == set(spec.kinds) and effect.spec.escape_skill == spec.escape_skill and effect.spec.escape_difficulty == spec.escape_difficulty)]
        target.status_effects.append(CombatStatusEffect(source_index, replace(weapon), spec, attacker.strength, attacker.size,
                                                       retrievable=retrievable))
        label = "·".join(spec.kinds)
        append_combat_log(session, f"【{label} 부여】 {target.character_name} · 해제 판정: {status_escape_label(spec)}")
        session.last_attack_events.append(f"{target.character_name}에게 {label} 부여! 해제 판정: {status_escape_label(spec)}.")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]


async def apply_combat_hit_effects(session: CombatSession, attacker: CombatParticipant, target: CombatParticipant, weapon: CombatWeapon) -> None:
    if not combat_is_active(target):
        return
    source_index = next(i for i, item in enumerate(session.participants) if item is attacker)
    target_index = next(i for i, item in enumerate(session.participants) if item is target)
    if (target.enemy_id in {"chimera", "dream"} or (target.enemy_id == "mage" and target.mana_barrier > 0)) and weapon.effects:
        apply_combat_weapon_statuses(session, attacker, target, weapon)
        weapon = replace(weapon, effects=[])

    if any("마비" in effect.kinds for effect in weapon.effects):
        roll, rolls, modifier = roll_combat_d100(target, session=session)
        result = coc_combat_check_result(roll, target.constitution)
        resisted = result not in {"실패", "대실패"}
        outcome = f"【마비 저항 {'성공' if resisted else '실패'}】 {target.character_name}"
        append_combat_log(session,
            f"건강 주사위 {combat_roll_text(target, roll, rolls, modifier, session=session)} / {target.constitution}\n{outcome}"
        )
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        session.last_attack_events.append(outcome)
        await session.message.edit(content=render_combat_session(session), view=None)
        await asyncio.sleep(0.7)
        effects = []
        paralysis_added = False
        for effect in weapon.effects:
            kinds = effect.kinds
            if "마비" in kinds:
                if resisted or paralysis_added:
                    kinds = tuple(kind for kind in kinds if kind != "마비")
                else:
                    paralysis_added = True
            if kinds:
                effects.append(replace(effect, kinds=kinds))
        weapon = replace(weapon, effects=effects)
    apply_combat_weapon_statuses(session, attacker, target, weapon)
    if weapon.snaring:
        target.snared = True
        append_combat_log(session, f"【발 묶임】 {target.character_name} · 다음 자기 차례 종료까지 이동 패널티 +1")
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        session.last_attack_events.append(f"{target.character_name}: 독액에 발이 묶였어요.")
    if weapon.knockback:
        previous = combat_distance(session, source_index, target_index)
        move_combat_position(session, target_index, source_index, 1)
        text = f"【밀려남】 {target.character_name} · {previous} → {combat_distance(session, source_index, target_index)}"
        append_combat_log(session, text)
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        session.last_attack_events.append(text)


def pending_combat_status_check(session: CombatSession, member: CombatParticipant) -> bool:
    return any(effect.escape_pending and "충격" not in effect.spec.kinds for effect in active_combat_statuses(session, member))


async def attempt_combat_status_escape(session: CombatSession, member: CombatParticipant, effect: CombatStatusEffect) -> bool | None:
    skill = "근접전 | 격투" if effect.spec.escape_skill.strip() == "근접전" else normalize_weapon_skill_reference(effect.spec.escape_skill)
    try:
        value = await combat_skill_value(member, skill)
        if value is None:
            raise SheetError(f"{skill} 값을 읽지 못했어요.")
    except Exception as exc:
        effect.escape_pending = True
        session.briefing = f"{member.character_name}의 {skill} 값을 읽지 못했어요. 해제 판정을 다시 시도해 주세요."
        print(f"Combat status escape read failed ({type(exc).__name__}).")
        return None
    roll, rolls, modifier = roll_combat_d100(member, session=session, context="spirit" if skill == "정신" else "")
    result = coc_combat_check_result(roll, value)
    succeeded = combat_success_rank(result) >= effect.spec.escape_difficulty
    effect.escape_pending = False
    if succeeded:
        member.status_effects.remove(effect)
    label = "·".join(effect.spec.kinds)
    requirement = f" · {status_escape_label(effect.spec)} 이상 필요" if effect.spec.escape_difficulty > 1 else ""
    append_combat_log(session,
        f"{member.character_name} · {label} 해제{requirement}\n"
        f"{skill} 주사위 {combat_roll_text(member, roll, rolls, modifier, session=session)} / {value}\n"
        f"【{result} · 해제 {'성공' if succeeded else '실패'}】"
    )
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    return succeeded


async def resolve_automatic_combat_status_checks(session: CombatSession, member: CombatParticipant) -> None:
    for effect in active_combat_statuses(session, member):
        if effect.escape_pending and "충격" not in effect.spec.kinds:
            await attempt_combat_status_escape(session, member, effect)


async def start_combat_madness_turn(session: CombatSession, member: CombatParticipant) -> None:
    if not member.madness or member.madness_last_start == session.turn_serial:
        return
    member.madness_last_start = session.turn_serial
    append_combat_log(session, f"【{member.madness}】 {random.choice(MADNESS_LINES[member.madness])}")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    if member.madness == "발작적 행동" and combat_is_active(member):
        raw, detail = roll_damage_formula("1d3")
        damage, health = apply_combat_damage(member, raw, member)
        append_combat_log(session, f"{detail}\n【발작적 행동 · {damage} 자해】 {health}")
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        session.last_attack = f"{member.character_name} · 발작적 행동"
        session.last_attack_events = [f"{damage} 자해 · {health}"]
        await session.message.edit(content=render_combat_session(session), view=None)
        await check_combat_major_wound(session, member, damage)


async def prepare_combat_status_turn(session: CombatSession) -> bool:
    for _ in range(len(session.participants)):
        member = session.participants[session.turn_index]
        if member.enemy_id == "hunter" and session.family_last_serial != session.turn_serial:
            member.guarded_round = 0
        await start_combat_madness_turn(session, member)
        member.status_effects = active_combat_statuses(session, member)
        for effect in member.status_effects[:]:
            if "지속" not in effect.spec.kinds or effect.last_tick == session.turn_serial:
                continue
            effect.last_tick = session.turn_serial
            effect.escape_pending = "충격" not in effect.spec.kinds
            damage, detail = roll_weapon_damage(effect.weapon, effect.strength, effect.size)
            source = session.participants[effect.source_index]
            damage, health_text = apply_combat_damage(member, damage, source)
            session.last_attack = f"{source.character_name} → {member.character_name} · {effect.weapon.name} 지속 피해"
            session.last_attack_events = [f"지속 피해 {damage} 데미지! ({health_text})"]
            append_combat_log(session,
                f"지속 피해 주사위 {detail} = {damage}\n"
                f"【지속 · {damage} 데미지!】 {member.character_name} · {health_text}"
            )
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await session.message.edit(content=render_combat_session(session), view=None)
            await asyncio.sleep(0.7)
            await check_combat_major_wound(session, member, damage)
            if not combat_is_active(member):
                break
        if combat_is_active(member):
            await resolve_automatic_combat_status_checks(session, member)
            if combat_is_shocked(session, member) and not pending_combat_status_check(session, member):
                session.briefing = f"{with_particle(member.character_name, '는', '은')} 충격 상태예요. 탈출 판정만 가능하고, 성공·실패 모두 턴이 끝나요."
            return False
        if session.enemy_id == "dream":
            await end_dream_player_turn(session, member)
        member.silenced = False
        end_combat_madness_turn(session, member)
        end_combat_domination_turn(session, member)
        if await finish_combat_if_decided(session):
            return True
        previous_round = session.round_number
        advance_combat_turn(session)
        if session.dream_result and await finish_combat_if_decided(session):
            return True
        session.briefing = f"행동할 수 없어 차례를 넘겨요. 이제 {session.participants[session.turn_index].character_name}의 턴이에요!"
        await refresh_combat_turn_weapons(session)
        if session.round_number != previous_round:
            return False
    return session.phase == "finished"


async def apply_combat_fumble_damage(session: CombatSession, member: CombatParticipant, unarmed: CombatWeapon) -> None:
    damage, detail = roll_weapon_damage(unarmed, member.strength, member.size)
    damage, health_text = apply_combat_damage(member, damage, member)
    append_combat_log(session,
        f"비무장 피해 {detail} = {damage}\n"
        f"【대실패 · 본인에게 {damage} 데미지!】 {member.character_name} · {health_text}"
    )
    session.last_attack_events.append(
        f"{member.character_name}의 대실패! 비무장 피해로 본인에게 {damage} 데미지 ({health_text})."
    )
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    session.briefing = f"{member.character_name}의 대실패로 본인에게 {damage} 데미지가 적용됐어요."
    await session.message.edit(content=render_combat_session(session), view=None)
    await asyncio.sleep(0.7)
    await check_combat_major_wound(session, member, damage)


class CombatLobbyView(discord.ui.View):
    def __init__(self, session: CombatSession) -> None:
        super().__init__(timeout=None)
        self.session = session

    @discord.ui.button(label="참여", style=discord.ButtonStyle.primary)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        session = self.session
        if combat_sessions.get(session.channel_id) is not session or session.phase != "lobby":
            await interaction.response.send_message("이 모집은 이미 종료됐어요.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            owned = await registry.get_character_choices_for_user(interaction.user.id)
            if combat_sessions.get(session.channel_id) is not session or session.phase != "lobby":
                await interaction.followup.send("모집이 이미 끝났어요.", ephemeral=True)
                return
            joined = {member.character_value.casefold() for member in session.participants}
            choices = [(value, label) for value, label in owned if value.casefold() not in joined]
            if not choices:
                await interaction.followup.send("참가할 캐릭터가 없어요. `/캐릭터등록`을 먼저 해 주세요. 이미 참가한 캐릭터는 목록에서 제외돼요.", ephemeral=True)
                return
            await interaction.followup.send(
                "참가할 캐릭터를 선택해 주세요.",
                view=CombatJoinView(session, interaction.user.id, choices), ephemeral=True,
            )
        except Exception as exc:
            print(f"Combat join choices failed ({type(exc).__name__}).")
            await interaction.followup.send("캐릭터 목록을 읽지 못했어요. 참여 버튼을 다시 눌러 주세요.", ephemeral=True)

    @discord.ui.button(label="전투 시작", style=discord.ButtonStyle.primary, emoji="⚔️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        session = self.session
        if interaction.user.id != session.owner_id:
            await interaction.response.send_message("모집을 연 사람만 전투를 시작할 수 있어요.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            async with session.lock:
                if combat_sessions.get(session.channel_id) is not session or session.phase != "lobby":
                    await interaction.followup.send("이 모집은 이미 종료됐어요.", ephemeral=True)
                    return
                player_count = sum(not member.enemy_id for member in session.participants)
                minimum = 2 if session.enemy_id == "dream" else 1 if session.mode == "레이드" else 2
                if player_count < minimum:
                    await interaction.followup.send(f"전투를 시작하려면 캐릭터가 {minimum}명 이상 참가해야 해요.", ephemeral=True)
                    return
                difficulty_count = sum(2 if member.is_pulp else 1 for member in session.participants if not member.enemy_id)
                for member in session.participants:
                    randomize_raid_enemy(member, difficulty_count)

                async def load_combat_data(member: CombatParticipant) -> tuple[int | None, int | None, int | None, int | None, list[CombatWeapon]]:
                    dexterity, strength, constitution, size, weapons = await asyncio.gather(
                        combat_skill_value(member, "민첩"),
                        combat_skill_value(member, "근력"),
                        combat_skill_value(member, "건강"),
                        combat_skill_value(member, "크기"),
                        combat_weapons(member, refresh=True),
                    )
                    return dexterity, strength, constitution, size, weapons

                combat_data = await asyncio.gather(*(load_combat_data(member) for member in session.participants))
                magic_users = [member for member, data in zip(session.participants, combat_data)
                               if not member.enemy_id]
                magic_values = await asyncio.gather(*(registry.get_combat_magic_points(member.character_value) for member in magic_users))
                if any(value is None for value in magic_values):
                    await interaction.followup.send("현재 마력을 읽지 못했어요. 시트의 마력 현재값을 확인한 뒤 다시 시작해 주세요.", ephemeral=True)
                    return
                magic_by_member = {id(member): value for member, value in zip(magic_users, magic_values)}
                sane_players = [member for member in session.participants if not member.enemy_id]
                sanity_values = await asyncio.gather(*(registry.get_skill_value(member.character_value, "이성") for member in sane_players))
                if any(value is None for value in sanity_values):
                    await interaction.followup.send("광기 판정에 필요한 현재 이성 값을 읽지 못했어요. 시트를 확인하고 다시 시작해 주세요.", ephemeral=True)
                    return
                starting_sanities = {id(member): value for member, value in zip(sane_players, sanity_values)}
                spirits = {}
                if session.fog_start_round or session.enemy_id == "dream":
                    fog_players = [member for member in session.participants if not member.enemy_id]
                    spirit_values = await asyncio.gather(*(combat_skill_value(member, "정신") for member in fog_players))
                    if any(value is None for value in spirit_values):
                        await interaction.followup.send("정신 판정 값을 읽지 못했어요. 시트를 확인하고 다시 시작해 주세요.", ephemeral=True)
                        return
                    spirits = {id(member): value for member, value in zip(fog_players, spirit_values)}
                missing_health = [
                    member.character_name for member, (_dexterity, strength, constitution, size, _weapons) in zip(session.participants, combat_data)
                    if strength is None or constitution is None or size is None
                ]
                if missing_health:
                    await interaction.followup.send(
                        "근력·건강·크기 값을 읽지 못했어요: " + ", ".join(missing_health), ephemeral=True
                    )
                    return
                for member, (dexterity, strength, constitution, size, weapons) in zip(session.participants, combat_data):
                    member.dexterity = dexterity or 0
                    member.strength = strength or 0
                    member.constitution = constitution or 0
                    member.size = size or 0
                    if not member.enemy_id:
                        member.max_hp = calculate_combat_max_hp(member)
                    elif member.enemy_id == "dummy":
                        member.max_hp = 0
                    member.hp = member.max_hp
                    member.weapons = weapons
                    member.magic_points = magic_by_member.get(id(member)) if not member.enemy_id else member.magic_points
                    member.defended_round = 0
                    member.cover_active = False
                    member.movement_choice = ""
                    member.major_wound = False
                    member.temporarily_treated = False
                    member.spirit = spirits.get(id(member))
                    member.sanity = starting_sanities.get(id(member))
                    member.starting_sanity = member.sanity
                    member.sanity_lost = 0
                    member.permanently_insane = False
                    member.madness = ""
                    member.madness_long = False
                    member.madness_turns = 0
                    member.madness_last_start = member.madness_last_end = member.madness_skip_end = -1
                    member.madness_knockout = False
                    member.compulsive_weapon = None
                    member.fog_checked_round = 0
                    member.encounter_sanity_checked = False
                    member.dream_asleep = member.dream_blind = member.dream_betrayal = False
                    member.dream_forbidden = member.last_used_weapon = None
                    member.dream_star = 0
                    member.dream_last_end = -1
                    member.unconscious = False
                    member.forfeited = False
                    member.sacrificed = False
                    member.doom_defeated = member.doom_dead = False
                    member.domination_source = member.domination_user = None
                    member.domination_turns = 0
                    member.domination_skip_end = member.domination_last_end = -1
                    member.status_effects = []
                    member.paralysis_stacks = 0
                    member.paralysis_skip_end_serial = -1
                    member.damage_dealt = 0
                    member.damage_received = 0
                session.participants, session.initiative_logs = sort_combat_initiative(session.participants)
                session.turn_order = list(range(len(session.participants)))
                initialize_combat_field(session)
                for member in session.participants:
                    if member.enemy_id == "chimera":
                        append_combat_log(session,
                            f"【실험체 생성】 HP {member.max_hp} · 장갑 {member.armor} · 민첩 {member.dexterity} · "
                            f"근접전 {member.enemy_skills['fight']} · 회피 {member.enemy_skills['dodge']}\n"
                            f"근력 {member.strength} · 크기 {member.size} · 체구 {member.build} · DB {damage_bonus_formula(member.strength, member.size)}\n"
                            f"습득한 특수기: {', '.join(CHIMERA_SPECIALS[key] for key in member.enemy_specials)} · 매 턴 행동 1d{member.action_dice_sides}회\n"
                            f"난이도 인원 {difficulty_count}명분 (일반 1 · 펄프 2)"
                        )
                session.phase = "combat"
                session.round_number = 1
                session.turn_index = 0
                session.turn_serial = 1
                if session.enemy_id == "kitchen":
                    kitchen.initialize(session, difficulty_count)
                for member in session.participants:
                    if not member.enemy_id and member.sanity == 0:
                        lose_combat_sanity(session, member, 0)
                if await finish_combat_if_decided(session):
                    return
                if session.enemy_id == "dream":
                    session.dream_difficulty = difficulty_count
                    append_combat_log(session, "고치에서 뻗은 실이 당신들의 꿈을 붙잡고 있습니다.")
                session.briefing = f"전투 시작! {session.participants[session.turn_index].character_name}의 턴이에요!"
                if await process_chimera_encounter_sanity(session):
                    return
                await repost_combat_turn(session)
                session.initiative_logs.clear()
        except Exception as exc:
            print(f"Combat start failed ({type(exc).__name__}).")
            await interaction.followup.send("캐릭터 시트에서 민첩·근력·건강·크기 값을 읽지 못했어요. 잠시 후 다시 시도해 주세요.", ephemeral=True)

    @discord.ui.button(label="모집 취소", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        session = self.session
        if interaction.user.id != session.owner_id:
            await interaction.response.send_message("모집을 연 사람만 취소할 수 있어요.", ephemeral=True)
            return
        async with session.lock:
            if combat_sessions.get(session.channel_id) is not session or session.phase != "lobby":
                await interaction.response.send_message("이 모집은 이미 종료됐어요.", ephemeral=True)
                return
            combat_sessions.pop(session.channel_id, None)
            await interaction.response.edit_message(content="모의전투 모집을 취소했어요.", view=None)
        self.stop()


class CombatJoinSelect(discord.ui.Select):
    def __init__(self, choices: list[tuple[str, str]], page: int) -> None:
        start = page * 25
        # Short local indexes avoid Discord's 100-character option value limit.
        options = [discord.SelectOption(label=trim_choice_name(label), value=str(index))
                   for index, (_value, label) in enumerate(choices[start:start + 25], start=start)]
        super().__init__(placeholder="참가할 캐릭터 선택", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not await view.interaction_check(interaction):
            return
        try:
            index = int(self.values[0])
            if not view.page * 25 <= index < min((view.page + 1) * 25, len(view.choices)):
                raise ValueError("Invalid character choice")
            joined = await join_combat(interaction, view.choices[index][0], expected_session=view.session)
            if joined:
                view.stop()
        except (ValueError, IndexError):
            await send_response(interaction, "캐릭터 선택을 다시 확인해 주세요.", ephemeral=True)
        except Exception as exc:
            print(f"Combat character join failed ({type(exc).__name__}).")
            await send_response(interaction, "참가 처리를 완료하지 못했어요. 모집창을 확인하고 참여 버튼을 다시 눌러 주세요.", ephemeral=True)


class CombatJoinView(discord.ui.View):
    def __init__(self, session: CombatSession, user_id: int, choices: list[tuple[str, str]], page: int = 0) -> None:
        super().__init__(timeout=300)
        self.session = session
        self.user_id = user_id
        self.choices = choices
        self.page = page
        self.add_item(CombatJoinSelect(choices, page))
        for direction, label in ((-1, "이전"), (1, "다음")):
            if 0 <= page + direction < (len(choices) + 24) // 25:
                button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=1)
                async def change_page(interaction: discord.Interaction, step: int = direction) -> None:
                    if not await self.interaction_check(interaction):
                        return
                    next_page = self.page + step
                    await interaction.response.edit_message(
                        content=f"참가할 캐릭터를 선택해 주세요. ({next_page + 1}/{(len(choices) + 24) // 25})",
                        view=CombatJoinView(session, user_id, choices, next_page),
                    )
                    self.stop()
                button.callback = change_page
                self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("본인의 참여 버튼으로 캐릭터를 선택해 주세요.", ephemeral=True)
            return False
        if combat_sessions.get(self.session.channel_id) is not self.session or self.session.phase != "lobby":
            await interaction.response.send_message("이 모집은 이미 종료됐어요.", ephemeral=True)
            return False
        return True


class CombatActionView(discord.ui.View):
    def __init__(self, session: CombatSession, back: bool = False) -> None:
        super().__init__(timeout=None)
        self.session = session
        self.turn_index = session.turn_index
        self.attack = session.pending_attack
        if back:
            button = discord.ui.Button(label="돌아가기", style=discord.ButtonStyle.secondary, row=4)
            button.callback = self.go_back
            self.add_item(button)
        button = discord.ui.Button(label="기권", style=discord.ButtonStyle.danger, row=4)
        button.callback = self.request_forfeit
        self.add_item(button)
        if session.mode == "레이드":
            finish = discord.ui.Button(label="훈련 종료" if session.enemy_id == "dummy" else "레이드 종료", style=discord.ButtonStyle.secondary, row=4)
            finish.callback = self.finish_training
            self.add_item(finish)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.ensure_current(interaction)

    async def ensure_current(self, interaction: discord.Interaction) -> bool:
        session = self.session
        if (combat_sessions.get(session.channel_id) is not session or session.phase != "combat"
                or session.message is None or interaction.message.id != session.message.id
                or session.turn_index != self.turn_index or session.pending_attack is not self.attack
                or (self.attack is not None and self.attack.stage not in {"defense", "confirm"})):
            await send_response(interaction, "이미 처리된 선택이에요. 현재 화면을 확인해 주세요.", ephemeral=True)
            return False
        return True

    async def go_back(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            if interaction.user.id != combat_actor_user(session, session.participants[session.turn_index]):
                await interaction.response.send_message("현재 차례인 사람만 선택을 바꿀 수 있어요.", ephemeral=True)
                return
            session.briefing = f"{session.participants[session.turn_index].character_name}의 턴이에요!"
            await interaction.response.edit_message(content=render_combat_session(session), view=CombatView(session))

    async def request_forfeit(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            index = (session.pending_attack.target_index if session.pending_attack is not None and session.pending_attack.stage != "confirm" else session.turn_index)
            member = session.participants[index]
            if interaction.user.id != member.user_id:
                await interaction.response.send_message(f"지금은 **{member.character_name}** 차례예요. 해당 캐릭터만 기권할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            await forfeit_combat_member(session, index)

    async def finish_training(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            if session.mode != "레이드" or interaction.user.id != session.owner_id:
                await interaction.response.send_message("모집을 연 사람만 레이드를 종료할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            session.phase = "finished"
            session.pending_attack = None
            combat_sessions.pop(session.channel_id, None)
            await session.message.edit(content=render_combat_winner(session), view=None)


class CombatFogRetryView(CombatActionView):
    @discord.ui.button(label="검은 안개 판정 재시도", style=discord.ButtonStyle.primary)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            if not any(member.user_id == interaction.user.id for member in self.session.participants if not member.enemy_id):
                await interaction.response.send_message("전투 참가자만 재시도할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            await repost_combat_turn(self.session)


async def forfeit_combat_member(session: CombatSession, index: int) -> None:
    member = session.participants[index]
    member.forfeited = True
    member.cover_active = False
    member.status_effects = []
    record_combat_elimination(session, member)
    append_combat_log(session, f"【기권】 {member.character_name} · 전투 탈락")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
    session.last_attack_events.append(f"{member.character_name} 기권! 전투에서 빠졌어요.")
    if await finish_combat_if_decided(session):
        return
    await CombatView(session).complete_attack_turn(f"{member.character_name} 기권!")


def combat_first_aid_targets(session: CombatSession) -> list[int]:
    current = session.participants[session.turn_index]
    if current.enemy_id or current.madness in {"폭력성", "도주"}:
        return []
    return [index for index, member in enumerate(session.participants)
            if not member.enemy_id and combat_is_present(member)
            and (member is current or member.madness != "편집증")
            and (member.hp < member.max_hp or member.major_wound or member.paralyzed or member.unconscious
                 or any("지속" in effect.spec.kinds for effect in active_combat_statuses(session, member)))
            and (member is current or (session.mode == "레이드"
                 and combat_distance(session, session.turn_index, index) == "근거리"))]


class CombatFirstAidTargetSelect(discord.ui.Select):
    def __init__(self, session: CombatSession, targets: list[int]) -> None:
        self.session = session
        super().__init__(placeholder="응급처치할 대상", options=[
            discord.SelectOption(label=trim_choice_name(session.participants[i].character_name), value=str(i),
                                 description=trim_choice_name(f"HP {session.participants[i].hp}/{session.participants[i].max_hp}"
                                     + (" · 기절" if session.participants[i].unconscious else "")
                                     + (" · 중상" if session.participants[i].major_wound else "")
                                     + (" · 마비" if session.participants[i].paralyzed else "")
                                     + (" · 지속" if any("지속" in effect.spec.kinds for effect in active_combat_statuses(session, session.participants[i])) else "")))
            for i in targets])

    async def callback(self, interaction: discord.Interaction) -> None:
        await CombatView(self.session).first_aid(interaction, int(self.values[0]))


class CombatFirstAidTargetView(CombatActionView):
    def __init__(self, session: CombatSession, targets: list[int]) -> None:
        super().__init__(session, back=True)
        self.add_item(CombatFirstAidTargetSelect(session, targets))


class CombatWeaponSelect(discord.ui.Select):
    def __init__(self, session: CombatSession) -> None:
        current = session.participants[session.turn_index]
        available = [
            (index, weapon) for index, weapon in enumerate(current.weapons)
            if available_combat_weapon(session, index) and not maintaining_combat_shock(session, current)
        ]
        options = [
            discord.SelectOption(
                label=trim_choice_name(f"주문:{weapon.name}{' (전체:건강)' if weapon.health_resisted_spell else ' (전체)' if weapon.area else ''}" if is_spell_weapon(weapon) else f"{weapon.name} — {weapon.skill_reference}"),
                value=str(index),
                description=trim_choice_name(
                    (combat_spell_summary(weapon) if is_spell_weapon(weapon) else f"피해 {weapon.damage} · DB {weapon.damage_bonus or '없음'}")
                    + (f" · 탄약 {weapon.ammo}" if is_projectile_weapon(weapon) else "")
                    + (" · 고장" if weapon.broken else "")
                ),
            )
            for index, weapon in available[:24 if combat_first_aid_targets(session) else 25]
        ]
        if missing_compulsive_weapon(current):
            options.append(discord.SelectOption(label=trim_choice_name(f"강박:{current.compulsive_weapon[0]}"), value="compulsion_empty", description="사라진 무기로 같은 행동 반복 · 효과 없이 턴 종료"))
        if combat_first_aid_targets(session):
            options.append(discord.SelectOption(label="응급처치", value="first_aid", description="성공 시 1d3 회복 · 중상·마비·지속·기절 치료 · 턴 종료"))
        super().__init__(placeholder="사용할 무기를 선택해 주세요", min_values=1, max_values=1, options=options)
        self.session = session

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, CombatView):
            if self.values[0] == "compulsion_empty":
                await view.repeat_missing_compulsion(interaction)
            elif self.values[0] == "first_aid":
                await view.first_aid(interaction)
            else:
                await view.select_weapon(interaction, int(self.values[0]))


def dream_help_targets(session: CombatSession) -> list[int]:
    current = session.participants[session.turn_index]
    return [i for i, member in enumerate(session.participants)
            if not current.enemy_id and not member.enemy_id and member is not current and combat_is_present(member)
            and (member.dream_asleep or member.dream_blind)
            and combat_distance(session, session.turn_index, i) == "근거리"]


class DreamUtilitySelect(discord.ui.Select):
    def __init__(self, session: CombatSession) -> None:
        options = [discord.SelectOption(label=trim_choice_name(f"{session.participants[i].character_name} · 도움 주기"), value=str(i),
                                       description="잠 깨우기·눈가리개 제거 · 판정 없이 턴 종료") for i in dream_help_targets(session)]
        if session.participants[session.turn_index].dream_star:
            options.append(discord.SelectOption(label="종이별 버리기", value="star", description="이성 손실 방지 · 턴 종료"))
        super().__init__(placeholder="꿈속에서 할 행동", options=options, row=3)
        self.session = session

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.dream_utility(interaction, self.values[0])


class DreamResourceView(CombatActionView):
    def __init__(self, session: CombatSession, amount: int) -> None:
        super().__init__(session)
        self.amount = amount
        target = session.participants[session.pending_attack.target_index]
        for resource in ["마력", "이성", "HP"]:
            if resource == "HP" and ((target.magic_points or 0) >= amount or (target.sanity or 0) > 0):
                continue
            button = discord.ui.Button(label=f"{resource} {amount} 소모", style=discord.ButtonStyle.secondary,
                                       disabled=(resource == "마력" and (target.magic_points or 0) < amount) or (resource == "이성" and not target.sanity))
            async def choose(interaction: discord.Interaction, selected: str = resource) -> None:
                async with session.lock:
                    if not await self.ensure_current(interaction):
                        return
                    attack = session.pending_attack
                    if attack is None or attack.stage != "defense" or interaction.user.id != session.participants[attack.target_index].user_id:
                        await interaction.response.send_message("해당 캐릭터만 선택할 수 있어요.", ephemeral=True)
                        return
                    member = session.participants[attack.target_index]
                    if selected == "마력" and (member.magic_points or 0) < self.amount:
                        await interaction.response.send_message("마력이 부족해요. 다른 자원을 선택해 주세요.", ephemeral=True)
                        return
                    if selected == "이성" and not member.sanity:
                        await interaction.response.send_message("남은 이성이 없어요. 다른 자원을 선택해 주세요.", ephemeral=True)
                        return
                    await interaction.response.defer()
                    attack.stage = "resolving"
                    if selected == "마력":
                        member.magic_points -= self.amount
                        text = f"【비어가는 윤곽】 {member.character_name} · 마력 -{self.amount}"
                    elif selected == "이성":
                        loss = lose_combat_sanity(session, member, self.amount)
                        text = f"【비어가는 윤곽】 {member.character_name} · 이성 -{loss}"
                    else:
                        damage, health = apply_combat_damage(member, self.amount, dream_boss(session))
                        text = f"【비어가는 윤곽】 {member.character_name} · {damage} 피해 · {health}"
                        await check_combat_major_wound(session, member, damage)
                    await dream_log(session, text)
                    if await finish_combat_if_decided(session):
                        return
                    await dream_fairy_trick(session)
                    await CombatView(session).complete_attack_turn("윤곽의 일부를 잃었어요.")
            button.callback = choose
            self.add_item(button)


class CombatView(CombatActionView):
    def __init__(self, session: CombatSession) -> None:
        super().__init__(session)
        current = session.participants[session.turn_index]
        if combat_is_shocked(session, current) or pending_combat_status_check(session, current):
            for item in self.children:
                if getattr(item, "label", "") == "차례 넘기기":
                    item.disabled = True
            if pending_combat_status_check(session, current):
                retry = discord.ui.Button(label="상태 해제 판정 재시도", style=discord.ButtonStyle.primary)
                retry.callback = self.retry_status_checks
                self.add_item(retry)
            else:
                self.add_item(kitchen.escape_control(session) if session.enemy_id == "kitchen" else CombatStatusEscapeSelect(session))
            return
        if current.dream_betrayal:
            for item in self.children:
                if getattr(item, "label", "") == "차례 넘기기":
                    item.disabled = True
            retry = discord.ui.Button(label="맨손 자동 공격 재시도", style=discord.ButtonStyle.primary)
            retry.callback = self.retry_dream_betrayal
            self.add_item(retry)
            return
        available_weapons = [weapon for index, weapon in enumerate(current.weapons) if available_combat_weapon(session, index)]
        if maintaining_combat_shock(session, current) and not combat_first_aid_targets(session):
            self.add_item(discord.ui.Button(label="충격 유지 중 · 다른 공격 불가", style=discord.ButtonStyle.secondary, disabled=True))
        elif available_weapons or combat_first_aid_targets(session) or missing_compulsive_weapon(current):
            self.add_item(CombatWeaponSelect(session))
        elif any(is_melee_weapon(weapon) for weapon in current.weapons):
            self.add_item(discord.ui.Button(label="근접전은 근거리에서 가능해요", style=discord.ButtonStyle.secondary, disabled=True))
        else:
            self.add_item(discord.ui.Button(label="시트에서 무기를 찾지 못했어요", style=discord.ButtonStyle.secondary, disabled=True))
        bindings = releasable_combat_statuses(session, current)
        if bindings:
            release = discord.ui.Button(
                label="무기회수",
                style=discord.ButtonStyle.secondary, row=1,
            )
            release.callback = self.release_bindings
            self.add_item(release)
        close_button = discord.ui.Button(label="거리 좁히기", style=discord.ButtonStyle.primary, row=2, disabled=current.movement_choice == "cover" or not any(combat_distance(session, session.turn_index, i) != "근거리" for i in combat_targets(session)))
        close_button.callback = self.close_distance
        self.add_item(close_button)
        widen_button = discord.ui.Button(label="거리 넓히기", style=discord.ButtonStyle.secondary, row=2, disabled=current.movement_choice == "cover" or not any(combat_distance(session, session.turn_index, i) != "먼 거리" for i in combat_targets(session)))
        widen_button.callback = self.widen_distance
        self.add_item(widen_button)
        cover_button = discord.ui.Button(
            label="엄폐", style=discord.ButtonStyle.secondary, row=2,
            disabled=bool(current.movement_choice) or not any(
                combat_distance(session, session.turn_index, i) != "근거리" for i in combat_targets(session)
            ),
        )
        cover_button.callback = self.take_cover
        self.add_item(cover_button)
        if session.enemy_id == "kitchen" and session.kitchen_state is not None and not current.enemy_id:
            self.add_item(kitchen.KitchenActions(session))
        if session.enemy_id == "dream" and (dream_help_targets(session) or current.dream_star):
            self.add_item(DreamUtilitySelect(session))
        if current.madness == "도주":
            for item in list(self.children):
                if isinstance(item, discord.ui.Select):
                    self.remove_item(item)
                elif getattr(item, "label", "") not in {"거리 넓히기", "기권", "레이드 종료", "훈련 종료"}:
                    item.disabled = True
            widen_button.disabled = False

    async def retry_dream_betrayal(self, interaction: discord.Interaction) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            member = self.session.participants[self.session.turn_index]
            if interaction.user.id != combat_actor_user(self.session, member):
                await interaction.response.send_message("현재 차례인 사람만 재시도할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            await refresh_combat_turn_weapons(self.session)
            await repost_combat_turn(self.session)

    async def dream_utility(self, interaction: discord.Interaction, value: str) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction) or not await self.allow_normal_action(interaction):
                return
            current = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, current) or current.madness == "도주":
                await interaction.response.send_message("현재 차례와 가능한 행동을 확인해 주세요.", ephemeral=True)
                return
            if value == "star":
                if not current.dream_star:
                    await interaction.response.send_message("버릴 종이별이 없어요.", ephemeral=True)
                    return
                current.dream_star = 0
                text = f"【종이별 버리기】 {current.character_name}"
            else:
                index = int(value)
                if index not in dream_help_targets(session):
                    await interaction.response.send_message("도움을 줄 수 있는 근거리 동료가 없어요.", ephemeral=True)
                    return
                target = session.participants[index]
                target.dream_asleep = target.dream_blind = False
                text = f"【도움】 {current.character_name} → {target.character_name} · 잠·눈가리개 해제"
            await interaction.response.defer()
            append_combat_log(session, text)
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await self.complete_attack_turn("도움을 주고 차례를 마쳤어요.")

    async def release_bindings(self, interaction: discord.Interaction) -> None:
        session = self.session
        await interaction.response.defer()
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            current = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, current):
                await interaction.followup.send("현재 차례인 캐릭터만 회수할 수 있어요.", ephemeral=True)
                return
            if combat_is_shocked(session, current) or pending_combat_status_check(session, current) or session.pending_attack is not None:
                await interaction.followup.send("자기 행동 차례에 상태 판정을 마친 뒤 회수해 주세요.", ephemeral=True)
                return
            if current.madness == "도주":
                await interaction.followup.send("【도주】 거리를 넓혀야 해요.", ephemeral=True)
                return
            bindings = releasable_combat_statuses(session, current)
            if not bindings:
                await interaction.followup.send("회수하거나 해제할 구속이 없어요.", ephemeral=True)
                return
            names = list(dict.fromkeys(target.character_name for target, _effect in bindings))
            for target, effect in bindings:
                target.status_effects.remove(effect)
            append_combat_log(session, f"【무기회수 · 구속 해제】 {current.character_name} → {', '.join(names)} · 충격·지속 효과 해제")
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            session.briefing = f"구속을 해제했어요. 아직 {current.character_name}의 턴이에요!"
            await session.message.edit(content=render_combat_session(session), view=CombatView(session))

    async def allow_normal_action(self, interaction: discord.Interaction) -> bool:
        member = self.session.participants[self.session.turn_index]
        if combat_is_shocked(self.session, member):
            await interaction.response.send_message("충격 상태에서는 탈출 판정만 할 수 있어요.", ephemeral=True)
            return False
        if pending_combat_status_check(self.session, member):
            await interaction.response.send_message("상태 해제 판정을 먼저 다시 시도해 주세요.", ephemeral=True)
            return False
        return True

    async def retry_status_checks(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            member = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, member):
                await interaction.response.send_message("현재 차례인 사람만 재시도할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            await resolve_automatic_combat_status_checks(session, member)
            if not pending_combat_status_check(session, member):
                if member.dream_betrayal:
                    await repost_combat_turn(session)
                    return
                session.briefing = f"상태 해제 판정이 끝났어요. {member.character_name}의 턴이에요!"
            await session.message.edit(content=render_combat_session(session), view=CombatView(session))

    async def escape_status(self, interaction: discord.Interaction, index: int) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            member = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, member):
                await interaction.response.send_message("현재 차례인 사람만 탈출할 수 있어요.", ephemeral=True)
                return
            if not 0 <= index < len(member.status_effects):
                await interaction.response.send_message("현재 상태 목록을 다시 확인해 주세요.", ephemeral=True)
                return
            effect = member.status_effects[index]
            if effect not in active_combat_statuses(session, member) or "충격" not in effect.spec.kinds:
                await interaction.response.send_message("이미 해제된 상태예요.", ephemeral=True)
                return
            await interaction.response.defer()
            succeeded = await attempt_combat_status_escape(session, member, effect)
            if succeeded is None:
                await session.message.edit(content=render_combat_session(session), view=CombatView(session))
                return
            await self.complete_attack_turn(f"{member.character_name}의 탈출 {'성공' if succeeded else '실패'}! 탈출 시도로 턴을 마쳤어요.")

    async def take_cover(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            if not await self.allow_normal_action(interaction):
                return
            current = session.participants[session.turn_index]
            if current.madness == "도주":
                await interaction.followup.send("【도주】 거리를 넓혀야 해요.", ephemeral=True)
                return
            if interaction.user.id != combat_actor_user(session, current):
                await interaction.response.send_message(f"지금은 **{current.character_name}** 차례예요.", ephemeral=True)
                return
            if current.movement_choice:
                await interaction.response.send_message("이번 턴에는 이미 이동하거나 엄폐를 시도했어요.", ephemeral=True)
                return
            if not any(combat_distance(session, session.turn_index, i) != "근거리" for i in combat_targets(session)):
                await interaction.response.send_message("엄폐는 상대와 보통거리 이상일 때 사용할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            try:
                stealth = await registry.get_skill_value(current.character_value, "은밀행동")
                if stealth is None:
                    raise SheetError("은밀행동 값을 읽지 못했어요.")
            except Exception as exc:
                print(f"Combat cover read failed ({type(exc).__name__}).")
                await interaction.followup.send("은밀행동 값을 읽지 못했어요. 엄폐 버튼을 눌러 다시 시도해 주세요.", ephemeral=True)
                return
            roll, rolls, modifier = roll_combat_d100(current, session=session)
            result = coc_combat_check_result(roll, stealth)
            current.cover_active = result not in {"실패", "대실패"}
            current.movement_choice = "cover"
            outcome = "성공" if current.cover_active else "실패"
            effect = " · 사격에 패널티 +1" if current.cover_active else ""
            append_combat_log(session,
                f"은밀행동 주사위 {combat_roll_text(current, roll, rolls, modifier, session=session)} / {stealth}\n"
                f"【엄폐 {outcome}】 {current.character_name}{effect}"
            )
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            session.briefing = (
                f"{current.character_name}의 엄폐 {outcome}! 이번 턴은 이동 없이 공격할 수 있어요. "
                f"아직 {current.character_name}의 턴이에요!"
            )
            await session.message.edit(content=render_combat_session(session), view=CombatView(session))

    async def close_distance(self, interaction: discord.Interaction) -> None:
        await self.move_distance(interaction, -1)

    async def widen_distance(self, interaction: discord.Interaction) -> None:
        await self.move_distance(interaction, 1)

    async def move_distance(self, interaction: discord.Interaction, direction: int, target_index: int | None = None) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            if not await self.allow_normal_action(interaction):
                return
            current = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, current):
                await interaction.response.send_message(f"지금은 **{current.character_name}** 차례예요.", ephemeral=True)
                return
            if current.madness == "도주" and direction < 0:
                await interaction.response.send_message("【도주】 거리를 넓혀야 해요.", ephemeral=True)
                return
            if current.movement_choice == "cover" and current.madness != "도주":
                await interaction.response.send_message("엄폐를 시도한 턴에는 거리를 이동할 수 없어요.", ephemeral=True)
                return
            targets = [i for i in combat_targets(session)
                       if combat_distance(session, session.turn_index, i) != ("근거리" if direction < 0 else "먼 거리")]
            if current.madness == "도주":
                opponents = [i for i, member in enumerate(session.participants)
                             if combat_opponents(session, session.turn_index, i) and combat_is_active(member)]
                targets = sorted(opponents, key=lambda i: abs(current.position - session.participants[i].position))[:1]
                target_index = targets[0] if targets else None
            if not targets:
                await interaction.response.send_message("더 이동할 수 있는 상대가 없어요.", ephemeral=True)
                return
            if target_index is None and len(targets) > 1:
                await interaction.response.edit_message(
                    content=render_combat_session(session, "거리를 조절할 상대 선택"),
                    view=CombatMoveTargetView(session, direction, targets),
                )
                return
            target_index = targets[0] if target_index is None else target_index
            if target_index not in targets:
                await interaction.response.send_message("현재 이동할 수 없는 상대예요.", ephemeral=True)
                return
            target = session.participants[target_index]
            await interaction.response.defer()
            roll, rolls, modifier = roll_combat_d100(current, -1 if current.snared else 0, session=session)
            current.movement_choice = "move"
            succeeded = roll <= current.dexterity
            move_combat_position(session, session.turn_index, target_index, direction)
            distance = combat_distance(session, session.turn_index, target_index)
            outcome = "성공" if succeeded else "실패"
            log = (
                f"민첩 주사위 {combat_roll_text(current, roll, rolls, modifier, session=session)} / {current.dexterity}\n"
                f"【이동 {outcome}】 {current.character_name} ↔ {target.character_name} · {distance}"
            )
            append_combat_log(session, log)
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            session.briefing = f"{current.character_name}의 이동 판정 결과를 적용하고 있어요."
            await interaction.message.edit(content=render_combat_session(session), view=None)
            await asyncio.sleep(0.7)
            movement = f"{target.character_name} 쪽으로 거리를 좁혔어요" if direction < 0 else f"{target.character_name}에게서 거리를 넓혔어요"
            if current.madness == "도주":
                await self.complete_attack_turn(f"【도주】 {current.character_name}의 턴 종료")
                return
            if not succeeded:
                await self.complete_attack_turn(f"{with_particle(current.character_name, '가', '이')} {movement}. 민첩 판정에 실패해 턴을 넘겨요.")
            else:
                session.briefing = (
                    f"{with_particle(current.character_name, '가', '이')} {movement}! 아직 {current.character_name}의 턴이에요!"
                )
            if succeeded:
                await interaction.message.edit(content=render_combat_session(session), view=CombatView(session))

    async def first_aid(self, interaction: discord.Interaction, target_index: int | None = None) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction) or not await self.allow_normal_action(interaction):
                return
            current = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, current):
                await interaction.response.send_message(f"지금은 **{current.character_name}** 차례예요.", ephemeral=True)
                return
            targets = combat_first_aid_targets(session)
            if not targets or (target_index is not None and target_index not in targets):
                await interaction.response.send_message("응급처치할 수 있는 대상이 없어요. 본인이나 근거리 동료에게 빠진 HP 또는 치료할 상태가 있어야 해요.", ephemeral=True)
                return
            if target_index is None and len(targets) > 1:
                await interaction.response.edit_message(content=render_combat_session(session, "응급처치할 대상 선택"),
                                                        view=CombatFirstAidTargetView(session, targets))
                return
            target_index = targets[0] if target_index is None else target_index
            await interaction.response.defer()
            try:
                skill = await combat_skill_value(current, "응급처치")
                if skill is None:
                    raise SheetError("응급처치 값을 시트에서 찾지 못했어요.")
            except Exception as exc:
                print(f"Combat first aid read failed ({type(exc).__name__}).")
                await interaction.followup.send("응급처치 값을 읽지 못했어요. 다시 선택해 주세요. 턴은 소모하지 않았어요.", ephemeral=True)
                return
            target = session.participants[target_index]
            roll, rolls, modifier = roll_combat_d100(current, session=session)
            result = coc_combat_check_result(roll, skill)
            success = result not in {"실패", "대실패"}
            log = (f"{current.character_name} → {target.character_name} · 응급처치\n"
                   f"{combat_roll_text(current, roll, rolls, modifier, session=session)} / {skill} 【{result}】")
            if success:
                healing = random.randint(1, 3)
                previous = target.hp
                target.hp = min(target.max_hp, target.hp + healing)
                treated = []
                if target.major_wound:
                    target.major_wound = False
                    target.temporarily_treated = True
                    treated.append("중상 → 임시처치")
                if target.paralyzed:
                    target.paralysis_stacks = 0
                    target.paralysis_skip_end_serial = -1
                    treated.append("마비 해제")
                if any("지속" in effect.spec.kinds for effect in target.status_effects):
                    remaining = []
                    for effect in target.status_effects:
                        kinds = tuple(kind for kind in effect.spec.kinds if kind != "지속")
                        if kinds:
                            remaining.append(replace(effect, spec=replace(effect.spec, kinds=kinds)))
                    target.status_effects = remaining
                    treated.append("지속 해제")
                if target.unconscious:
                    target.madness_knockout = False
                    target.unconscious = False
                    treated.append("기절 회복")
                log += f"\n회복 1d3 [{healing}]\n【{target.hp - previous} 회복】 HP {previous} → {target.hp}"
                if treated:
                    log += "\n【" + " · ".join(treated) + "】"
            else:
                log += "\n【회복 없음】"
            append_combat_log(session, log)
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await interaction.message.edit(content=render_combat_session(session), view=None)
            await asyncio.sleep(0.7)
            await self.complete_attack_turn(f"{current.character_name}의 응급처치 {'성공' if success else '실패'}!")

    async def select_weapon(self, interaction: discord.Interaction, weapon_index: int) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            if not await self.allow_normal_action(interaction):
                return
            current = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, current):
                await interaction.response.send_message(f"지금은 **{current.character_name}** 차례예요.", ephemeral=True)
                return
            if maintaining_combat_shock(session, current):
                await interaction.response.send_message("충격을 유지하는 동안에는 다른 공격을 할 수 없어요.", ephemeral=True)
                return
            if not 0 <= weapon_index < len(current.weapons):
                await interaction.response.send_message("무기 선택이 만료됐어요. 화면을 새로 확인해 주세요.", ephemeral=True)
                return
            weapon = current.weapons[weapon_index]
            if current.madness == "도주" or not compulsion_allows(current, weapon):
                await interaction.response.send_message("【광기】 지금은 그 행동을 할 수 없어요.", ephemeral=True)
                return
            if current.madness == "강박" and current.compulsive_weapon is not None and (
                    weapon.broken or not combat_targets(session, weapon)
                    or (is_projectile_weapon(weapon) and not weapon.ammo)):
                await interaction.response.defer()
                await self.repeat_compulsive_action(weapon)
                return
            if current.dream_forbidden == (weapon.name, weapon.skill_reference):
                if current.madness == "강박":
                    await interaction.response.defer()
                    await self.repeat_compulsive_action(weapon)
                else:
                    await interaction.response.send_message("【잊힌 동작】 다음 차례에는 다른 행동을 골라 주세요.", ephemeral=True)
                return
            if not combat_targets(session, weapon):
                await interaction.response.send_message("지배 주문은 근거리에서만 사용할 수 있어요." if is_spell_weapon(weapon) and weapon.damage.strip() == "지배" else "근접전 무기는 근거리에서만 사용할 수 있어요.", ephemeral=True)
                return
            if weapon.broken:
                await interaction.response.send_message(f"`{weapon.name}`은(는) 고장 나서 사용할 수 없어요.", ephemeral=True)
                return
            if (is_projectile_weapon(weapon) and (weapon.ammo is None or weapon.ammo <= 0)
                    and not (is_firearm_weapon(weapon) and weapon.ammo_capacity)):
                await interaction.response.send_message(f"`{weapon.name}`의 탄약이 없어요.", ephemeral=True)
                return
            if is_projectile_weapon(weapon):
                reload_hint = (
                    f"발수 선택 또는 즉시 마력충전 · 마력 {current.magic_points if current.magic_points is not None else '?'} · 마력 1당 1발"
                    if weapon.magic_ammo else
                    f"발수 선택 또는 재장전 (턴 종료) · 남은 재장전 {max(0, 3 - weapon.reload_count)}회"
                )
                await interaction.response.edit_message(
                    content=render_combat_session(
                        session,
                        f"선택 무기: {weapon.name}\n남은 탄약: {weapon.ammo}발\n"
                        + (reload_hint if is_firearm_weapon(weapon) else "연사 발수 선택"),
                    ),
                    view=CombatShotCountView(session, weapon_index),
                )
                return
            await interaction.response.defer()
            await self.resolve_weapon(interaction, weapon_index, 1)

    async def resolve_weapon(
        self,
        interaction: discord.Interaction,
        weapon_index: int,
        shot_count: int,
        target_index: int | None = None,
    ) -> None:
        session = self.session
        current = session.participants[session.turn_index]
        if combat_is_shocked(session, current) or pending_combat_status_check(session, current):
            await interaction.followup.send("상태 탈출·해제 판정을 먼저 진행해 주세요.", ephemeral=True)
            return
        if maintaining_combat_shock(session, current):
            await interaction.followup.send("충격을 유지하는 동안에는 다른 공격을 할 수 없어요.", ephemeral=True)
            return
        weapon = current.weapons[weapon_index]
        if current.madness == "도주" or not compulsion_allows(current, weapon):
            await interaction.followup.send("【광기】 지금은 그 행동을 할 수 없어요.", ephemeral=True)
            return
        if current.madness == "강박" and current.compulsive_weapon is not None and (weapon.broken or not combat_targets(session, weapon) or (is_projectile_weapon(weapon) and not weapon.ammo)):
            await self.repeat_compulsive_action(weapon)
            return
        if current.dream_forbidden == (weapon.name, weapon.skill_reference):
            if current.madness == "강박":
                await self.repeat_compulsive_action(weapon)
            else:
                await interaction.followup.send("【잊힌 동작】 다른 행동을 골라 주세요.", ephemeral=True)
            return
        if is_spell_weapon(weapon):
            await self.prepare_spell(interaction, weapon_index, target_index)
            return
        skill_name = normalize_weapon_skill_reference(weapon.skill_reference)
        try:
            skill_value = await combat_skill_value(current, skill_name)
            if skill_value is None:
                await session.message.edit(content=render_combat_session(session), view=CombatView(session))
                await interaction.followup.send(
                    f"무기 `{weapon.name}`의 참조 기능치 `{weapon.skill_reference}`를 시트에서 찾지 못했어요. 기능치 표기와 기능치 값을 확인해 주세요.",
                    ephemeral=True,
                )
                return
            if is_projectile_weapon(weapon):
                if weapon.ammo is None or weapon.ammo <= 0:
                    await interaction.followup.send(f"`{weapon.name}`의 탄약이 없어요.", ephemeral=True)
                    return
                shot_count = min(max(1, shot_count), 3, weapon.ammo)
            targets = combat_targets(session, weapon)
            if not targets:
                await interaction.followup.send("이 무기로 공격할 수 있는 상대가 없어요. 근접전은 근거리에서만 가능해요.", ephemeral=True)
                await session.message.edit(content=render_combat_session(session), view=CombatView(session))
                return
            random_target = target_index == -1
            if random_target:
                target_index = random.choice(targets)
            if current.madness == "폭력성":
                target_index = targets[0]
            if target_index is None and len(targets) > 1:
                await session.message.edit(
                    content=render_combat_session(session, "공격 대상 선택"),
                    view=CombatTargetView(session, weapon_index, shot_count, targets),
                )
                return
            if target_index is None:
                target_index = targets[0]
            if target_index not in targets:
                await interaction.followup.send("공격 대상이 전투에서 빠졌어요. 대상을 다시 선택해 주세요.", ephemeral=True)
                return

            target_index = await redirect_madness_attack(session, weapon, target_index)
            attack = PendingCombatAttack(session.turn_index, target_index, weapon_index, skill_value, shot_count)
            if weapon.malfunction is not None:
                attack.luck_value = await registry.get_skill_value(current.character_value, "행운")
                if attack.luck_value is None:
                    raise SheetError("고장 판정에 필요한 행운 값을 읽지 못했어요. 다시 무기를 선택해 주세요.")
            else:
                attack.fumble_weapon = next((item for item in current.weapons if "비무장" in item.name), None)
                if attack.fumble_weapon is None:
                    weapons = await registry.get_combat_weapons(current.character_value)
                    attack.fumble_weapon = next((item for item in weapons if "비무장" in item.name), None)
                if attack.fumble_weapon is None:
                    raise SheetError("대실패 피해에 필요한 비무장 무기를 시트에서 찾지 못했어요.")
            lock_compulsive_weapon(current, weapon)
            session.pending_attack = attack
            session.last_attack = f"{current.character_name} → {session.participants[target_index].character_name} · {weapon.name}"
            if random_target:
                session.last_attack += " · 무작위 대상"
            session.last_attack_events = []
            session.briefing = f"{current.character_name} → {session.participants[target_index].character_name}, 공격 판정 중이에요."
            await self.process_pending_attack(interaction)
        except SheetError as exc:
            session.briefing = "시트 값을 읽지 못했어요. 무기를 다시 선택해 시도해 주세요."
            await session.message.edit(content=render_combat_session(session), view=CombatView(session))
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception as exc:
            print(f"Combat weapon action failed ({type(exc).__name__}).")
            if session.pending_attack is None:
                session.briefing = "시트 연결을 확인한 뒤 무기를 다시 선택해 주세요."
                await session.message.edit(content=render_combat_session(session), view=CombatView(session))
            await interaction.followup.send("굴림을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.", ephemeral=True)

    async def repeat_missing_compulsion(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction) or not await self.allow_normal_action(interaction):
                return
            member = self.session.participants[self.session.turn_index]
            if interaction.user.id != combat_actor_user(session, member) or not missing_compulsive_weapon(member):
                await interaction.response.send_message("현재 차례와 강박 행동을 다시 확인해 주세요.", ephemeral=True)
                return
            await interaction.response.defer()
            await self.repeat_compulsive_action(CombatWeapon(*member.compulsive_weapon, "0"))

    async def repeat_compulsive_action(self, weapon: CombatWeapon) -> None:
        append_combat_log(self.session, f"【강박】 {weapon.name}을 반복했지만 효과가 없어요.")
        self.session.recent_logs = self.session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        await self.complete_attack_turn("강박 행동으로 턴을 마쳤어요.")

    async def prepare_spell(self, interaction: discord.Interaction, weapon_index: int, target_index: int | None) -> None:
        session = self.session
        caster = session.participants[session.turn_index]
        weapon = caster.weapons[weapon_index]
        try:
            if caster.silenced:
                raise SheetError("침묵 상태에서는 주문을 사용할 수 없어요.")
            doom = weapon.damage.strip() == "멸망"
            targets = [session.turn_index] if doom else combat_targets(session, weapon)
            if doom or weapon.area:
                target_index = targets[0] if targets else None
            if not targets:
                raise SheetError("지배 주문은 근거리에서만 사용할 수 있어요." if weapon.damage.strip() == "지배" else "주문을 사용할 상대가 없어요.")
            if caster.madness == "폭력성" and not doom and not weapon.area:
                target_index = targets[0]
            if target_index is None and len(targets) > 1:
                await session.message.edit(content=render_combat_session(session, "주문 대상 선택"),
                                           view=CombatTargetView(session, weapon_index, 1, targets))
                return
            if target_index == -1:
                target_index = random.choice(targets)
            target_index = targets[0] if target_index is None else target_index
            if target_index not in targets:
                raise SheetError("주문 대상을 다시 선택해 주세요.")
            if not doom and not weapon.area:
                target_index = await redirect_madness_attack(session, weapon, target_index)
            defender = session.participants[target_index]
            spirit = (caster.spirit or 0) if doom or weapon.health_resisted_spell else await combat_skill_value(caster, "정신")
            defenses = {}
            if not doom:
                for index in (targets if weapon.area else [target_index]):
                    value = await combat_skill_value(session.participants[index], "건강" if weapon.health_resisted_spell else "정신")
                    if value is None:
                        raise SheetError("주문 방어에 필요한 특성치를 읽지 못했어요.")
                    defenses[index] = value
            defense = defenses.get(target_index, 0)
            if spirit is None or defense is None:
                raise SheetError("주문 방어에 필요한 특성치를 읽지 못했어요.")
            if (not re.fullmatch(r"\d*[dD]\d+(?:[+-]\d+)?|\d+", weapon.damage.replace(" ", ""))
                    and not (weapon.damage == "0" and weapon.effects) and weapon.damage.strip() != "지배" and not doom):
                raise SheetError("주문의 피해식이나 효과를 먼저 적어 주세요.")
            deferred = {}
            costs = roll_spell_costs(weapon.spell_cost_text, deferred)
            if "마력" in costs and caster.magic_points is None:
                caster.magic_points = await registry.get_combat_magic_points(caster.character_value)
                if caster.magic_points is None:
                    raise SheetError("현재 마력 값을 읽지 못했어요.")
            if "이성" in costs and caster.sanity is None:
                caster.sanity = await combat_skill_value(caster, "이성")
                if caster.sanity is None:
                    raise SheetError("현재 이성 값을 읽지 못했어요.")
            if (doom or weapon.health_resisted_spell) and "정신" in costs and caster.spirit is None:
                spirit = await combat_skill_value(caster, "정신")
                if spirit is None:
                    raise SheetError("주문 대가에 필요한 정신 값을 읽지 못했어요.")
            if costs.get("정신", 0) > spirit:
                raise SheetError("주문 대가로 사용할 정신이 부족해요.")
            hp_cost = max(0, costs.get("마력", 0) - (caster.magic_points or 0))
            if hp_cost > caster.hp and not spell_mana_sources(session) and not spell_mana_sources(session, corpses=True):
                raise SheetError(f"마력이 부족하고, 대신 사용할 HP {hp_cost}도 부족해요.")
            attack = PendingCombatAttack(session.turn_index, target_index, weapon_index, spirit, 1,
                                         stage="confirm", spell_costs=costs, spell_deferred_costs=deferred, spell_defense_value=defense,
                                         spell_defenses=defenses, remaining_targets=[i for i in targets if i != target_index] if weapon.area else [])
            session.pending_attack = attack
            if hp_cost or costs.get("마력", 0):
                session.briefing = spell_funding_prompt(session)
                await session.message.edit(content=render_combat_session(session), view=CombatSpellCostView(session))
                return
            await self.cast_spell()
        except SheetError as exc:
            if caster.madness == "강박" and caster.compulsive_weapon is not None and (str(exc).startswith("주문 대가로") or str(exc).startswith("마력이 부족하고")):
                await self.repeat_compulsive_action(weapon)
                return
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception as exc:
            print(f"Combat spell preparation failed ({type(exc).__name__}).")
            await interaction.followup.send("주문 값을 읽지 못했어요. 자원을 확인하고 다시 선택해 주세요.", ephemeral=True)

    async def cast_spell(self) -> None:
        session = self.session
        attack = session.pending_attack
        if attack is None or attack.spell_paid:
            return
        caster = session.participants[attack.attacker_index]
        target = session.participants[attack.target_index]
        weapon = caster.weapons[attack.weapon_index]
        if not combat_is_active(caster) or not combat_is_active(target):
            session.pending_attack = None
            await session.message.edit(content=render_combat_session(session), view=CombatView(session))
            return
        costs = attack.spell_costs
        magic_cost = costs.get("마력", 0)
        if attack.spell_requested_donor is not None:
            return
        for index, amount in attack.spell_donations.items():
            donor = session.participants[index]
            if index not in spell_mana_sources(session) or amount < 1 or amount > (donor.magic_points or 0):
                session.briefing = "제공받을 마력을 다시 확인해 주세요. 아직 자원을 소모하지 않았어요."
                await session.message.edit(content=render_combat_session(session), view=CombatSpellCostView(session))
                return
        corpse = session.participants[attack.spell_sacrifice] if attack.spell_sacrifice is not None else None
        if corpse is not None and attack.spell_sacrifice not in spell_mana_sources(session, corpses=True):
            attack.spell_sacrifice = None
            session.briefing = "제물로 사용할 수 없는 대상이에요. 다시 선택해 주세요."
            await session.message.edit(content=render_combat_session(session), view=CombatSpellCostView(session))
            return
        gifts = sum(attack.spell_donations.values())
        pool = (caster.magic_points or 0) + ((corpse.magic_points or 0) if corpse is not None else 0)
        magic_used = min(pool, max(0, magic_cost - gifts))
        hp_cost = max(0, magic_cost - gifts - magic_used)
        if hp_cost > caster.hp or costs.get("정신", 0) > (caster.spirit or 0):
            session.briefing = "주문 대가가 부족해요. 마력을 요청하거나 제물을 선택해 주세요."
            await session.message.edit(content=render_combat_session(session), view=CombatSpellCostView(session))
            return
        for resource, formula in attack.spell_deferred_costs.items():
            costs[resource] = roll_damage_formula(formula)[0]
        if costs.get("정신", 0) > (caster.spirit or 0):
            session.briefing = "주문 대가로 사용할 정신이 부족해 시전하지 못했어요."
            await session.message.edit(content=render_combat_session(session), view=CombatSpellCostView(session))
            return
        attack.spell_deferred_costs.clear()
        attack.spell_paid = True
        attack.stage = "rolling"
        spent = []
        for index, amount in attack.spell_donations.items():
            donor = session.participants[index]
            donor.magic_points -= amount
            spent.append(f"{donor.character_name} 마력 -{amount}")
        if corpse is not None:
            corpse.sacrificed = True
            corpse.magic_points = 0
            spent.append(f"제물 {corpse.character_name}")
        if "마력" in costs:
            previous = caster.magic_points or 0
            caster.magic_points = pool - magic_used
            spent.append(f"마력 {previous} → {caster.magic_points}")
        if hp_cost:
            previous = caster.hp
            caster.hp -= hp_cost
            spent.append(f"HP {previous} → {caster.hp}")
            record_combat_elimination(session, caster)
        if "이성" in costs:
            previous = caster.sanity
            lose_combat_sanity(session, caster, costs["이성"])
            spent.append(f"이성 {previous} → {caster.sanity} (-{costs['이성']})")
        if "정신" in costs:
            previous = caster.spirit
            caster.spirit -= costs["정신"]
            spent.append(f"정신 {previous} → {caster.spirit}")
        lock_compulsive_weapon(caster, weapon)
        await kitchen.check_control(session, attack)
        if weapon.damage.strip() == "멸망":
            session.last_attack = f"{caster.character_name} · {weapon.name}"
            session.last_attack_events = ["대가: " + (" · ".join(spent) or "없음")]
            append_combat_log(session, session.last_attack + "\n" + session.last_attack_events[0])
            await resolve_combat_annihilation(session, caster)
            return
        if weapon.health_resisted_spell:
            attack.spell_result = "보통 성공"
            attack.hits = [(0, "보통 성공", 1)]
            session.last_attack = f"{caster.character_name} · {weapon.name} (전체:건강)"
            session.last_attack_events = ["대가: " + (" · ".join(spent) or "없음")]
            append_combat_log(session, session.last_attack + "\n" + session.last_attack_events[0])
            await begin_health_spell_target(session)
            return
        attack.skill_value = caster.spirit
        # Self-targeting isn't offered, but keep stored defense consistent with resource changes.
        if target is caster:
            attack.spell_defense_value = caster.spirit
        roll, rolls, modifier = roll_combat_d100(caster, session=session, context="spell_attack")
        result = coc_combat_check_result(roll, attack.skill_value)
        attack.spell_result = result
        if combat_success_rank(result):
            attack.hits = [(roll, result, 1)]
        session.last_attack = f"{caster.character_name} → {'전체' if weapon.area else target.character_name} · {weapon.name}"
        session.last_attack_events = ["대가: " + (" · ".join(spent) or "없음")]
        append_combat_log(session, session.last_attack + "\n대가: " + (" · ".join(spent) or "없음")
                          + f"\n정신 {combat_roll_text(caster, roll, rolls, modifier, session=session)} / {attack.skill_value} 【{result}】")
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        attack.stage = "defense"
        session.briefing = f"{target.character_name}의 정신 대항 차례예요!"
        await session.message.edit(content=render_combat_session(session), view=CombatSpellDefenseView(session))
        if target is caster:
            if attack.hits:
                if weapon.damage.strip() == "지배":
                    apply_combat_domination(session, attack)
                else:
                    await self.apply_incoming_hits()
            await self.complete_attack_turn("감각 왜곡으로 자신을 공격했어요.")
        elif target.enemy_id:
            await CombatSpellDefenseView(session).resolve_spell()

    async def process_pending_attack(self, interaction: discord.Interaction | None = None) -> None:
        session = self.session
        attack = session.pending_attack
        if attack is None:
            return
        current = session.participants[attack.attacker_index]
        target = session.participants[attack.target_index]
        weapon = current.weapons[attack.weapon_index]
        await kitchen.check_control(session, attack)
        for shot_number in range(1, attack.shot_count + 1):
            burst_penalty = shot_number - 1 if is_projectile_weapon(weapon) else 0
            distance = combat_distance(session, attack.attacker_index, attack.target_index)
            distance_modifier = 1 if is_projectile_weapon(weapon) and distance == "근거리" else -1 if is_projectile_weapon(weapon) and distance == "먼 거리" else 0
            outnumbered_bonus = 1 if target.defended_round == session.round_number else 0
            cover_penalty = 1 if target.cover_active and is_firearm_weapon(weapon) and distance != "근거리" else 0
            net_modifier = attack.modifier + distance_modifier + outnumbered_bonus - burst_penalty - cover_penalty
            roll, rolls, net_modifier = roll_combat_d100(current, net_modifier, session=session, context="attack", weapon=weapon)
            result = coc_combat_check_result(roll, attack.skill_value)
            dice_text = combat_roll_text(current, roll, rolls, net_modifier, session=session)
            reasons = []
            if distance_modifier:
                reasons.append("근거리" if distance_modifier > 0 else "먼 거리")
            if burst_penalty:
                reasons.append(f"연사 {shot_number}발째")
            if outnumbered_bonus:
                reasons.append("수적열세")
            if cover_penalty:
                reasons.append("엄폐")
            reason_text = " · " + ", ".join(reasons) if reasons else ""
            if is_projectile_weapon(weapon) and weapon.ammo is not None:
                weapon.ammo -= 1
            ammo_text = f" · 남은 탄약 {weapon.ammo}" if is_projectile_weapon(weapon) else ""
            shot_text = f" · {shot_number}발째" if is_projectile_weapon(weapon) else ""
            random_text = " · 무작위" if "무작위 대상" in session.last_attack else ""
            line = (
                f"{current.character_name} → {target.character_name} · {weapon.name}{shot_text}{random_text}\n"
                f"{dice_text} / {attack.skill_value}{reason_text}{ammo_text} 【{result}】"
            )
            append_combat_log(session, line)
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await session.message.edit(content=render_combat_session(session), view=None)
            await asyncio.sleep(0.7)
            if result not in {"실패", "대실패"}:
                attack.hits.append((roll, result, shot_number))
            else:
                session.last_attack_events.append(f"{weapon.name}{shot_text}: {result}, 상대 피해 없음.")

            if weapon.malfunction is None and result == "대실패":
                assert attack.fumble_weapon is not None
                await apply_combat_fumble_damage(session, current, attack.fumble_weapon)
                if not combat_is_active(current):
                    break

            if weapon.malfunction is not None and roll >= weapon.malfunction:
                weapon.broken = True
                luck_value = attack.luck_value
                luck_roll, luck_rolls, luck_modifier = roll_combat_d100(current, session=session)
                luck_text = combat_roll_text(current, luck_roll, luck_rolls, luck_modifier, session=session)
                luck_succeeded = luck_value is not None and luck_roll <= luck_value
                if luck_succeeded:
                    malfunction_log = (
                        f"행운 주사위 {luck_text} / {luck_value}\n"
                        f"【무기 고장 · 행운 성공】 {weapon.name}만 고장났어요!"
                    )
                    session.last_attack_events.append(f"{weapon.name} 고장! 행운 판정에 성공해 본인 피해는 없었어요.")
                else:
                    luck_display = str(luck_value) if luck_value is not None else "확인 불가"
                    self_damage, damage_detail = roll_damage_formula(weapon.damage)
                    self_damage, health_text = apply_combat_damage(current, self_damage, current)
                    malfunction_log = (
                        f"행운 주사위 {luck_text} / {luck_display} · 피해 {damage_detail} = {self_damage}\n"
                        f"【무기 고장 · 행운 실패 · 본인에게 {self_damage} 데미지!】 {current.character_name} · {health_text}"
                    )
                    session.last_attack_events.append(
                        f"{weapon.name} 고장·행운 실패로 {current.character_name} 본인에게 {self_damage} 데미지 ({health_text})."
                    )
                append_combat_log(session, malfunction_log)
                session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
                await session.message.edit(content=render_combat_session(session), view=None)
                await asyncio.sleep(0.7)
                if not luck_succeeded:
                    await check_combat_major_wound(session, current, self_damage)
                break
        if not combat_is_active(current) and not attack.hits:
            await self.complete_attack_turn("공격자가 전투불능이 됐어요.")
            return
        if not attack.hits and (not is_melee_weapon(weapon) or combat_is_shocked(session, target)):
            await self.complete_attack_turn("공격이 빗나갔어요.")
            return
        needs_response = target is not current and target.enemy_id != "dummy" and not (target.enemy_id == "dream" and not target.dream_angel) and not combat_is_shocked(session, target) and (is_melee_weapon(weapon) or not is_firearm_weapon(weapon) or target.is_pulp)
        if needs_response:
            attack.stage = "defense"
            if target.enemy_id:
                can_counter = (is_melee_weapon(weapon) and combat_is_active(current)
                               and not target.recovering and not maintaining_combat_shock(session, target))
                await CombatDefenseView(session).resolve_roll("반격" if can_counter and random.randrange(4) == 0 else "회피")
                return
            session.briefing = (
                f"{current.character_name}의 공격 판정이 끝났어요. {target.character_name}의 방어 차례예요!"
                if attack.hits else
                f"공격이 빗나갔어요. {with_particle(target.character_name, '는', '은')} 반격하거나 그대로 넘길 수 있어요!"
            )
            can_counter = is_melee_weapon(weapon) and combat_is_active(current) and not maintaining_combat_shock(session, target)
            response_choices = ("반격 또는 회피" if attack.hits else "반격 또는 그대로 넘기기") if can_counter else "회피" if attack.hits else "그대로 넘기기"
            await session.message.edit(
                content=render_combat_session(session, f"{target.character_name}: {response_choices} 선택"),
                view=CombatDefenseView(session),
            )
            return
        await self.apply_incoming_hits()
        await self.complete_attack_turn("피해가 적용됐어요.")

    async def apply_incoming_hits(self, avoided_hit_indexes: set[int] | None = None) -> None:
        session = self.session
        attack = session.pending_attack
        if attack is None:
            return
        attacker = session.participants[attack.attacker_index]
        target = session.participants[attack.target_index]
        weapon = attacker.weapons[attack.weapon_index]
        if is_spell_weapon(weapon):
            weapon = replace(weapon, damage_bonus="", impaling=False)
        if not combat_is_active(target):
            return
        attack.stage = "damage"
        session.briefing = f"{target.character_name}의 피해를 계산하고 있어요."
        avoided_hit_indexes = avoided_hit_indexes or set()
        for hit_index, (_roll, result, shot_number) in enumerate(attack.hits):
            if hit_index < attack.kitchen_next_hit:
                continue
            if hit_index in avoided_hit_indexes:
                shot_text = f" · {shot_number}발째" if is_projectile_weapon(weapon) else ""
                append_combat_log(session, f"【회피 성공!】 {target.character_name}{shot_text} · 피해 없음")
                session.last_attack_events.append(f"{target.character_name}의 회피 성공{shot_text}! 피해 없음.")
                attack.kitchen_next_hit = hit_index + 1
                session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
                continue
            choice = session.kitchen_state.damage_choice if session.kitchen_state is not None else None
            if choice is not None and choice.attack is attack and choice.index == hit_index:
                damage, detail = choice.raw, choice.detail
            else:
                damage, detail = roll_weapon_damage(
                    weapon, attacker.strength, attacker.size,
                    critical=weapon.impaling and result in {"극단적 성공", "대성공"},
                )
            limited = await kitchen.limit_damage(session, attack, hit_index, damage, detail, avoided_hit_indexes)
            if limited is None:
                return
            damage, detail = limited
            barrier_protected = target.enemy_id == "mage" and target.mana_barrier > 0
            damage, health_text = apply_combat_damage(target, damage, attacker, weapon=weapon)
            attack.kitchen_next_hit = hit_index + 1
            append_combat_log(session,
                f"피해 {detail}\n"
                f"【{damage} 피해】 {target.character_name} · {health_text}"
            )
            session.last_attack_events.append(
                f"{weapon.name}{' ' + str(shot_number) + '발째' if is_projectile_weapon(weapon) else ''} 공격으로 {target.character_name}에게 {damage} 데미지! "
                f"({health_text})"
            )
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await session.message.edit(content=render_combat_session(session), view=None)
            await asyncio.sleep(0.7)
            if not barrier_protected:
                await apply_combat_hit_effects(session, attacker, target, weapon)
            elif weapon.effects:
                append_combat_log(session, f"【장벽 면역】 {target.character_name} · 부가 효과 차단")
            await check_combat_major_wound(session, target, damage)
            if not combat_is_active(target):
                break

    async def complete_attack_turn(self, summary: str = "공격이 끝났어요.") -> None:
        session = self.session
        attack = session.pending_attack
        if session.kitchen_state is not None and session.kitchen_state.damage_choice is not None:
            return
        resume = attack.resume_turn_index if attack is not None else None
        session.pending_attack = None
        if resume is not None:
            session.turn_index = resume
        if attack is not None and attack.family_spell and await continue_family_spell(session, attack):
            return
        if attack is not None:
            weapon = session.participants[attack.attacker_index].weapons[attack.weapon_index]
            if is_spell_weapon(weapon) and weapon.area and await continue_combat_area_spell(session, attack):
                return
        if await finish_combat_if_decided(session):
            return
        if attack is not None and attack.remaining_targets and combat_is_active(session.participants[attack.attacker_index]):
            remaining = [index for index in attack.remaining_targets if combat_is_active(session.participants[index])]
            if remaining:
                target_index, *rest = remaining
                modifier = -1 if session.participants[target_index].cover_active else 0
                await begin_raid_attack(session, attack.attacker_index, target_index, attack.weapon_index,
                                        modifier=modifier, remaining_targets=rest)
                return
        if session.enemy_id == "hunter" and not combat_is_active(session.participants[session.turn_index]):
            session.family_ops.clear()
        if session.enemy_id == "hunter" and session.family_ops and session.participants[session.turn_index].enemy_id in {"hunter", "mage"}:
            await take_family_turn(session)
            return
        if resume is not None:
            session.briefing = f"예고 공격이 끝났어요. 이제 {session.participants[resume].character_name}의 일반 행동을 시작해요!"
            await repost_combat_turn(session)
            return
        current = session.participants[session.turn_index]
        current.snared = False
        if current.enemy_id in {"chimera", "minion"} and not combat_is_controlled(session, session.turn_index):
            current.actions_left = max(0, current.actions_left - 1)
            if current.actions_left and combat_is_active(current):
                await take_chimera_turn(session, continuation=True)
                return
        if current.paralyzed and current.paralysis_skip_end_serial != session.turn_serial:
            current.paralysis_stacks = 0
            current.paralysis_skip_end_serial = -1
            append_combat_log(session, f"【마비 해제】 {current.character_name}")
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        if session.enemy_id == "dream":
            await end_dream_player_turn(session, current)
        current.silenced = False
        end_combat_madness_turn(session, current)
        end_combat_domination_turn(session, current)
        advance_combat_turn(session)
        next_turn = session.participants[session.turn_index]
        session.briefing = f"{summary} 이제 {next_turn.character_name}의 턴이에요!"
        await refresh_combat_turn_weapons(session)
        await repost_combat_turn(session)


    @discord.ui.button(label="차례 넘기기", style=discord.ButtonStyle.secondary, row=4)
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            if not await self.allow_normal_action(interaction):
                return
            current = session.participants[session.turn_index]
            if current.madness == "도주":
                await interaction.response.send_message("【도주】 거리 넓히기를 눌러 주세요.", ephemeral=True)
                return
            if interaction.user.id != combat_actor_user(session, current):
                await interaction.response.send_message(f"지금은 **{current.character_name}** 차례예요.", ephemeral=True)
                return
            await interaction.response.defer()
            append_combat_log(session, f"{current.character_name} — 차례 넘김")
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await self.complete_attack_turn(f"{with_particle(current.character_name, '가', '이')} 차례를 넘겼어요.")

class CombatStatusEscapeSelect(discord.ui.Select):
    def __init__(self, session: CombatSession) -> None:
        member = session.participants[session.turn_index]
        effects = active_combat_statuses(session, member)
        options = [discord.SelectOption(
            label=trim_choice_name(f"{effect.weapon.name} · {'·'.join(effect.spec.kinds)} · {status_escape_label(effect.spec)}"),
            value=str(index),
            description=trim_choice_name(f"시전자: {session.participants[effect.source_index].character_name} · 성공·실패 모두 턴 종료"),
        ) for index, effect in enumerate(member.status_effects) if effect in effects and "충격" in effect.spec.kinds]
        super().__init__(placeholder="탈출할 상태 선택", options=options[:25])
        self.session = session

    async def callback(self, interaction: discord.Interaction) -> None:
        await CombatView(self.session).escape_status(interaction, int(self.values[0]))


class CombatMoveTargetView(CombatActionView):
    def __init__(self, session: CombatSession, direction: int, targets: list[int]) -> None:
        super().__init__(session, back=True)
        self.direction = direction
        self.target_select = discord.ui.Select(
            placeholder="거리를 조절할 상대",
            options=[discord.SelectOption(
                label=trim_choice_name(session.participants[index].character_name), value=str(index),
                description=combat_distance(session, session.turn_index, index),
            ) for index in targets],
        )
        self.target_select.callback = self.select_target
        self.add_item(self.target_select)

    async def select_target(self, interaction: discord.Interaction) -> None:
        if not await self.ensure_current(interaction):
            return
        await CombatView(self.session).move_distance(interaction, self.direction, int(self.target_select.values[0]))


class CombatShotCountSelect(discord.ui.Select):
    def __init__(self, session: CombatSession, weapon_index: int) -> None:
        weapon = session.participants[session.turn_index].weapons[weapon_index]
        max_shots = min(3, weapon.ammo or 0)
        options = [discord.SelectOption(label=f"{count}발 연사", value=str(count)) for count in range(1, max_shots + 1)]
        super().__init__(placeholder="연사할 발수를 선택해 주세요", min_values=1, max_values=1, options=options)
        self.session = session
        self.weapon_index = weapon_index

    async def callback(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if self.view is not None and not await self.view.ensure_current(interaction):
                return
            current = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, current):
                await interaction.response.send_message(f"지금은 **{current.character_name}** 차례예요.", ephemeral=True)
                return
            await interaction.response.defer()
            root_view = CombatView(session)
            await root_view.resolve_weapon(interaction, self.weapon_index, int(self.values[0]))


class CombatShotCountView(CombatActionView):
    def __init__(self, session: CombatSession, weapon_index: int) -> None:
        super().__init__(session, back=True)
        self.weapon_index = weapon_index
        current = session.participants[session.turn_index]
        weapon = current.weapons[weapon_index]
        if weapon.ammo is not None and weapon.ammo > 0:
            self.add_item(CombatShotCountSelect(session, weapon_index))
        if is_firearm_weapon(weapon):
            capacity = weapon.ammo_capacity or 0
            label = ("마력충전 · 1마력당 1발 (즉시)" if weapon.magic_ammo else
                     f"재장전 · 남은 {max(0, 3 - weapon.reload_count)}회 (턴 종료)")
            unavailable = (current.magic_points == 0 if weapon.magic_ammo else weapon.reload_count >= 3)
            reload_button = discord.ui.Button(
                label=label, style=discord.ButtonStyle.primary,
                disabled=weapon.broken or capacity <= 0 or (weapon.ammo or 0) >= capacity or unavailable or (current.madness == "강박" and current.compulsive_weapon is not None),
            )
            reload_button.callback = self.reload_weapon
            self.add_item(reload_button)

    async def reload_weapon(self, interaction: discord.Interaction) -> None:
        session = self.session
        await interaction.response.defer()
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            current = session.participants[session.turn_index]
            if current.madness == "도주" or (current.madness == "강박" and current.compulsive_weapon is not None):
                await interaction.followup.send("【광기】 재장전 대신 같은 행동을 반복해야 해요.", ephemeral=True)
                return
            if session.pending_attack is not None or not combat_is_active(current):
                await interaction.followup.send("자기 행동 차례에만 재장전할 수 있어요.", ephemeral=True)
                return
            if interaction.user.id != combat_actor_user(session, current):
                await interaction.followup.send("현재 차례인 캐릭터만 재장전할 수 있어요.", ephemeral=True)
                return
            if combat_is_shocked(session, current) or pending_combat_status_check(session, current):
                await interaction.followup.send("상태 탈출·해제 판정을 먼저 진행해 주세요.", ephemeral=True)
                return
            if not 0 <= self.weapon_index < len(current.weapons):
                await interaction.followup.send("무기 선택을 다시 확인해 주세요.", ephemeral=True)
                return
            weapon = current.weapons[self.weapon_index]
            capacity = weapon.ammo_capacity or 0
            if not is_firearm_weapon(weapon) or weapon.broken or capacity <= 0 or (weapon.ammo or 0) >= capacity:
                await interaction.followup.send("현재 재장전할 수 없는 무기예요.", ephemeral=True)
                return
            previous_ammo = weapon.ammo or 0
            if weapon.magic_ammo:
                if current.magic_points is None:
                    try:
                        current.magic_points = await registry.get_combat_magic_points(current.character_value)
                    except Exception as exc:
                        print(f"Combat magic read failed ({type(exc).__name__}).")
                    if current.magic_points is None:
                        await interaction.followup.send("현재 마력을 읽지 못했어요. 마력을 소모하지 않았으니 시트를 확인한 뒤 다시 눌러 주세요.", ephemeral=True)
                        return
                charge = min(capacity - previous_ammo, current.magic_points)
                if charge <= 0:
                    await interaction.followup.send("충전에 사용할 마력이 없어요.", ephemeral=True)
                    return
                previous_magic = current.magic_points
                current.magic_points -= charge
                weapon.ammo = previous_ammo + charge
                append_combat_log(session,
                    f"【즉시 마력충전】 {current.character_name} · {weapon.name} · 탄약 {previous_ammo} → {weapon.ammo}\n"
                    f"마력 {previous_magic} → {current.magic_points} · 턴 소모 없음"
                )
                session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
                session.briefing = f"마력으로 탄환 {charge}발을 충전했어요. 아직 {current.character_name}의 턴이에요!"
                await session.message.edit(content=render_combat_session(session), view=CombatShotCountView(session, self.weapon_index))
                return
            if weapon.reload_count >= 3:
                await interaction.followup.send("이 무기는 이번 전투에서 재장전 3회를 모두 사용했어요.", ephemeral=True)
                return
            weapon.ammo = capacity
            weapon.reload_count += 1
            append_combat_log(session,
                f"【재장전 · 턴 종료】 {current.character_name} · {weapon.name} · 탄약 {previous_ammo} → {capacity} · 재장전 {weapon.reload_count}/3"
            )
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await CombatView(session).complete_attack_turn(f"{with_particle(current.character_name, '가', '이')} {with_particle(weapon.name, '를', '을')} 재장전했어요.")


class CombatTargetSelect(discord.ui.Select):
    def __init__(self, session: CombatSession, weapon_index: int, shot_count: int, targets: list[int]) -> None:
        options = [discord.SelectOption(
            label="무작위 1명", value="random",
            description="현재 무기로 공격 가능한 상대 중 한 명을 무작위로 선택",
        )] + [
            discord.SelectOption(
                label=trim_choice_name(session.participants[index].character_name),
                value=str(index),
                description=f"HP {session.participants[index].hp}/{session.participants[index].max_hp}",
            )
            for index in targets[:24]
        ]
        super().__init__(placeholder="공격할 상대를 선택해 주세요", min_values=1, max_values=1, options=options)
        self.session = session
        self.weapon_index = weapon_index
        self.shot_count = shot_count

    async def callback(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if self.view is not None and not await self.view.ensure_current(interaction):
                return
            attacker = session.participants[session.turn_index]
            if interaction.user.id != combat_actor_user(session, attacker):
                await interaction.response.send_message(f"지금은 **{attacker.character_name}** 차례예요.", ephemeral=True)
                return
            await interaction.response.defer()
            await CombatView(session).resolve_weapon(
                interaction, self.weapon_index, self.shot_count,
                -1 if self.values[0] == "random" else int(self.values[0]),
            )


class CombatTargetView(CombatActionView):
    def __init__(self, session: CombatSession, weapon_index: int, shot_count: int, targets: list[int]) -> None:
        super().__init__(session, back=True)
        self.add_item(CombatTargetSelect(session, weapon_index, shot_count, targets))


class CombatManaSourceSelect(discord.ui.Select):
    def __init__(self, session: CombatSession, targets: list[int], corpses: bool) -> None:
        self.session, self.corpses = session, corpses
        super().__init__(placeholder="제물 선택" if corpses else "마력을 요청할 동료 선택", options=[
            discord.SelectOption(label=trim_choice_name(session.participants[i].character_name), value=str(i),
                                 description=f"마력 {session.participants[i].magic_points}") for i in targets[:25]])

    async def callback(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            if not await self.view.ensure_current(interaction):
                return
            attack = session.pending_attack
            if attack is None or attack.stage != "confirm" or interaction.user.id != combat_actor_user(session, session.participants[attack.attacker_index]):
                await interaction.response.send_message("시전자만 선택할 수 있어요.", ephemeral=True)
                return
            index = int(self.values[0])
            if index not in spell_mana_sources(session, corpses=self.corpses) or attack.spell_requested_donor is not None:
                await interaction.response.send_message("대상을 다시 선택해 주세요.", ephemeral=True)
                return
            if self.corpses:
                attack.spell_sacrifice = index
                session.briefing = spell_funding_prompt(session)
                await interaction.response.edit_message(content=render_combat_session(session), view=CombatSpellCostView(session))
            else:
                attack.spell_requested_donor = index
                attack.spell_request_serial += 1
                donor = session.participants[index]
                caster = session.participants[attack.attacker_index]
                session.briefing = f"{donor.character_name}, {caster.character_name}의 주문에 제공할 마력량을 정해 주세요."
                await interaction.response.edit_message(content=render_combat_session(session), view=CombatManaOfferView(session))


class CombatManaSourceView(CombatActionView):
    def __init__(self, session: CombatSession, targets: list[int], corpses: bool) -> None:
        super().__init__(session)
        self.add_item(CombatManaSourceSelect(session, targets, corpses))
        button = discord.ui.Button(label="돌아가기", style=discord.ButtonStyle.secondary, row=4)
        async def back(interaction: discord.Interaction) -> None:
            async with session.lock:
                if not await self.ensure_current(interaction):
                    return
                attack = session.pending_attack
                if attack is None or attack.stage != "confirm" or interaction.user.id != combat_actor_user(session, session.participants[attack.attacker_index]):
                    await interaction.response.send_message("시전자만 돌아갈 수 있어요.", ephemeral=True)
                    return
                if attack.spell_requested_donor is not None:
                    await interaction.response.send_message("마력 요청이 진행 중이에요. 현재 화면의 요청 취소를 눌러 주세요.", ephemeral=True)
                    return
                session.briefing = spell_funding_prompt(session)
                await interaction.response.edit_message(content=render_combat_session(session), view=CombatSpellCostView(session))
        button.callback = back
        self.add_item(button)


class CombatManaAmountModal(discord.ui.Modal, title="제공할 마력"):
    amount = discord.ui.TextInput(label="제공할 마력량", placeholder="숫자로 입력해 주세요", min_length=1, max_length=4)

    def __init__(self, session: CombatSession) -> None:
        super().__init__()
        self.session = session
        self.attack = session.pending_attack
        self.request_serial = self.attack.spell_request_serial
        self.donor_index = self.attack.spell_requested_donor

    async def on_submit(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            attack = session.pending_attack
            if (combat_sessions.get(session.channel_id) is not session or session.phase != "combat"
                    or attack is not self.attack or attack.stage != "confirm"
                    or attack.spell_requested_donor != self.donor_index or attack.spell_request_serial != self.request_serial):
                await interaction.response.send_message("이미 종료된 마력 요청이에요.", ephemeral=True)
                return
            donor = session.participants[self.donor_index]
            if interaction.user.id != donor.user_id:
                await interaction.response.send_message("요청받은 캐릭터만 제공량을 정할 수 있어요.", ephemeral=True)
                return
            others = sum(amount for i, amount in attack.spell_donations.items() if i != self.donor_index)
            maximum = min(donor.magic_points or 0, max(0, attack.spell_costs.get("마력", 0) - others))
            text = str(self.amount.value).strip()
            if not text.isascii() or not text.isdecimal() or not 1 <= int(text) <= maximum or self.donor_index not in spell_mana_sources(session):
                await interaction.response.send_message(f"1~{maximum} 사이의 마력을 입력해 주세요. 다시 마력 제공을 눌러 입력할 수 있어요.", ephemeral=True)
                return
            attack.spell_donations[self.donor_index] = int(text)
            attack.spell_requested_donor = None
            attack.spell_request_serial += 1
            session.briefing = spell_funding_prompt(session)
            await interaction.response.defer()
            await session.message.edit(content=render_combat_session(session), view=CombatSpellCostView(session))


class CombatManaOfferView(CombatActionView):
    @discord.ui.button(label="마력 제공", style=discord.ButtonStyle.primary)
    async def offer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            attack = self.session.pending_attack
            if attack is None or attack.stage != "confirm" or attack.spell_requested_donor is None:
                await interaction.response.send_message("이미 종료된 마력 요청이에요.", ephemeral=True)
                return
            if interaction.user.id != self.session.participants[attack.spell_requested_donor].user_id:
                await interaction.response.send_message("요청받은 캐릭터만 제공량을 정할 수 있어요.", ephemeral=True)
                return
            await interaction.response.send_modal(CombatManaAmountModal(self.session))

    @discord.ui.button(label="거절", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.finish_request(interaction, False)

    @discord.ui.button(label="요청 취소", style=discord.ButtonStyle.secondary)
    async def cancel_request(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.finish_request(interaction, True)

    async def finish_request(self, interaction: discord.Interaction, caster: bool) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            attack = self.session.pending_attack
            if attack is None or attack.stage != "confirm" or attack.spell_requested_donor is None:
                await interaction.response.send_message("이미 종료된 마력 요청이에요.", ephemeral=True)
                return
            index = attack.attacker_index if caster else attack.spell_requested_donor
            owner = combat_actor_user(self.session, self.session.participants[index]) if caster else self.session.participants[index].user_id
            if interaction.user.id != owner:
                await interaction.response.send_message("해당 캐릭터만 선택할 수 있어요.", ephemeral=True)
                return
            attack.spell_requested_donor = None
            attack.spell_request_serial += 1
            self.session.briefing = spell_funding_prompt(self.session)
            await interaction.response.edit_message(content=render_combat_session(self.session), view=CombatSpellCostView(self.session))


class CombatSpellCostView(CombatActionView):
    def __init__(self, session: CombatSession) -> None:
        super().__init__(session)
        attack = session.pending_attack
        if attack is None:
            return
        self.confirm.label = "HP를 소모하고 시전" if spell_funding_hp(session, attack) else "시전"
        self.confirm.disabled = attack.spell_requested_donor is not None
        self.confirm.style = discord.ButtonStyle.danger if spell_funding_hp(session, attack) else discord.ButtonStyle.primary
        if attack.spell_costs.get("마력", 0):
            for corpses, label in [(False, "마력 요청"), (True, "제물 사용")]:
                button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=1,
                                           disabled=attack.spell_requested_donor is not None or not spell_mana_sources(session, corpses=corpses))
                async def choose(interaction: discord.Interaction, use_corpses: bool = corpses) -> None:
                    async with session.lock:
                        if not await self.ensure_current(interaction):
                            return
                        if interaction.user.id != combat_actor_user(session, session.participants[session.turn_index]):
                            await interaction.response.send_message("시전자만 선택할 수 있어요.", ephemeral=True)
                            return
                        if session.pending_attack.stage != "confirm" or session.pending_attack.spell_requested_donor is not None:
                            await interaction.response.send_message("마력 요청을 먼저 마쳐 주세요.", ephemeral=True)
                            return
                        targets = spell_mana_sources(session, corpses=use_corpses)
                        if not targets:
                            await interaction.response.send_message("선택할 대상이 없어요.", ephemeral=True)
                            return
                        await interaction.response.edit_message(content=render_combat_session(session, "제물 선택" if use_corpses else "마력을 요청할 동료 선택"),
                                                                view=CombatManaSourceView(session, targets, use_corpses))
                button.callback = choose
                self.add_item(button)

    @discord.ui.button(label="HP를 소모하고 시전", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            attack = self.session.pending_attack
            if attack is None or attack.stage != "confirm" or interaction.user.id != combat_actor_user(self.session, self.session.participants[attack.attacker_index]):
                await interaction.response.send_message("시전자만 결정할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            await CombatView(self.session).cast_spell()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            attack = self.session.pending_attack
            if attack is None or attack.stage != "confirm" or interaction.user.id != combat_actor_user(self.session, self.session.participants[attack.attacker_index]):
                await interaction.response.send_message("시전자만 취소할 수 있어요.", ephemeral=True)
                return
            current = self.session.participants[self.session.turn_index]
            if current.madness == "강박" and current.compulsive_weapon is not None:
                weapon = current.weapons[attack.weapon_index]
                self.session.pending_attack = None
                await interaction.response.defer()
                await CombatView(self.session).repeat_compulsive_action(weapon)
                return
            self.session.pending_attack = None
            current = self.session.participants[self.session.turn_index]
            self.session.briefing = f"시전을 취소했어요. 아직 {current.character_name}의 턴이에요!"
            await interaction.response.edit_message(content=render_combat_session(self.session), view=CombatView(self.session))


async def begin_health_spell_target(session: CombatSession) -> None:
    attack = session.pending_attack
    if attack is None:
        return
    target = session.participants[attack.target_index]
    attack.stage = "defense"
    session.briefing = f"{target.character_name}의 건강 판정 차례예요!"
    await session.message.edit(content=render_combat_session(session), view=CombatSpellDefenseView(session))
    if target.enemy_id:
        await CombatSpellDefenseView(session).resolve_spell()


async def continue_combat_area_spell(session: CombatSession, previous: PendingCombatAttack) -> bool:
    remaining = [index for index in previous.remaining_targets if combat_is_active(session.participants[index])]
    if not remaining:
        return False
    target_index, *rest = remaining
    attack = replace(previous, target_index=target_index, remaining_targets=rest, stage="defense",
                     spell_defense_value=previous.spell_defenses.get(target_index, 0), hits=list(previous.hits), kitchen_next_hit=0)
    session.pending_attack = attack
    defender = session.participants[target_index]
    weapon = session.participants[attack.attacker_index].weapons[attack.weapon_index]
    if weapon.health_resisted_spell:
        await begin_health_spell_target(session)
        return True
    session.briefing = f"전체 주문 · {defender.character_name}의 정신 대항 차례예요!"
    await session.message.edit(content=render_combat_session(session), view=CombatSpellDefenseView(session))
    if defender.enemy_id:
        await CombatSpellDefenseView(session).resolve_spell()
    return True


class CombatSpellDefenseView(CombatActionView):
    def __init__(self, session: CombatSession) -> None:
        super().__init__(session)
        attack = session.pending_attack
        if attack is not None and session.participants[attack.attacker_index].weapons[attack.weapon_index].health_resisted_spell:
            self.resist.label = "건강 판정"

    @discord.ui.button(label="정신 대항", style=discord.ButtonStyle.primary)
    async def resist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            attack = self.session.pending_attack
            if attack is None or interaction.user.id != self.session.participants[attack.target_index].user_id:
                await interaction.response.send_message("주문 대상만 방어 판정을 할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            await self.resolve_spell()

    async def resolve_spell(self) -> None:
        session = self.session
        attack = session.pending_attack
        if attack is None or attack.stage != "defense":
            return
        attack.stage = "resolving"
        defender = session.participants[attack.target_index]
        weapon = session.participants[attack.attacker_index].weapons[attack.weapon_index]
        health_check = weapon.health_resisted_spell
        roll, rolls, modifier = roll_combat_d100(defender, session=session, context="" if health_check else "spirit")
        result = coc_combat_check_result(roll, attack.spell_defense_value)
        attack_rank = combat_success_rank(attack.spell_result)
        defense_rank = combat_success_rank(result)
        blocked = defense_rank > 0 if health_check else attack_rank == 0 or defense_rank >= attack_rank
        label = "건강 판정" if health_check else "정신 대항"
        append_combat_log(session, f"{defender.character_name} · {label}\n"
                          f"{combat_roll_text(defender, roll, rolls, modifier, session=session)} / {attack.spell_defense_value} 【{result}】\n"
                          + ("【주문 불발】 시전 판정 실패" if attack_rank == 0 else "【주문 방어 성공】" if blocked else "【주문 명중】"))
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        await session.message.edit(content=render_combat_session(session), view=None)
        await asyncio.sleep(0.7)
        if not blocked:
            weapon = session.participants[attack.attacker_index].weapons[attack.weapon_index]
            if weapon.damage.strip() == "지배":
                apply_combat_domination(session, attack)
            else:
                await CombatView(session).apply_incoming_hits()
        else:
            session.last_attack_events.append("주문 효과 없음 · 대가는 소모")
        await CombatView(session).complete_attack_turn("건강 판정이 끝났어요." if health_check else "정신 대항 판정이 끝났어요.")


class CombatCounterWeaponSelect(discord.ui.Select):
    def __init__(self, defender: CombatParticipant, indexes: list[int]) -> None:
        options = [discord.SelectOption(
            label=trim_choice_name(f"{defender.weapons[i].name} — {defender.weapons[i].skill_reference}"), value=str(i),
            description=trim_choice_name(f"피해 {defender.weapons[i].damage} · DB {defender.weapons[i].damage_bonus or '없음'}"),
        ) for i in indexes[:25]]
        super().__init__(placeholder="반격할 근접무기 선택", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.resolve(interaction, "반격", int(self.values[0]))


class CombatDefenseView(CombatActionView):
    def __init__(self, session: CombatSession) -> None:
        super().__init__(session)
        attack = session.pending_attack
        if attack is None:
            return
        weapon = session.participants[attack.attacker_index].weapons[attack.weapon_index]
        defender = session.participants[attack.target_index]
        if (is_melee_weapon(weapon) and combat_is_active(session.participants[attack.attacker_index])
                and not maintaining_combat_shock(session, defender)):
            indexes = [i for i, item in enumerate(defender.weapons) if is_melee_weapon(item) and not item.broken and compulsion_allows(defender, item) and defender.dream_forbidden != (item.name, item.skill_reference)]
            if len(indexes) > 1:
                self.add_item(CombatCounterWeaponSelect(defender, indexes))
            elif indexes:
                counter = discord.ui.Button(label="반격", style=discord.ButtonStyle.primary)
                counter.callback = self.counter
                self.add_item(counter)
        if not is_firearm_weapon(weapon) or session.participants[attack.target_index].is_pulp:
            dodge = discord.ui.Button(label="회피" if attack.hits else "그대로 넘기기", style=discord.ButtonStyle.secondary)
            dodge.callback = self.dodge
            self.add_item(dodge)

    async def counter(self, interaction: discord.Interaction) -> None:
        attack = self.session.pending_attack
        if attack is None:
            await self.resolve(interaction, "반격")
            return
        defender = self.session.participants[attack.target_index]
        indexes = [i for i, item in enumerate(defender.weapons) if is_melee_weapon(item) and not item.broken and compulsion_allows(defender, item) and defender.dream_forbidden != (item.name, item.skill_reference)]
        index = indexes[0] if len(indexes) == 1 and "비무장" not in defender.weapons[indexes[0]].name else None
        await self.resolve(interaction, "반격", index)

    async def dodge(self, interaction: discord.Interaction) -> None:
        await self.resolve(interaction, "회피")

    async def resolve(self, interaction: discord.Interaction, action: str, counter_weapon_index: int | None = None) -> None:
        session = self.session
        async with session.lock:
            if not await self.ensure_current(interaction):
                return
            attack = session.pending_attack
            if attack is None:
                await interaction.response.send_message("이미 처리된 방어 판정이에요.", ephemeral=True)
                return
            attacker = session.participants[attack.attacker_index]
            defender = session.participants[attack.target_index]
            if combat_is_shocked(session, defender):
                await interaction.response.send_message("충격 상태에서는 회피·반격을 할 수 없어요.", ephemeral=True)
                return
            if interaction.user.id != defender.user_id:
                await interaction.response.send_message(f"이번 방어는 **{defender.character_name}** 차례예요.", ephemeral=True)
                return
            if action == "반격" and maintaining_combat_shock(session, defender):
                await interaction.response.send_message("충격을 유지하는 동안에는 반격할 수 없어요. 회피를 선택해 주세요.", ephemeral=True)
                return
            if action == "반격" and not is_melee_weapon(attacker.weapons[attack.weapon_index]):
                await interaction.response.send_message("이 공격에는 근접무기로 반격할 수 없어요.", ephemeral=True)
                return
            await interaction.response.defer()

            await self.resolve_roll(action, interaction, counter_weapon_index)

    async def resolve_roll(self, action: str, interaction: discord.Interaction | None = None,
                           counter_weapon_index: int | None = None) -> None:
        """Resolve player and automatic enemy defense under the session lock."""
        session = self.session
        attack = session.pending_attack
        if attack is None:
            return
        attacker = session.participants[attack.attacker_index]
        defender = session.participants[attack.target_index]
        if action == "회피" and not attack.hits:
            append_combat_log(session, f"{defender.character_name} — 공격이 빗나가 회피 굴림 생략")
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await CombatView(session).complete_attack_turn("공격이 빗나가 피해 없이 넘겼어요.")
            return

        counter_weapon: CombatWeapon | None = None
        fumble_weapon: CombatWeapon | None = None
        counter_luck: int | None = None
        resolved = None
        try:
            resolved = await registry.resolve_character_reference(defender.character_value) if not defender.enemy_id else None
            if action == "회피":
                defense_skill = await combat_skill_value(defender, "회피")
            else:
                if counter_weapon_index is not None:
                    if not 0 <= counter_weapon_index < len(defender.weapons):
                        raise SheetError("반격할 무기를 다시 선택해 주세요.")
                    counter_weapon = defender.weapons[counter_weapon_index]
                    if not is_melee_weapon(counter_weapon) or counter_weapon.broken:
                        raise SheetError("고장 나지 않은 근접무기만 반격에 사용할 수 있어요.")
                    counter_weapons = defender.weapons
                else:
                    counter_weapons = await combat_weapons(defender)
                    counter_weapon = next((item for item in counter_weapons if "비무장" in item.name and not item.broken), None)
                if counter_weapon is None:
                    raise SheetError("반격에 사용할 근접무기를 찾지 못했어요.")
                if counter_weapon.malfunction is None:
                    fumble_weapon = next((item for item in counter_weapons if "비무장" in item.name), None)
                    if fumble_weapon is None:
                        fumble_weapon = next((item for item in await combat_weapons(defender) if "비무장" in item.name), None)
                    if fumble_weapon is None:
                        raise SheetError("대실패 피해에 필요한 비무장 무기를 찾지 못했어요.")
                else:
                    counter_luck = await combat_skill_value(defender, "행운")
                    if counter_luck is None:
                        raise SheetError("무기 고장에 필요한 행운 값을 읽지 못했어요.")
                defense_skill = await combat_skill_value(
                    defender, normalize_weapon_skill_reference(counter_weapon.skill_reference)
                )
            if defense_skill is None:
                raise SheetError(f"시트에서 {action} 기능치를 읽지 못했어요.")
        except Exception as exc:
            if resolved is not None:
                registry._skill_cache.pop(f"{resolved[0]}|{resolved[1]}", None)
            print(f"Combat defense read failed ({type(exc).__name__}).")
            session.briefing = f"{defender.character_name}의 {action} 값을 읽지 못했어요. 같은 버튼을 눌러 다시 시도해 주세요."
            await session.message.edit(content=render_combat_session(session), view=CombatDefenseView(session))
            if interaction is not None:
                await interaction.followup.send("판정과 피해를 진행하지 않았어요. 시트 연결과 값을 확인한 뒤 다시 눌러 주세요.", ephemeral=True)
            return

        if counter_weapon is not None and (not compulsion_allows(defender, counter_weapon) or defender.dream_forbidden == (counter_weapon.name, counter_weapon.skill_reference)):
            session.briefing = "광기·잊힌 동작으로 사용할 수 없는 반격 무기예요."
            await session.message.edit(content=render_combat_session(session), view=CombatDefenseView(session))
            return
        if counter_weapon is not None:
            lock_compulsive_weapon(defender, counter_weapon)
        attack.stage = "resolving"
        session.briefing = f"{defender.character_name}의 {action} 판정을 처리하고 있어요."

        roll, rolls, modifier = roll_combat_d100(defender, session=session, context="attack" if action == "반격" else "defense", weapon=counter_weapon)
        defender.defended_round = session.round_number
        result = coc_combat_check_result(roll, defense_skill)
        ranks = {"대실패": 0, "실패": 0, "보통 성공": 1, "어려운 성공": 2, "극단적 성공": 3, "대성공": 4}
        rank = ranks[result]
        attack_ranks = [ranks[hit_result] for _hit_roll, hit_result, _shot in attack.hits]
        append_combat_log(session,
            f"주사위 {combat_roll_text(defender, roll, rolls, modifier, session=session)} / {defense_skill}\n"
            f"【{result}】 {defender.character_name}의 {action} 판정"
            + (f" · {counter_weapon.name}" if counter_weapon is not None else "")
        )
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
        await session.message.edit(content=render_combat_session(session), view=None)
        await asyncio.sleep(0.7)

        if action == "반격" and result == "대실패" and counter_weapon is not None and counter_weapon.malfunction is None:
            assert fumble_weapon is not None
            await apply_combat_fumble_damage(session, defender, fumble_weapon)

        if (counter_weapon is not None and counter_weapon.malfunction is not None
                and roll >= counter_weapon.malfunction):
            counter_weapon.broken = True
            luck_roll, luck_rolls, luck_modifier = roll_combat_d100(defender, session=session)
            succeeded = counter_luck is not None and luck_roll <= counter_luck
            detail = f"행운 주사위 {combat_roll_text(defender, luck_roll, luck_rolls, luck_modifier, session=session)} / {counter_luck}"
            if succeeded:
                outcome = f"【반격 무기 고장 · 행운 성공】 {counter_weapon.name}만 고장났어요."
            else:
                damage, damage_detail = roll_damage_formula(counter_weapon.damage)
                damage, health_text = apply_combat_damage(defender, damage, defender)
                outcome = f"【반격 무기 고장 · 본인에게 {damage} 데미지!】 {defender.character_name} · {health_text}"
                detail += f" · 피해 {damage_detail}"
                await check_combat_major_wound(session, defender, damage)
            append_combat_log(session, detail + "\n" + outcome)
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            session.last_attack_events.append(outcome)
            await session.message.edit(content=render_combat_session(session), view=None)
            await CombatView(session).apply_incoming_hits()
            await CombatView(session).complete_attack_turn("반격 무기가 고장났어요.")
            return

        turn_summary = f"{defender.character_name}의 {action} 판정이 끝났어요."
        if action == "회피":
            avoided = {index for index, attack_rank in enumerate(attack_ranks) if rank >= attack_rank and rank > 0}
            await CombatView(session).apply_incoming_hits(avoided)
            turn_summary = (
                f"{with_particle(defender.character_name, '가', '이')} 공격을 피했어요."
                if len(avoided) == len(attack_ranks)
                else f"{with_particle(defender.character_name, '가', '이')} 공격을 일부 피했어요."
                if avoided
                else f"{with_particle(defender.character_name, '가', '이')} 공격을 피하지 못했어요."
            )
        elif rank > max(attack_ranks, default=0):
            assert counter_weapon is not None
            damage, detail = roll_weapon_damage(counter_weapon, defender.strength, defender.size,
                                               critical=counter_weapon.impaling and result in {"극단적 성공", "대성공"})
            barrier_protected = attacker.enemy_id == "mage" and attacker.mana_barrier > 0
            damage, health_text = apply_combat_damage(attacker, damage, defender, weapon=counter_weapon)
            append_combat_log(session,
                f"{counter_weapon.name} 피해 {detail}\n"
                f"【반격 성공 · {damage} 데미지!】 {attacker.character_name} · {health_text}"
            )
            session.last_attack_events.append(
                f"{defender.character_name}의 {counter_weapon.name} 반격으로 {attacker.character_name}에게 {damage} 데미지! "
                f"({health_text})"
            )
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            session.briefing = f"{defender.character_name}의 반격이 성공했어요. 피해를 적용하고 있어요."
            await session.message.edit(content=render_combat_session(session), view=None)
            await asyncio.sleep(0.7)
            if not barrier_protected:
                await apply_combat_hit_effects(session, defender, attacker, counter_weapon)
            await check_combat_major_wound(session, attacker, damage)
            turn_summary = f"{defender.character_name}의 반격이 성공했어요."
        else:
            append_combat_log(session, f"【반격 실패】 {defender.character_name}")
            session.last_attack_events.append(f"{defender.character_name}의 반격 실패.")
            session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]
            await CombatView(session).apply_incoming_hits()
            turn_summary = f"{defender.character_name}의 반격이 통하지 않았어요."

        await CombatView(session).complete_attack_turn(turn_summary)



FAMILY_SPELLS = {
    "barrage": "마력 난사", "mark": "검은 낙인", "charm": "현혹의 속삭임",
    "poison": "쇠약의 안개", "drain": "마력 약탈", "pit": "지면 파열",
    "silence": "침묵의 봉인", "hold": "마력의 족쇄",
}


def spawn_family_mage(session: CombatSession) -> None:
    if session.family_spawned:
        return
    session.family_spawned = True
    mage = make_raid_enemy("mage")
    randomize_raid_enemy(mage, 1)
    spec = RAID_ENEMIES["mage"]
    mage.dexterity, mage.strength, mage.constitution, mage.size = spec["dex"], spec["str"], spec["con"], spec["size"]
    mage.spirit = 95
    mage.hp = mage.max_hp
    mage.mana_barrier_max = 40 + 10 * sum(p.is_pulp for p in session.participants if not p.enemy_id)
    mage.mana_barrier = mage.mana_barrier_max
    mage.weapons = [CombatWeapon("비무장", "근접전 | 격투", "1d3"), CombatWeapon("마력탄", "마법", "1d6")]
    mage.position = max((p.position for p in session.participants if combat_is_present(p)), default=0) + 2
    mage.field_symbol = "◆"
    session.participants.append(mage)
    append_combat_log(session, "마력이 전장을 뒤덮습니다. 딜리아가 디안에게 칼끝을 돌립니다.")
    session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]


def update_family_alliance(session: CombatSession) -> None:
    if session.family_spawned and not session.family_revenge and not any(p.enemy_id == "mage" and combat_is_present(p) for p in session.participants):
        session.family_revenge = True
        session.family_events.clear()
        if any(p.enemy_id == "hunter" and combat_is_present(p) for p in session.participants):
            append_combat_log(session, "마력이 잦아듭니다. 딜리아가 다시 당신들을 바라봅니다.")
        session.recent_logs = session.recent_logs[-COMBAT_RECENT_LOG_LIMIT:]


def family_targets(session: CombatSession, member: CombatParticipant) -> list[int]:
    if member.enemy_id == "hunter":
        mage = [i for i, p in enumerate(session.participants) if p.enemy_id == "mage" and combat_is_active(p)]
        if mage:
            return mage
    return [i for i, p in enumerate(session.participants) if p is not member and combat_is_active(p)
            and (not p.enemy_id or member.enemy_id == "mage")]


def choose_family_spell(session: CombatSession, mage: CombatParticipant, targets: list[int]) -> tuple[str, int]:
    # Every legal spell keeps a chance; tactical conditions increase its weight.
    weights = {"barrage": 3, "mark": 1, "charm": 1, "poison": 2, "drain": 1, "pit": 1, "silence": 0, "hold": 1}
    clustered = any(sum(abs(session.participants[j].position - session.participants[i].position) <= 1 for j in targets) >= 2 for i in targets)
    casters = [i for i in targets if any(is_spell_weapon(w) for w in session.participants[i].weapons) and not session.participants[i].silenced]
    rich = [i for i in targets if (session.participants[i].magic_points or 0) > 0]
    melee = [i for i in targets if session.participants[i].enemy_id == "hunter" or any(is_melee_weapon(w) for w in session.participants[i].weapons)]
    if clustered:
        weights["mark"] += 4
        weights["pit"] += 3
    if any(session.participants[i].hp * 3 <= session.participants[i].max_hp for i in targets):
        weights["barrage"] += 5
    if mage.mana_barrier * 40 < 25 * mage.mana_barrier_max or (mage.magic_points or 0) < 8:
        weights["drain"] += 6
    if casters:
        weights["silence"] = 5 + 3 * any(session.participants[i].last_used_weapon and session.participants[i].last_used_weapon[1] == "주문" for i in casters)
    if melee:
        weights["hold"] += 4
    if not rich:
        weights["drain"] = 0
    if session.family_events:
        weights["mark"] = weights["pit"] = 0
    if any(e.spec.independent_hold for p in session.participants for e in active_combat_statuses(session, p)):
        weights["hold"] = 0
    weights[session.family_last_spell] = 0
    for key in weights:
        if (3 if key in {"mark", "pit", "poison"} else 2) > (mage.magic_points or 0):
            weights[key] = 0
    keys = [key for key, value in weights.items() if value > 0]
    key = random.choices(keys, weights=[weights[k] for k in keys], k=1)[0]
    pool = casters if key == "silence" else rich if key == "drain" else melee if key == "hold" else targets
    if key == "barrage" and any(session.participants[i].hp * 3 <= session.participants[i].max_hp for i in targets):
        pool = [min(targets, key=lambda i: session.participants[i].hp)]
    if key in {"mark", "pit"}:
        density = max(sum(abs(session.participants[j].position - session.participants[i].position) <= (1 if key == "mark" else 0) for j in targets) for i in targets)
        pool = [i for i in targets if sum(abs(session.participants[j].position - session.participants[i].position) <= (1 if key == "mark" else 0) for j in targets) == density]
    return key, random.choice(pool)


async def family_spell_value(session: CombatSession, target: int, key: str) -> int:
    member = session.participants[target]
    value = member.constitution if key == "poison" else await combat_skill_value(member, "정신")
    if value is None:
        raise SheetError("주문 방어에 필요한 특성치를 읽지 못했어요.")
    return value


async def take_family_turn(session: CombatSession) -> None:
    actor = session.participants[session.turn_index]
    if session.family_last_serial != session.turn_serial:
        session.family_last_serial = session.turn_serial
        session.family_ops.clear()
        actor.guarded_round = 0
        if combat_is_shocked(session, actor):
            for effect in active_combat_statuses(session, actor)[:]:
                if "충격" in effect.spec.kinds:
                    await attempt_combat_status_escape(session, actor, effect)
            await CombatView(session).complete_attack_turn("충격 탈출 판정으로 차례를 마쳤어요.")
            return
        if maintaining_combat_shock(session, actor):
            await CombatView(session).complete_attack_turn("구속을 유지하고 있어요.")
            return
        targets = family_targets(session, actor)
        if not targets:
            await CombatView(session).complete_attack_turn()
            return
        if actor.enemy_id == "hunter":
            actor.pattern_step += 1
            phase = (actor.pattern_step - 1) % 4
            target = actor.hunt_target if phase != 0 and actor.hunt_target in targets else random.choice(targets)
            gap_before_move = abs(actor.position - session.participants[target].position)
            if phase == 2 and not any(session.participants[i].enemy_id == "mage" for i in targets):
                actor.guarded_round = session.round_number
                await show_raid_event(session, "【반격 태세】 딜리아가 칼을 세웁니다. 다음 자기 차례까지 회피 보너스 +1")
                await CombatView(session).complete_attack_turn("딜리아가 방어에 집중했어요.")
                return
            if phase == 0 and not any(session.participants[i].enemy_id == "mage" for i in targets):
                actor.hunt_target = target
                actor.round_attack_distance = abs(actor.position - session.participants[target].position)
                await show_raid_event(session, f"【사냥감 지목】 {session.participants[target].character_name} · 다음 추격 전 거리를 벌리면 공격 패널티 +1")
            if combat_distance(session, session.turn_index, target) != "근거리":
                roll, rolls, modifier = roll_combat_d100(actor, session=session)
                move_combat_position(session, session.turn_index, target, -1, adjacent=True)
                success = combat_success_rank(coc_combat_check_result(roll, actor.dexterity)) > 0
                await show_raid_event(session, f"민첩 {combat_roll_text(actor, roll, rolls, modifier, session=session)} / {actor.dexterity}\n【파고들기 {'성공' if success else '실패'}】 딜리아")
                if not success:
                    await CombatView(session).complete_attack_turn("접근했지만 공격하지 못했어요.")
                    return
            weapon = 2 if phase == 3 and session.participants[target].enemy_id != "mage" else 1
            penalty = -1 if phase == 1 and gap_before_move > actor.round_attack_distance else 0
            await begin_raid_attack(session, session.turn_index, target, weapon, modifier=penalty)
            return
        session.family_mage_turns += 1
        for event in session.family_events[:]:
            if event["due"] <= session.family_mage_turns:
                session.family_events.remove(event)
                session.family_ops.append({"kind": "hazard", "event": event})
        if actor.barrier_rebuild:
            session.family_ops.append({"kind": "rebuild"})
        if (actor.magic_points or 0) < 2:
            session.family_ops.append({"kind": "recharge"})
        session.family_ops.append({"kind": "select_spell"})
    while session.family_ops:
        op = session.family_ops[0]
        if op["kind"] == "select_spell":
            targets = family_targets(session, actor)
            if not targets:
                session.family_ops.pop(0)
                continue
            key, target = choose_family_spell(session, actor, targets)
            op = {"kind": "cast", "spell": key, "target": target}
            session.family_ops[0] = op
        if op["kind"] == "cast" and op["spell"] in {"charm", "poison", "drain", "silence", "hold"}:
            targets = family_targets(session, actor) if op["spell"] == "poison" else [op["target"]]
            try:
                values = {i: await family_spell_value(session, i, op["spell"]) for i in targets if combat_is_active(session.participants[i])}
            except Exception as exc:
                print(f"Family raid spell read failed ({type(exc).__name__}).")
                session.briefing = "방어 값을 읽지 못했어요. 다시 시도해 주세요."
                await publish_combat_panel(session, FamilyRetryView(session))
                return
            op["values"] = values
        session.family_ops.pop(0)
        if op["kind"] == "hazard":
            event = op["event"]
            center = session.participants[event["target"]].position if event["kind"] == "mark" else event["position"]
            for i in family_targets(session, actor):
                member = session.participants[i]
                if abs(member.position - center) > (1 if event["kind"] == "mark" else 0):
                    continue
                raw, detail = roll_damage_formula("2d4" if event["kind"] == "mark" else "2d6")
                damage, health = apply_combat_damage(member, raw, actor)
                session.last_attack = event["name"]
                session.last_attack_events.append(f"{member.character_name} · {damage} 피해 · {health}")
                await show_raid_event(session, f"{detail}\n【{event['name']} · {damage} 피해】 {member.character_name} · {health}")
                await check_combat_major_wound(session, member, damage)
            if await finish_combat_if_decided(session):
                return
            continue
        if op["kind"] == "rebuild":
            actor.mana_barrier = actor.mana_barrier_max
            actor.barrier_rebuild = False
            await show_raid_event(session, f"【마나장벽 복구】 내구도 {actor.mana_barrier_max} · 디안이 주문을 이어갑니다.")
            continue
        if op["kind"] == "recharge":
            actor.magic_points = min(19, (actor.magic_points or 0) + 5)
            await show_raid_event(session, f"【마력 회복】 디안 · 마력 {actor.magic_points} · 주문을 이어갑니다.")
            continue
        key, target = op["spell"], op["target"]
        session.family_last_spell = key
        actor.magic_points = max(0, (actor.magic_points or 0) - (3 if key in {"mark", "pit", "poison"} else 2))
        if key in {"mark", "pit"}:
            event = {"kind": key, "name": FAMILY_SPELLS[key], "target": target,
                     "position": session.participants[target].position, "due": session.family_mage_turns + 1}
            session.family_events.append(event)
            await show_raid_event(session, f"【{event['name']} 예고】 다음 디안 차례에 발동!\n" +
                                  (f"{session.participants[target].field_symbol}※ {session.participants[target].character_name}에게서 떨어지세요." if key == "mark" else f"위치 {event['position']}에서 이동하세요."))
            continue
        if key == "barrage":
            pool = family_targets(session, actor)
            if pool:
                shots = [target] + [random.choice(pool) for _ in range(2)]
                await begin_raid_attack(session, session.turn_index, shots[0], 1, remaining_targets=shots[1:])
                return
            continue
        values = op["values"]
        if not values:
            continue
        target, *rest = list(values)
        roll, rolls, modifier = (0, [], 0) if key == "poison" else roll_combat_d100(actor, session=session, context="spell_attack")
        result = "보통 성공" if key == "poison" else coc_combat_check_result(roll, 95)
        session.last_attack = f"디안 · {FAMILY_SPELLS[key]}"
        session.last_attack_events = []
        if key != "poison":
            await show_raid_event(session, f"마법 {combat_roll_text(actor, roll, rolls, modifier, session=session)} / 95 【{result}】\n{FAMILY_SPELLS[key]}")
        session.pending_attack = PendingCombatAttack(session.turn_index, target, 0, 95, 1, stage="defense", family_spell=key,
                                                    spell_result=result, spell_defenses=values, spell_defense_value=values[target], remaining_targets=rest)
        await present_family_spell(session)
        return
    await CombatView(session).complete_attack_turn("디안의 주문이 끝났어요.")


async def present_family_spell(session: CombatSession) -> None:
    attack = session.pending_attack
    if attack is None:
        return
    member = session.participants[attack.target_index]
    label = "건강 판정" if attack.family_spell == "poison" else "정신 대항"
    session.briefing = f"{member.character_name} · {FAMILY_SPELLS[attack.family_spell]} · {label}"
    await session.message.edit(content=render_combat_session(session), view=FamilySpellView(session))
    if member.enemy_id:
        await resolve_family_spell(session)


async def continue_family_spell(session: CombatSession, attack: PendingCombatAttack) -> bool:
    remaining = [i for i in attack.remaining_targets if combat_is_active(session.participants[i])]
    if not remaining:
        return False
    target, *rest = remaining
    session.pending_attack = replace(attack, target_index=target, remaining_targets=rest, stage="defense", spell_defense_value=attack.spell_defenses[target])
    await present_family_spell(session)
    return True


async def resolve_family_spell(session: CombatSession) -> None:
    attack = session.pending_attack
    if attack is None or attack.stage != "defense":
        return
    attack.stage = "resolving"
    source = session.participants[attack.attacker_index]
    target = session.participants[attack.target_index]
    key = attack.family_spell
    roll, rolls, modifier = roll_combat_d100(target, session=session, context="" if key == "poison" else "spirit")
    result = coc_combat_check_result(roll, attack.spell_defense_value)
    rank = combat_success_rank(result)
    blocked = rank > 0 if key == "poison" else combat_success_rank(attack.spell_result) == 0 or rank >= combat_success_rank(attack.spell_result)
    await show_raid_event(session, f"{target.character_name} · {'건강' if key == 'poison' else '정신'} {combat_roll_text(target, roll, rolls, modifier, session=session)} / {attack.spell_defense_value}\n【{result} · {'방어 성공' if blocked else FAMILY_SPELLS[key]}】")
    if not blocked:
        if key == "poison":
            raw, detail = roll_damage_formula("1d6")
            damage, health = apply_combat_damage(target, raw, source)
            target.paralysis_stacks = min(2, target.paralysis_stacks + 1)
            target.paralysis_skip_end_serial = -1
            await show_raid_event(session, f"{detail}\n【쇠약의 안개 · {damage} 피해 · 마비】 {target.character_name} · {health}")
            await check_combat_major_wound(session, target, damage)
        elif key == "silence":
            target.silenced = True
            await show_raid_event(session, f"【침묵의 봉인】 {target.character_name} · 다음 자기 차례 종료까지 주문 불가")
        elif key == "drain":
            amount = min(target.magic_points or 0, random.randint(1, 4))
            target.magic_points = (target.magic_points or 0) - amount
            source.magic_points = min(19, (source.magic_points or 0) + amount)
            source.mana_barrier = min(source.mana_barrier_max, source.mana_barrier + amount)
            await show_raid_event(session, f"【마력 약탈】 {target.character_name} 마력 -{amount} · 마나장벽 {source.mana_barrier}")
        elif key == "charm":
            apply_combat_domination(session, attack)
        elif key == "hold":
            spec = CombatStatusSpec(("충격",), "정신", independent_hold=True)
            weapon = CombatWeapon("마력의 족쇄", "주문", "0", effects=[spec])
            apply_combat_weapon_statuses(session, source, target, weapon)
    await CombatView(session).complete_attack_turn("주문 방어 판정이 끝났어요.")


async def resolve_family_domination(session: CombatSession) -> bool:
    member = session.participants[session.turn_index]
    source = member.domination_source
    if source is None or session.participants[source].enemy_id != "mage" or not combat_is_controlled(session, session.turn_index):
        return False
    if combat_is_shocked(session, member) or pending_combat_status_check(session, member):
        return False
    targets = [i for i, p in enumerate(session.participants) if p is not member and i != source and combat_is_active(p)
               and combat_distance(session, session.turn_index, i) == "근거리"]
    weapon_index = next((i for i, w in enumerate(member.weapons) if "비무장" in w.name and is_melee_weapon(w)), None)
    if not targets or weapon_index is None or maintaining_combat_shock(session, member):
        await CombatView(session).complete_attack_turn("【현혹】 공격할 근거리 대상이 없어 차례를 마쳤어요.")
        return True
    target = random.choice(targets)
    weapon = member.weapons[weapon_index]
    try:
        value = await combat_skill_value(member, normalize_weapon_skill_reference(weapon.skill_reference))
        if value is None:
            raise SheetError("현혹된 맨손 공격 값을 읽지 못했어요.")
    except Exception as exc:
        print(f"Family dominated attack read failed ({type(exc).__name__}).")
        session.briefing = "현혹된 맨손 공격 값을 읽지 못했어요. 다시 시도해 주세요."
        await publish_combat_panel(session, FamilyRetryView(session))
        return True
    session.pending_attack = PendingCombatAttack(session.turn_index, target, weapon_index, value, 1, fumble_weapon=weapon)
    session.last_attack = f"【현혹】 {member.character_name} → {session.participants[target].character_name} · 맨손 공격"
    session.last_attack_events = []
    await publish_combat_panel(session, None)
    await CombatView(session).process_pending_attack()
    return True


class FamilyRetryView(CombatActionView):
    @discord.ui.button(label="주문 처리 재시도", style=discord.ButtonStyle.primary)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            if interaction.user.id != self.session.owner_id:
                await interaction.response.send_message("모집한 사람이 재시도해 주세요.", ephemeral=True)
                return
            await interaction.response.defer()
            if combat_is_controlled(self.session, self.session.turn_index):
                await repost_combat_turn(self.session)
            else:
                await take_family_turn(self.session)


class FamilySpellView(CombatActionView):
    def __init__(self, session: CombatSession) -> None:
        super().__init__(session)
        if session.pending_attack.family_spell == "poison":
            self.resist.label = "건강 판정"

    @discord.ui.button(label="정신 대항", style=discord.ButtonStyle.primary)
    async def resist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.session.lock:
            if not await self.ensure_current(interaction):
                return
            attack = self.session.pending_attack
            if interaction.user.id != self.session.participants[attack.target_index].user_id:
                await interaction.response.send_message("해당 대상만 판정할 수 있어요.", ephemeral=True)
                return
            await interaction.response.defer()
            await resolve_family_spell(self.session)



async def start_combat(interaction: discord.Interaction, mode: str = "개인전", enemy_id: str = "") -> bool:
    channel_id = interaction.channel_id
    if channel_id in combat_sessions:
        await send_response(interaction, "이 채널에는 이미 진행 중인 모의전투가 있어요.", ephemeral=True)
        return False
    session = CombatSession(
        guild_id=interaction.guild_id or 0,
        channel_id=channel_id,
        owner_id=interaction.user.id,
        participants=[make_raid_enemy(enemy_id)] if mode == "레이드" else [],
        mode=mode,
        enemy_id=enemy_id,
        fog_start_round=10 if enemy_id == "chimera" else 0,
    )
    combat_sessions[channel_id] = session
    await interaction.response.send_message(render_combat_session(session), view=CombatLobbyView(session))
    session.message = await interaction.original_response()
    return True


async def join_combat(interaction: discord.Interaction, character: str, *, expected_session: CombatSession | None = None) -> bool:
    session = combat_sessions.get(interaction.channel_id)
    if session is None or session.phase != "lobby" or (expected_session is not None and session is not expected_session):
        await send_response(interaction, "이 모집은 이미 종료됐어요. 새 모집창의 참여 버튼을 눌러 주세요!", ephemeral=True)
        return False
    # A component update edits the private picker through its interaction token.
    # Message.edit uses the bot endpoint, which cannot edit ephemeral messages.
    await interaction.response.defer()
    owned = await registry.get_character_choices_for_user(interaction.user.id)
    selected = next((value for value, _ in owned if value.casefold() == character.casefold()), None)
    if selected is None:
        await interaction.edit_original_response(content="직접 등록한 캐릭터만 참가시킬 수 있어요. 참여 버튼으로 다시 선택해 주세요.", view=None)
        return False
    resolved = await registry.resolve_character_reference(selected)
    if resolved is None:
        await interaction.edit_original_response(content="캐릭터 시트를 찾지 못했어요. `/캐릭터등록`에서 다시 등록해 주세요.", view=None)
        return False
    display_name = selected.partition("|")[2].strip()
    async with session.lock:
        if combat_sessions.get(session.channel_id) is not session or session.phase != "lobby":
            await interaction.edit_original_response(content="모집이 이미 끝났어요.", view=None)
            return False
        if sum(not member.enemy_id for member in session.participants) >= 8:
            await interaction.edit_original_response(content="모의전투에는 캐릭터를 최대 8명까지 참가시킬 수 있어요.", view=None)
            return False
        if any(member.character_value.casefold() == selected.casefold() for member in session.participants):
            await interaction.edit_original_response(content="이 캐릭터는 이미 참가했어요.", view=None)
            return False
        session.participants.append(CombatParticipant(
            interaction.user.id,
            interaction.user.display_name,
            selected,
            display_name,
            is_pulp=resolved[0] == SORTED_TABLE_SPREADSHEET_ID,
        ))
        if session.message is not None:
            try:
                await session.message.edit(content=render_combat_session(session), view=CombatLobbyView(session))
            except (discord.HTTPException, OSError) as exc:
                print(f"Combat lobby roster refresh failed after join ({type(exc).__name__}).")
    try:
        await interaction.edit_original_response(
            content=f"**{display_name}** 캐릭터가 모의전투에 참가했어요! 다른 캐릭터는 모집창의 참여 버튼으로 추가해 주세요.",
            view=None,
        )
    except (discord.HTTPException, OSError) as exc:
        # Registration has succeeded. A UI cleanup error must not report failure.
        print(f"Combat join confirmation update failed ({type(exc).__name__}).")
    return True


class CombatRaidSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="모집할 레이드를 선택해 주세요",
            options=[
                discord.SelectOption(label="연습용 허수아비", value="dummy"),
                discord.SelectOption(label="실험키메라", value="chimera"),
                discord.SelectOption(label="꿈꾸는 고치", value="dream"),
                discord.SelectOption(label="루베랄드의 칼날과 광기", value="hunter"),
                discord.SelectOption(label="레레의 완벽한 식사", value="kitchen"),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if await start_combat(interaction, "레이드", self.values[0]):
            view.stop()
            try:
                await view.command_interaction.delete_original_response()
            except discord.HTTPException as exc:
                print(f"레이드 선택 메뉴 닫기 실패: {exc}")


class CombatRaidPicker(discord.ui.View):
    def __init__(self, interaction: discord.Interaction) -> None:
        super().__init__(timeout=180)
        self.command_interaction = interaction
        self.add_item(CombatRaidSelect())


@bot.tree.command(name="모의전투", description="개인전·레이드를 모집해요! 참가는 모집창의 참여 버튼을 눌러 주세요.")
@app_commands.guild_only()
@app_commands.rename(mode="종류")
@app_commands.choices(mode=[app_commands.Choice(name="개인전", value="duel"),
                            app_commands.Choice(name="레이드", value="raid")])
@app_commands.describe(mode="개인전 또는 레이드를 선택해 주세요.")
async def combat_command(interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
    if mode.value == "duel":
        await start_combat(interaction, "개인전")
        return
    if interaction.channel_id in combat_sessions:
        await send_response(interaction, "이 채널에는 이미 진행 중인 모의전투가 있어요.", ephemeral=True)
        return
    await interaction.response.send_message("모집할 레이드를 선택해 주세요.", view=CombatRaidPicker(interaction), ephemeral=True)


@bot.tree.command(name="관찰", description="캐릭터들이 무엇을 하고 있는지 살펴보고 올게요!")
@app_commands.rename(character="캐릭터")
@app_commands.autocomplete(character=character_autocomplete)
async def observe(interaction: discord.Interaction, character: str) -> None:
    await interaction.response.defer(thinking=True)
    try:
        resolved = await registry.resolve_character_reference(character)
        if resolved is None:
            await send_response(interaction, "등록된 캐릭터를 시트에서 찾지 못했어요. `/캐릭터등록`에서 다시 등록해 주세요!", ephemeral=True)
            return
        _sheet_id, character_name = resolved

        if random.random() < 0.30:
            activity, reaction = random.choice(OBSERVATION_REST_ACTIVITIES)
            try:
                same_sheet = await registry.get_character_tab_choices(_sheet_id)
                other_names = [
                    value.partition("|")[2].strip()
                    for value, _label in same_sheet
                    if value.partition("|")[2].strip().casefold() != character_name.casefold()
                ]
                if other_names and random.randrange(3) == 0:
                    partner = random.choice(other_names)
                    activity, reaction = personalize_activity(
                        random.choice(OBSERVATION_REST_WITH_OTHER), character_name, partner
                    )
            except Exception as exc:
                print(f"Observation rest character lookup failed ({type(exc).__name__}).")
            await send_response(
                interaction,
                f"레레가 살짝 보고 왔는데, **{character_name}**{topic_particle(character_name)} {activity} {reaction}",
            )
            return

        data = await registry._get_skill_data(character)
        if not data or not data.values:
            await send_response(interaction, "시트에서 캐릭터의 기능치를 찾지 못했어요. 캐릭터 등록과 시트 내용을 확인해 주세요!")
            return
        if data.occupation and random.random() < 0.10:
            occupation_activity = random.choice([
                f"{data.occupation} 일을 하고 있었어요! 집중하는 모습이 눈에 들어오네요!",
                f"{data.occupation} 일을 시작하기 전에 오늘 일정을 확인하고 있었어요! 차근차근 준비하는 모습이 보기 좋아요!",
            ])
            await send_response(
                interaction,
                f"레레가 살짝 보고 왔는데, **{character_name}**{topic_particle(character_name)} {occupation_activity}",
            )
            return
        candidates = []
        for skill, value in data.values.items():
            base_name = skill.split("|", 1)[0].strip()
            if base_name.casefold() in {name.casefold() for name in CHARACTERISTIC_NAMES}:
                continue
            parts = skill.split("|", 1)
            lookup_name = parts[1].strip() if len(parts) > 1 and parts[1].strip().casefold() == "수사과학" else base_name
            default = SKILL_BASE_VALUES.get(lookup_name, 20)
            dexterity = next((v for k, v in data.values.items() if k.casefold() == "민첩"), None)
            if lookup_name.casefold() == "회피" and dexterity is not None:
                default = dexterity // 2
            candidates.append((skill, max(1, value - default + 1)))
        if not candidates:
            await send_response(interaction, "이 캐릭터의 기능치를 찾지 못했어요. 시트에 기능치가 있는지 확인해 주세요!")
            return

        if data.invested_points is not None:
            invested = []
            uninvested = []
            for skill, weight in candidates:
                points = next((v for k, v in data.invested_points.items() if k.casefold() == skill.casefold()), 0)
                if points > 0:
                    invested.append((skill, points))
                else:
                    uninvested.append(skill)
            if invested:
                selected_skill = random.choice(uninvested) if uninvested and random.randrange(100) >= 95 else weighted_choice(invested)
            else:
                selected_skill = random.choice([skill for skill, _ in candidates])
        else:
            selected_skill = weighted_choice(candidates)

        sheet_id, character_name = resolved
        other_names = []
        for value, _name in await registry.get_character_tab_choices(sheet_id):
            other_name = value.partition("|")[2]
            if other_name and other_name.casefold() != character_name.casefold() and other_name.casefold() not in {n.casefold() for n in other_names}:
                other_names.append(other_name)
        partner = random.choice(other_names) if other_names else None
        action, reaction = ObservationActivities.pick(selected_skill, character_name, partner)
        action = action.replace("있어요.", "있었어요!")
        await send_response(interaction, f"레레가 살짝 보고 왔는데, **{character_name}**{topic_particle(character_name)} {action} {reaction}")
    except SheetError as exc:
        await send_response(interaction, str(exc), ephemeral=True)
    except Exception as exc:
        print(f"Observation failed ({type(exc).__name__}).")
        await send_response(interaction, "관찰할 수 없었어요. 잠시 후 다시 시도해 주세요!", ephemeral=True)


def weighted_choice(candidates: list[tuple[str, int]]) -> str:
    total = sum(max(1, weight) for _, weight in candidates)
    ticket = random.randrange(total)
    for skill, weight in candidates:
        ticket -= max(1, weight)
        if ticket < 0:
            return skill
    return candidates[-1][0]


@bot.tree.command(name="응원", description="레레가 응원할게요!")
async def cheer(interaction: discord.Interaction) -> None:
    if random.random() < 0.10:
        message = random.choice(FLAT_CHEER_MESSAGES)
        if await send_flat_response(interaction, message):
            return
        await send_response(interaction, message)
        return
    await send_response(interaction, random.choice(CHEER_MESSAGES))


@bot.tree.command(name="선택", description="쉼표로 나눠서 말해주면 하나를 골라줄게요!")
@app_commands.rename(items="항목들")
async def choose(interaction: discord.Interaction, items: str) -> None:
    choices = [item.strip() for item in re.split(r"[,，、]", items) if item.strip()]
    if len(choices) < 2:
        await send_response(interaction, "쉼표로 나눠서 선택지를 두 개 이상 입력해 주세요! 예: `빨강, 파랑, 초록`", ephemeral=True)
        return
    if random.random() < 0.05:
        message = "제가 대신 말씀드리겠습니다. 선택지가 전부 마음에 들지 않는군요. 다시 시도해주십시오."
        if await send_flat_response(interaction, message):
            return
        await send_response(interaction, message)
        return
    await send_response(interaction, f"레레가 고른 건,  **[{random.choice(choices)}]** 예요!")


@bot.tree.command(name="기능판정", description="캐릭터와 기능을 골라 바로 판정해요!")
@app_commands.rename(character="캐릭터", skill="기능", mode="패널티_보너스")
@app_commands.autocomplete(character=character_autocomplete, skill=skill_autocomplete, mode=roll_mode_autocomplete)
async def skill_check(interaction: discord.Interaction, character: str, skill: str, mode: str | None = None) -> None:
    valid_modes = {None, "", "패널티+1", "패널티+2", "보너스+1", "보너스+2"}
    if mode not in valid_modes:
        await send_response(interaction, "패널티/보너스 값이 올바르지 않아요. 선택 목록에서 `패널티 +1`, `패널티 +2`, `보너스 +1`, `보너스 +2` 중 하나를 골라 주세요. 비워두면 일반 굴림이에요!", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        skill_value = await registry.get_skill_value(character, skill)
        if skill_value is None:
            await send_response(interaction, "캐릭터나 기능값을 시트에서 찾지 못했어요. `/캐릭터등록`에서 캐릭터를 등록하고 기능 이름을 확인해 주세요!")
            return
        character_name = character.partition("|")[2].strip() or character
        mode_label = {"패널티+1": " — 패널티 +1", "패널티+2": " — 패널티 +2", "보너스+1": " — 보너스 +1", "보너스+2": " — 보너스 +2"}.get(mode, "")
        roll_count = 2 if mode in {"패널티+1", "보너스+1"} else 3 if mode in {"패널티+2", "보너스+2"} else 1
        rolls = [random.randint(1, 100) for _ in range(roll_count)]
        is_penalty = bool(mode and mode.startswith("패널티"))
        is_bonus = bool(mode and mode.startswith("보너스"))
        result_value = max(rolls) if is_penalty else min(rolls) if is_bonus else rolls[0]
        is_sanity = skill.casefold() == "이성"
        if is_sanity:
            result = "성공" if result_value <= skill_value else "실패"
        elif result_value == 1:
            result = "대성공"
        elif (skill_value < 50 and result_value >= 95) or (skill_value >= 50 and result_value == 100):
            result = "대실패"
        elif result_value <= skill_value // 5:
            result = "극단적 성공"
        elif result_value <= skill_value // 2:
            result = "어려운 성공"
        elif result_value <= skill_value:
            result = "보통 성공"
        else:
            result = "실패"
        succeeded = result not in {"실패", "대실패"}
        ending = "이에요!" if succeeded else "예요!"
        roll_display = f"[ {', '.join(map(str, rolls))} ]"
        applied = (f"이 나왔으므로 더 높은 값인 [ {result_value} ]을 적용해서 " if is_penalty else
                   f"이 나왔으므로 더 낮은 값인 [ {result_value} ]을 적용해서 " if is_bonus else "이 나왔으므로 ")
        emote_suffix = ""
        try:
            emote_name = await registry.get_character_emote_name(character, succeeded)
            emote = next((item for item in (interaction.guild.emojis if interaction.guild else []) if emote_name and item.name.casefold() == emote_name.casefold()), None)
            if emote:
                emote_suffix = f" {emote}"
        except Exception as exc:
            print(f"Character emote lookup failed ({type(exc).__name__}).")
        await send_response(interaction, f"**{character_name} — {skill} ({skill_value}){mode_label}**\n> {roll_display}{applied}***{result}*** {ending}{emote_suffix}")
    except SheetError as exc:
        await send_response(interaction, str(exc))
    except Exception as exc:
        print(f"Skill check failed ({type(exc).__name__}).")
        await send_response(interaction, "기능판정 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요!")


@bot.tree.command(name="임의판정", description="기능치를 입력해 시트 없이 판정해요!")
@app_commands.rename(skill_value="기능치")
async def arbitrary_check(interaction: discord.Interaction, skill_value: app_commands.Range[int, 1, 100]) -> None:
    roll = random.randint(1, 100)
    if roll == 1:
        result = "대성공"
    elif (skill_value < 50 and roll >= 95) or (skill_value >= 50 and roll == 100):
        result = "대실패"
    elif roll <= skill_value // 5:
        result = "극단적 성공"
    elif roll <= skill_value // 2:
        result = "어려운 성공"
    elif roll <= skill_value:
        result = "보통 성공"
    else:
        result = "실패"
    ending = "예요!" if result in {"실패", "대실패"} else "이에요!"
    await send_response(interaction, f"**임의 판정 ({skill_value})**\n> 1d100 [{roll}]이 나와서 ***{result}*** {ending}")


async def roll_dice_command(interaction: discord.Interaction, expression: str, *, ephemeral: bool) -> None:
    await interaction.response.defer(ephemeral=ephemeral, thinking=True)
    try:
        total, rolls = DiceExpressionEvaluator(expression).evaluate()
        dice_results = " + ".join(rolls) if rolls else f"계산값 [{format_decimal(total)}]"
        prefix = "이건 비밀인데...\n" if ephemeral else ""
        await interaction.edit_original_response(content=f"{prefix}굴린 주사위: `{expression}`\n주사위 값이 {dice_results}가 나와서, [{format_decimal(total)}]예요!")
    except (DiceFormatError, DiceLimitError) as exc:
        await interaction.edit_original_response(content=f"주사위 식을 읽지 못했어요. `1d100+2d6`처럼 입력해 주세요!\n{exc}")


@bot.tree.command(name="주사위", description="주사위를 굴려요! 예: 1d100+2d6")
@app_commands.rename(expression="굴리기")
async def roll_dice(interaction: discord.Interaction, expression: str) -> None:
    await roll_dice_command(interaction, expression, ephemeral=False)


@bot.tree.command(name="비밀주사위", description="주사위 결과를 나에게만 보여줘요! 예: 1d100+2d6")
@app_commands.rename(expression="굴리기")
async def secret_roll_dice(interaction: discord.Interaction, expression: str) -> None:
    await roll_dice_command(interaction, expression, ephemeral=True)


@bot.tree.command(name="운세", description="오늘의 운세")
async def fortune(interaction: discord.Interaction) -> None:
    if random.random() < 0.10:
        message = random.choice(FLAT_FORTUNE_MESSAGES)
        if await send_flat_response(interaction, message):
            return
        await send_response(interaction, message)
        return
    await send_response(interaction, random.choice(FORTUNES))


@bot.tree.command(name="캐릭터등록", description="시트와 캐릭터를 고르고 최대 5명까지 등록해요!")
@app_commands.guild_only()
@app_commands.rename(sheet="시트", character1="캐릭터1", character2="캐릭터2", character3="캐릭터3", character4="캐릭터4", character5="캐릭터5")
@app_commands.autocomplete(sheet=sheet_autocomplete, character1=registration_character_autocomplete, character2=registration_character_autocomplete, character3=registration_character_autocomplete, character4=registration_character_autocomplete, character5=registration_character_autocomplete)
async def register_characters(
    interaction: discord.Interaction,
    sheet: str,
    character1: str,
    character2: str | None = None,
    character3: str | None = None,
    character4: str | None = None,
    character5: str | None = None,
) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        sheets = await registry.get_available_sheets()
        spreadsheet = next((item for item in sheets if item.spreadsheet_id == sheet), None)
        if spreadsheet is None:
            await send_response(interaction, "시트를 목록에서 골라 주세요.", ephemeral=True)
            return
        valid = {value for value, _ in await registry.get_character_tab_choices(sheet)}
        selected = list(dict.fromkeys(value for value in (character1, character2, character3, character4, character5) if value))
        if not selected or any(value not in valid for value in selected):
            await send_response(interaction, "캐릭터는 선택한 시트의 탭 목록에서 골라 주세요. 첫 번째 캐릭터는 꼭 선택해야 해요.", ephemeral=True)
            return
        await registry.add_user_character_selections(interaction.user.id, sheet, selected)
        names = [value.partition("|")[2] for value in selected]
        await send_response(interaction, f"**{spreadsheet.title}**에서 {', '.join(names)} 캐릭터를 등록했어요!", ephemeral=True)
    except SheetError as exc:
        await send_response(interaction, str(exc), ephemeral=True)
    except Exception as exc:
        print(f"Character registration failed ({type(exc).__name__}).")
        await send_response(interaction, "캐릭터를 등록하지 못했어요. 잠시 후 다시 시도해 주세요!", ephemeral=True)


@bot.tree.command(name="캐릭터목록", description="내가 등록한 캐릭터를 보여드려요!")
@app_commands.guild_only()
async def list_characters(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        selected = await registry.get_user_character_selection(interaction.user.id)
        if not selected:
            await send_response(interaction, "아직 등록한 캐릭터가 없어요! `/캐릭터등록`에서 시트와 캐릭터를 골라 주세요.", ephemeral=True)
            return
        selected_set = set(selected)
        sheets = await registry.get_available_sheets()
        lines = []
        for sheet in sheets:
            characters = [tab for tab in sheet.tabs if f"{sheet.spreadsheet_id}|{tab}" in selected_set]
            if characters:
                lines.append(f"**{sheet.title}**\n{', '.join(characters)}")
        message = "\n\n".join(lines)
        if not message:
            message = "등록된 캐릭터를 시트에서 찾지 못했어요. `/캐릭터등록`을 다시 진행해 주세요!"
        await send_response(interaction, message[:1900] + ("…" if len(message) > 1900 else ""), ephemeral=True)
    except SheetError as exc:
        await send_response(interaction, str(exc), ephemeral=True)


@bot.tree.command(name="캐릭터리셋", description="내가 기억해 둔 캐릭터 목록을 비워요!")
@app_commands.guild_only()
async def reset_characters(interaction: discord.Interaction) -> None:
    cleared = await registry.clear_user_character_selections(interaction.user.id)
    message = "기억하고 있던 캐릭터 목록을 비웠어요. 다시 사용하려면 `/캐릭터등록`으로 등록해 주세요!" if cleared else "비울 캐릭터 목록이 없어요."
    await send_response(interaction, message, ephemeral=True)


async def sync_guild_commands(guild: discord.Guild) -> None:
    if guild.id in synced_guilds:
        return
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    synced_guilds.add(guild.id)
    print(f"Registered commands to {guild.name}")


@bot.event
async def on_ready() -> None:
    print(f"{bot.user} is online!")
    try:
        sheets = await registry.get_available_sheets()
        print(f"Loaded {len(sheets)} TRPG spreadsheets.")
    except Exception as exc:
        print(f"TRPG spreadsheet preload failed ({type(exc).__name__}): {exc}")
    for guild in bot.guilds:
        try:
            await sync_guild_commands(guild)
        except Exception as exc:
            print(f"Command registration failed for guild ({type(exc).__name__}).")


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    try:
        await sync_guild_commands(guild)
    except Exception as exc:
        print(f"Command registration failed for new guild ({type(exc).__name__}).")


async def main() -> None:
    token = os.getenv(DISCORD_TOKEN_VARIABLE, "").strip()
    if not token:
        raise RuntimeError(f"{DISCORD_TOKEN_VARIABLE} 환경 변수가 설정되지 않았습니다. 호스팅 환경변수에 봇 토큰을 등록해 주세요.")
    try:
        await bot.start(token)
    finally:
        await registry.close()


kitchen.bind(globals())

if __name__ == "__main__":
    asyncio.run(main())
