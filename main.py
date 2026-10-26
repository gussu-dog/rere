from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
class CachedSkillData:
    values: dict[str, int]
    invested_points: dict[str, int] | None
    emote_key: str | None
    expires_at: float


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
        sheet_skills = list(data.values)
        existing = {skill.casefold() for skill in sheet_skills}
        missing_defaults = [skill for skill in CHECK_DEFAULT_SKILL_VALUES if skill.casefold() not in existing]
        return sorted(missing_defaults, key=str.casefold) + sorted(sheet_skills, key=str.casefold)

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

    async def get_character_emote_name(self, character_value: str, succeeded: bool) -> str | None:
        data = await self._get_skill_data(character_value)
        if not data or not data.emote_key:
            return None
        outcome = "P" if succeeded else "N"
        sheet_marker, separator, character_marker = data.emote_key.partition("_")
        if separator and character_marker:
            return f"{sheet_marker}_{outcome}_{character_marker}"
        return f"{outcome}_{sheet_marker}"

    async def _get_skill_data(self, character_value: str) -> CachedSkillData | None:
        resolved = await self.resolve_character_reference(character_value)
        if resolved is None:
            return None
        spreadsheet_id, tab = resolved
        if not self.api_key:
            raise SheetError(f"{GOOGLE_API_KEY_VARIABLE} 환경 변수를 찾지 못했어요. 호스팅 환경변수에 키를 등록해 주세요!")

        cache_key = f"{spreadsheet_id}|{tab}"
        cached = self._skill_cache.get(cache_key)
        if cached and cached.expires_at > time.monotonic():
            return cached
        lock = self._skill_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._skill_cache.get(cache_key)
            if cached and cached.expires_at > time.monotonic():
                return cached
            escaped_tab = tab.replace("'", "''")
            use_sorted_table = spreadsheet_id == SORTED_TABLE_SPREADSHEET_ID
            ranges = (
                [f"'{escaped_tab}'!A1", f"'{escaped_tab}'!B129:M200", f"'{escaped_tab}'!O21:AL27", f"'{escaped_tab}'!AE12"]
                if use_sorted_table else
                [f"'{escaped_tab}'!A1", f"'{escaped_tab}'!S3:AH7", f"'{escaped_tab}'!C19:N80", f"'{escaped_tab}'!P19:AA80", f"'{escaped_tab}'!AC19:AN80", f"'{escaped_tab}'!AE9"]
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
            cached = CachedSkillData(values, invested_points, emote_key, time.monotonic() + 60)
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
    def _parse_sanity_value(cls, value_ranges: list[dict[str, Any]]) -> int | None:
        if not value_ranges:
            return None
        rows = cls._range_rows(value_ranges, len(value_ranges) - 1)
        return parse_int(rows[0][0]) if rows and rows[0] else None

    @classmethod
    def _parse_skill_values(cls, value_ranges: list[dict[str, Any]]) -> dict[str, int]:
        result: dict[str, int] = {}
        for range_index in range(2, len(value_ranges)):
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
        for range_index in range(2, len(value_ranges)):
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


if __name__ == "__main__":
    asyncio.run(main())
