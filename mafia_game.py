from __future__ import annotations

import asyncio
import random
from collections import Counter
from dataclasses import dataclass, field

import discord
from discord import app_commands

MAFIA = {"마피아", "스파이", "해커"}
DESCRIPTIONS = {
    "마피아": "밤마다 공격 대상을 골라요. 마피아 진영의 최다 지목 대상을 공격하며, 동률이면 공격하지 않아요.",
    "스파이": "마피아 진영이에요. 경찰 조사에는 시민으로 나와요. 밤에는 마피아와 함께 공격 대상을 골라요.",
    "해커": "마피아 진영이에요. 밤마다 한 명의 능력을 막고, 공격 대상도 골라요.",
    "경찰": "매일 밤 한 명이 마피아 진영인지 조사해요. 스파이는 시민으로 나와요.",
    "의사": "매일 밤 한 명을 공격으로부터 보호해요. 자신도 보호할 수 있어요.",
    "탐정": "매일 밤 한 명이 누구에게 밤 능력을 사용했는지 확인해요.",
    "기자": "게임 중 한 번, 한 명의 정확한 역할을 다음 아침 모두에게 공개해요. 취재했다면 죽어도 기사는 나와요.",
    "군인": "마피아의 밤 공격을 한 번 버텨요. 낮의 투표에는 적용되지 않아요.",
}
sessions: dict[int, Game] = {}
character_registry = None


@dataclass
class Player:
    player_id: int
    name: str
    role: str = ""
    alive: bool = True
    used: bool = False
    inbox: list[str] = field(default_factory=list)
    owner_id: int = 0
    character_value: str = ""


@dataclass
class Game:
    channel_id: int
    owner_id: int
    players: dict[int, Player] = field(default_factory=dict)
    phase: str = "모집"
    day: int = 1
    revision: int = 0
    actions: dict[int, int | None] = field(default_factory=dict)
    attacks: dict[int, int | None] = field(default_factory=dict)
    votes: dict[int, int | None] = field(default_factory=dict)
    news: list[str] = field(default_factory=list)
    message: discord.Message | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def alive(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def start(self) -> None:
        count = len(self.players)
        if not 4 <= count <= 7:
            raise ValueError("마피아게임은 4~7명으로 진행해요.")
        mafia_count = 2 if count == 7 else 1
        roles = random.sample(sorted(MAFIA), mafia_count) + ["경찰", "의사"]
        roles += random.sample(["탐정", "기자", "군인"], count - len(roles))
        random.shuffle(roles)
        for player, role in zip(self.players.values(), roles):
            player.role = role
        self.phase = "밤"
        self.revision += 1
        self.news = ["밤이 됐어요! 역할을 확인하고 밤 행동을 골라 주세요."]

    def winner(self) -> str:
        alive = self.alive()
        mafia = sum(p.role in MAFIA for p in alive)
        if not mafia:
            return "시민 진영 승리!"
        if mafia >= len(alive) - mafia:
            return "마피아 진영 승리!"
        return ""

    def finish_if_decided(self) -> bool:
        outcome = self.winner()
        if not outcome:
            return False
        self.phase = "종료"
        self.news.append(outcome)
        return True

    def resolve_night(self) -> None:
        blocked = {target for uid, target in self.actions.items()
                   if self.players[uid].role == "해커" and target is not None}
        for uid in blocked:
            self.players[uid].inbox.append(f"{self.day}일 밤 · 누군가의 방해로 능력을 사용하지 못했어요.")
        protected = {target for uid, target in self.actions.items()
                     if uid not in blocked and self.players[uid].role == "의사"}
        articles = []
        for uid, target in self.actions.items():
            player = self.players[uid]
            if uid in blocked or target is None:
                continue
            subject = self.players[target]
            if player.role == "경찰":
                result = "마피아" if subject.role in MAFIA - {"스파이"} else "시민"
                player.inbox.append(f"{self.day}일 밤 · {subject.name} 조사 결과는 {result}예요.")
            elif player.role == "탐정":
                visited = self.actions.get(target)
                if subject.role in MAFIA:
                    visited = self.attacks.get(target)
                result = self.players[visited].name if visited is not None else "아무도 없음"
                player.inbox.append(f"{self.day}일 밤 · {subject.name}의 행동 대상은 {result}이에요.")
            elif player.role == "기자" and not player.used:
                player.used = True
                articles.append(f"【기사】 {subject.name}의 역할은 {subject.role}!")
        ballots = [target for uid, target in self.attacks.items() if uid not in blocked and target is not None]
        victim = unique_most_voted(ballots)
        self.news = []
        if victim is not None and victim not in protected:
            player = self.players[victim]
            if player.role == "군인" and not player.used:
                player.used = True
                player.inbox.append("군인 능력으로 밤 공격을 한 번 버텼어요.")
            else:
                player.alive = False
                self.news.append(f"{player.name}님이 밤사이 사망했어요.")
        if not self.news:
            self.news.append("오늘 밤에는 아무도 사망하지 않았어요.")
        self.news.extend(articles)
        self.phase = "토론"
        self.revision += 1
        self.finish_if_decided()

    def resolve_vote(self) -> None:
        victim = unique_most_voted([v for v in self.votes.values() if v is not None])
        self.news = []
        if victim is None:
            self.news.append("최다 득표가 동률이거나 모두 기권해서 처형하지 않았어요.")
        else:
            self.players[victim].alive = False
            self.news.append(f"{self.players[victim].name}님이 투표로 처형됐어요.")
        self.revision += 1
        if self.finish_if_decided():
            return
        self.day += 1
        self.phase = "밤"
        self.actions.clear()
        self.attacks.clear()
        self.votes.clear()
        self.news.append("밤이 됐어요! 밤 행동을 골라 주세요.")

    def render(self) -> str:
        lines = [f"## 마피아게임",
                 f"**{self.day}일째 · {self.phase}**", "━━━━━━━━━━━━"]
        if self.phase == "모집":
            lines.append(f"### 참가 캐릭터 · {len(self.players)}/7")
        else:
            lines.append(f"### 참가 캐릭터 · 생존 {len(self.alive())}/{len(self.players)}")
        for player in self.players.values():
            name = discord.utils.escape_markdown(player.name)
            if self.phase == "종료":
                lines.append(f"- **{name}** · {player.role} · {'생존' if player.alive else '탈락'}")
            elif player.alive:
                lines.append(f"- **{name}**")
            else:
                lines.append(f"- ~~{name}~~ · 탈락")
        if not self.players:
            lines.append("아직 참가한 캐릭터가 없어요.")
        if self.phase == "밤":
            attack_count = sum(p.player_id in self.attacks for p in self.alive() if p.role in MAFIA)
            mafia_count = sum(p.role in MAFIA for p in self.alive())
            lines.append(f"\n**밤 행동** {len(self.actions)}/{len(self.alive())} · **공격 선택** {attack_count}/{mafia_count}")
        elif self.phase == "투표":
            lines.append(f"\n**투표 완료** {len(self.votes)}/{len(self.alive())}")
        lines.append("\n━━━━━━━━━━━━")
        lines.extend(f"> {discord.utils.escape_markdown(line)}" for line in self.news)
        guides = {
            "모집": "**참여**로 캐릭터를 골라 주세요! 4캐릭터 이상 모이면 모집자가 **시작**을 눌러요.",
            "밤": "**내 역할 / 결과**에서 역할을 확인하고 **밤 행동**을 골라 주세요. 마피아 진영은 **마피아 공격**도 선택해요.",
            "토론": "캐릭터끼리 이야기를 나눠 주세요. 토론이 끝나면 모집자가 **다음 단계**를 눌러요.",
            "투표": "**투표**에서 캐릭터별로 한 표씩 골라 주세요. 전원 완료 후 모집자가 **다음 단계**를 눌러요.",
        }
        if self.phase in guides:
            lines.append(f"\n{guides[self.phase]}")
        return "\n".join(lines)


def unique_most_voted(values: list[int]) -> int | None:
    counts = Counter(values)
    if not counts:
        return None
    leaders = [uid for uid, count in counts.items() if count == max(counts.values())]
    return leaders[0] if len(leaders) == 1 else None


async def refresh(game: Game) -> None:
    if game.message:
        await game.message.edit(content=game.render(), view=GameView(game), allowed_mentions=discord.AllowedMentions.none())


class TargetSelect(discord.ui.Select):
    def __init__(self, game: Game, player_id: int, kind: str):
        options = [discord.SelectOption(label=p.name[:100], value=str(p.player_id))
                   for p in game.alive()
                   if kind == "vote" or (kind == "action" and game.players[player_id].role == "의사")
                   or (p.player_id != player_id and (kind != "attack" or p.role not in MAFIA))]
        options.append(discord.SelectOption(label="사용하지 않기 / 기권", value="skip"))
        super().__init__(placeholder="대상을 골라 주세요", options=options)
        self.game, self.player_id, self.kind = game, player_id, kind
        self.revision = game.revision

    async def callback(self, interaction: discord.Interaction) -> None:
        game = self.game
        async with game.lock:
            valid_phase = "투표" if self.kind == "vote" else "밤"
            if (interaction.user.id != game.players[self.player_id].owner_id or game.phase != valid_phase
                    or game.revision != self.revision or sessions.get(game.channel_id) is not game
                    or not game.players[self.player_id].alive):
                await interaction.response.send_message("현재 사용할 수 없는 선택창이에요.", ephemeral=True)
                return
            target = None if self.values[0] == "skip" else int(self.values[0])
            if target is not None and not game.players[target].alive:
                await interaction.response.send_message("이미 탈락한 대상이에요.", ephemeral=True)
                return
            await interaction.response.defer()
            collection = game.votes if self.kind == "vote" else game.attacks if self.kind == "attack" else game.actions
            collection[self.player_id] = target
            name = game.players[target].name if target is not None else "기권"
            await interaction.edit_original_response(content=f"**{discord.utils.escape_markdown(game.players[self.player_id].name)}** 선택 완료!\n> {discord.utils.escape_markdown(name)}", view=None)
            await refresh(game)


class TargetView(discord.ui.View):
    def __init__(self, game: Game, player_id: int, kind: str):
        super().__init__(timeout=None)
        self.add_item(TargetSelect(game, player_id, kind))


class ActorSelect(discord.ui.Select):
    def __init__(self, panel: GameView, label: str, players: list[Player]):
        super().__init__(placeholder="조종할 캐릭터", options=[
            discord.SelectOption(label=p.name[:100], value=str(p.player_id)) for p in players])
        self.panel = panel
        self.action = label

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.panel.callback_for(self.action, int(self.values[0]))(interaction)


class ActorView(discord.ui.View):
    def __init__(self, panel: GameView, label: str, players: list[Player]):
        super().__init__(timeout=None)
        self.add_item(ActorSelect(panel, label, players))


class CharacterJoinSelect(discord.ui.Select):
    def __init__(self, game: Game, owner_id: int, choices: list[tuple[str, str]], page: int):
        start = page * 25
        super().__init__(placeholder="참가시킬 캐릭터", options=[
            discord.SelectOption(label=name[:100], value=str(index))
            for index, (value, name) in enumerate(choices[start:start + 25], start)])
        self.game, self.owner_id, self.choices = game, owner_id, choices

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("본인의 캐릭터 선택창을 이용해 주세요.", ephemeral=True)
            return
        await interaction.response.defer()
        value, name = self.choices[int(self.values[0])]
        owned = await character_registry.get_character_choices_for_user(self.owner_id)
        if value not in {item[0] for item in owned}:
            await interaction.edit_original_response(content="현재 등록된 캐릭터를 다시 선택해 주세요.", view=None)
            return
        game = self.game
        async with game.lock:
            if sessions.get(game.channel_id) is not game or game.phase != "모집":
                await interaction.edit_original_response(content="이미 종료된 모집이에요.", view=None)
                return
            if len(game.players) >= 7 or any(p.character_value.casefold() == value.casefold() for p in game.players.values()):
                await interaction.edit_original_response(content="이미 참가했거나 모집 정원이 찼어요.", view=None)
                return
            player_id = max(game.players, default=0) + 1
            game.players[player_id] = Player(player_id, name, owner_id=self.owner_id, character_value=value)
            await interaction.edit_original_response(content=f"**{discord.utils.escape_markdown(name)}** 참가 완료!", view=None)
            await refresh(game)


class CharacterJoinView(discord.ui.View):
    def __init__(self, game: Game, owner_id: int, choices: list[tuple[str, str]], page: int = 0):
        super().__init__(timeout=None)
        self.add_item(CharacterJoinSelect(game, owner_id, choices, page))
        for step, label in [(-1, "이전"), (1, "다음")]:
            next_page = page + step
            if 0 <= next_page < (len(choices) + 24) // 25:
                button = discord.ui.Button(label=label, row=1)
                async def change_page(interaction: discord.Interaction, target: int = next_page) -> None:
                    if interaction.user.id != owner_id:
                        await interaction.response.send_message("본인의 선택창을 이용해 주세요.", ephemeral=True)
                        return
                    await interaction.response.edit_message(view=CharacterJoinView(game, owner_id, choices, target))
                button.callback = change_page
                self.add_item(button)


class GameView(discord.ui.View):
    def __init__(self, game: Game):
        super().__init__(timeout=None)
        self.game = game
        self.revision = game.revision
        labels = ["참여", "시작", "모집 취소"] if game.phase == "모집" else [
            "내 역할 / 결과", "밤 행동", "마피아 공격", "투표", "다음 단계", "게임 종료"]
        if game.phase == "종료":
            labels = []
        for label in labels:
            button = discord.ui.Button(label=label, row=0 if len(self.children) < 3 else 1)
            button.callback = self.callback_for(label)
            if label == "밤 행동":
                button.disabled = game.phase != "밤"
            elif label == "마피아 공격":
                button.disabled = game.phase != "밤"
            elif label == "투표":
                button.disabled = game.phase != "투표"
            self.add_item(button)

    def callback_for(self, label: str, player_id: int | None = None):
        async def callback(interaction: discord.Interaction) -> None:
            game = self.game
            async with game.lock:
                if sessions.get(game.channel_id) is not game or game.phase == "종료" or self.revision != game.revision:
                    await interaction.response.send_message("이미 종료된 게임이에요.", ephemeral=True)
                    return
                player = game.players.get(player_id)
                personal = {"내 역할 / 결과", "밤 행동", "마피아 공격", "투표"}
                if label in personal and player_id is None:
                    owned = [p for p in game.players.values() if p.owner_id == interaction.user.id
                             and (label == "내 역할 / 결과" or p.alive)]
                    if not owned:
                        await interaction.response.send_message("이 행동을 할 수 있는 참가 캐릭터가 없어요.", ephemeral=True)
                        return
                    await interaction.response.send_message("어느 캐릭터로 진행할까요?",
                                                            view=ActorView(self, label, owned), ephemeral=True)
                    return
                if label in personal and (player is None or player.owner_id != interaction.user.id):
                    await interaction.response.send_message("본인이 참가시킨 캐릭터만 조종할 수 있어요.", ephemeral=True)
                    return
                if label in {"시작", "모집 취소", "다음 단계", "게임 종료"} and interaction.user.id != game.owner_id:
                    await interaction.response.send_message("모집한 사람만 진행할 수 있어요.", ephemeral=True)
                    return
                if label == "참여" and game.phase == "모집":
                    if len(game.players) >= 7:
                        await interaction.response.send_message("최대 7캐릭터까지 참가할 수 있어요.", ephemeral=True)
                        return
                    await interaction.response.defer(ephemeral=True, thinking=True)
                    choices = await character_registry.get_character_choices_for_user(interaction.user.id)
                    joined = {p.character_value.casefold() for p in game.players.values()}
                    choices = [(value, name) for value, name in choices if value.casefold() not in joined]
                    if not choices:
                        await interaction.followup.send("참가할 캐릭터가 없어요. /캐릭터등록으로 먼저 등록해 주세요.", ephemeral=True)
                        return
                    await interaction.followup.send("참가시킬 캐릭터를 골라 주세요.",
                                                    view=CharacterJoinView(game, interaction.user.id, choices), ephemeral=True)
                    return
                elif label == "시작" and game.phase == "모집":
                    if len(game.players) < 4:
                        await interaction.response.send_message("경찰·의사를 포함해 최소 4캐릭터가 필요해요.", ephemeral=True)
                        return
                    game.start()
                elif label in {"모집 취소", "게임 종료"}:
                    game.phase = "종료"
                    game.news = ["게임을 종료했어요."]
                elif label == "내 역할 / 결과" and player and game.phase != "모집":
                    partners = ", ".join(discord.utils.escape_markdown(p.name) for p in game.players.values() if p.role in MAFIA)
                    text = f"## {discord.utils.escape_markdown(player.name)}\n**역할 · {player.role}**\n> {DESCRIPTIONS[player.role]}"
                    if player.role in MAFIA:
                        text += f"\n마피아 진영 구성원 · {partners}"
                    if player.inbox:
                        text += "\n\n### 전달받은 정보\n" + "\n".join(f"> {discord.utils.escape_markdown(result)}" for result in player.inbox[-6:])
                    await interaction.response.send_message(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                    return
                elif label in {"밤 행동", "마피아 공격", "투표"} and player and player.alive:
                    expected = "투표" if label == "투표" else "밤"
                    if game.phase != expected:
                        await interaction.response.send_message("지금은 해당 행동을 할 수 없어요.", ephemeral=True)
                        return
                    if label == "마피아 공격" and player.role not in MAFIA:
                        await interaction.response.send_message("마피아 진영만 사용할 수 있어요.", ephemeral=True)
                        return
                    if label == "밤 행동" and (player.role in {"군인", "마피아", "스파이"} or player.role == "기자" and player.used):
                        game.actions[player.player_id] = None
                        await interaction.response.send_message("오늘 밤은 별도 능력 없이 기다려요. 마피아 진영은 공격도 선택해 주세요.", ephemeral=True)
                        await refresh(game)
                        return
                    kind = "vote" if label == "투표" else "attack" if label == "마피아 공격" else "action"
                    await interaction.response.send_message(f"**{discord.utils.escape_markdown(player.name)} · {label}**\n대상을 골라 주세요. 같은 버튼으로 다시 선택하면 변경할 수 있어요.",
                                                            view=TargetView(game, player.player_id, kind), ephemeral=True)
                    return
                elif label == "다음 단계":
                    if game.phase == "밤":
                        if any(p.player_id not in game.actions or p.role in MAFIA and p.player_id not in game.attacks for p in game.alive()):
                            await interaction.response.send_message("모두 밤 행동을 확인해야 해요. 마피아 진영은 공격도 선택해야 해요.", ephemeral=True)
                            return
                        game.resolve_night()
                    elif game.phase == "토론":
                        game.phase = "투표"
                        game.revision += 1
                        game.news = ["토론을 마쳤어요. 투표 버튼으로 한 명을 고르거나 기권해 주세요."]
                    elif game.phase == "투표":
                        if any(p.player_id not in game.votes for p in game.alive()):
                            await interaction.response.send_message("모두 투표해야 해요. 기권도 선택할 수 있어요.", ephemeral=True)
                            return
                        game.resolve_vote()
                    else:
                        await interaction.response.send_message("먼저 게임을 시작해 주세요.", ephemeral=True)
                        return
                else:
                    await interaction.response.send_message("게임 참가자와 생존 여부를 확인해 주세요.", ephemeral=True)
                    return
                await interaction.response.defer()
                await refresh(game)
                if game.phase == "종료":
                    sessions.pop(game.channel_id, None)
        return callback


def install(bot, registry) -> None:
    global character_registry
    character_registry = registry
    @bot.tree.command(name="마피아게임", description="캐릭터 4~7명으로 마피아게임을 진행해요! 한 사람이 여러 캐릭터로 참가할 수 있어요.")
    @app_commands.guild_only()
    async def mafia_game(interaction: discord.Interaction) -> None:
        existing = sessions.get(interaction.channel_id)
        if existing:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await refresh(existing)
            await interaction.followup.send("진행 중인 마피아게임 안내를 갱신했어요.", ephemeral=True)
            return
        game = Game(interaction.channel_id, interaction.user.id)
        sessions[game.channel_id] = game
        try:
            await interaction.response.send_message(game.render(), view=GameView(game))
            game.message = await interaction.original_response()
        except Exception:
            sessions.pop(game.channel_id, None)
            raise
