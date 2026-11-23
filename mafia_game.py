from __future__ import annotations

import asyncio
import random
import traceback
import time
from collections import Counter
from dataclasses import dataclass, field

import discord
from discord import app_commands

MAFIA = {"마피아", "스파이", "해커"}
PHASE_SECONDS = {"밤": 120, "토론": 180, "투표": 60}
DESCRIPTIONS = {
    "마피아": "매일 밤 사격으로 한 명을 공격해요. 접선한 해커가 살아 있으면 공격 판정이 자동 성공해요.",
    "스파이": "경찰에게 시민으로 보여요. 밤 행동으로 한 명에게 접선을 시도해요. 성공한 대상이 마피아면 다음 밤부터 별도 공격과 팀 대화가 가능해요.",
    "해커": "밤 행동으로 접선을 시도하거나 한 명의 능력을 방해해요. 접선 성공 다음 밤부터 살아 있는 동안 마피아의 공격 판정을 자동 성공시켜요.",
    "경찰": "추적·수사과학·관찰력 중 가장 높은 수치로 진영을 조사해요. 스파이는 시민으로 보여요.",
    "의사": "응급처치·의료·의학 중 가장 높은 수치로 한 명을 보호해요. 자신도 선택할 수 있어요.",
    "탐정": "추적·수사과학·관찰력 중 가장 높은 수치로 대상의 밤 행동 대상을 알아내요.",
    "기자": "자료조사로 정확한 역할을 취재해 다음 아침 공개해요. 성공은 게임 중 한 번이고 실패하면 다시 시도할 수 있어요.",
    "군인": "밤 공격에 명중당하면 건강으로 버티기를 판정해요. 성공은 게임 중 한 번 가능해요.",
}
ROLE_SKILLS = {
    "마피아": {"사격"}, "스파이": {"은밀행동"}, "해커": {"자료조사"},
    "경찰": {"추적", "수사과학", "관찰력"}, "의사": {"응급처치", "의료", "의학"},
    "탐정": {"추적", "수사과학", "관찰력"}, "기자": {"자료조사"}, "군인": {"건강"},
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
    skill_values: dict[str, int] = field(default_factory=dict)
    connected_day: int = 0


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
    contact_attempts: set[int] = field(default_factory=set)
    team_messages: dict[int, list[tuple[int, str]]] = field(default_factory=dict)
    team_windows: dict[int, tuple[int, discord.WebhookMessage]] = field(default_factory=dict)
    message: discord.Message | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    deadline: float = 0
    phase_task: asyncio.Task | None = None
    extension_votes: dict[int, bool] | None = None
    extension_round: int = 0
    extension_seconds: int = 0
    extension_notice: str = ""
    private_recipients: dict[int, discord.Interaction] = field(default_factory=dict)
    night_inbox_offsets: dict[int, int] = field(default_factory=dict)

    def alive(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def start(self) -> None:
        count = len(self.players)
        if not 4 <= count <= 7:
            raise ValueError("마피아게임은 4~7명으로 진행해요.")
        mafia_count = 2 if count >= 6 else 1
        roles = ["마피아", "경찰", "의사"]
        if mafia_count == 2:
            roles.append(random.choice(["스파이", "해커"]))
        roles += random.sample(["탐정", "기자", "군인"], count - len(roles))
        random.shuffle(roles)
        for player, role in zip(self.players.values(), roles):
            player.role = role
        self.phase = "밤"
        self.prepare_night()
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

    def team_access(self, player: Player) -> bool:
        return player.alive and (player.role == "마피아" or
            player.role in {"스파이", "해커"} and 0 < player.connected_day <= self.day)

    def can_attack(self, player: Player) -> bool:
        return player.alive and (player.role == "마피아" or player.role == "스파이" and self.team_access(player))

    def needs_night_action(self, player: Player) -> bool:
        return (player.role in {"경찰", "의사", "탐정", "해커"}
                or player.role == "기자" and not player.used
                or player.role == "스파이" and not player.connected_day)

    def prepare_night(self) -> None:
        self.night_inbox_offsets = {p.player_id: len(p.inbox) for p in self.alive()}
        for player in self.alive():
            if not self.needs_night_action(player):
                self.actions.setdefault(player.player_id, None)

    def random_night_target(self, player: Player, kind: str) -> int | None:
        candidates = target_candidates(self, player.player_id, kind)
        target = random.choice(candidates) if candidates else None
        name = self.players[target].name if target is not None else "대상 없음"
        action = {"attack": "공격", "contact": "접선", "action": "능력"}[kind]
        player.inbox.append(f"{self.day}일 밤 · 시간 초과로 {action} 대상을 자동 선택했어요. {name}")
        return target

    def fill_missing_night_choices(self) -> None:
        for player in self.alive():
            if player.player_id not in self.actions:
                if self.needs_night_action(player):
                    kind = "contact" if player.role == "스파이" and not player.connected_day else "action"
                    self.actions[player.player_id] = self.random_night_target(player, kind)
                    if kind == "contact":
                        self.contact_attempts.add(player.player_id)
                else:
                    self.actions[player.player_id] = None
            if self.can_attack(player) and player.player_id not in self.attacks:
                self.attacks[player.player_id] = self.random_night_target(player, "attack")

    def all_choices_ready(self) -> bool:
        if self.phase == "밤":
            return all((not self.needs_night_action(p) or p.player_id in self.actions)
                       and (not self.can_attack(p) or p.player_id in self.attacks) for p in self.alive())
        if self.phase == "투표":
            return all(p.player_id in self.votes for p in self.alive())
        return False

    def success_rate(self, player: Player, *, attack: bool = False) -> int:
        skills = {"사격"} if attack else ROLE_SKILLS[player.role]
        value = max((value for name, value in player.skill_values.items()
                     if any(part.strip() in skills for part in name.replace("(", "|").replace(")", "").split("|"))), default=0)
        return min(90, 30 + max(0, value) * 3 // 5)

    def check(self, player: Player, *, attack: bool = False, automatic: bool = False) -> bool:
        rate = self.success_rate(player, attack=attack)
        if automatic:
            player.inbox.append(f"{self.day}일 밤 · 해커의 조작으로 공격 판정 자동 성공!")
            return True
        roll = random.randint(1, 100)
        success = roll <= rate
        player.inbox.append(f"{self.day}일 밤 · 주사위 [{roll}] / 성공률 {rate}% · {'성공' if success else '실패'}")
        return success

    def resolve_night(self) -> None:
        active = {p.player_id for p in self.alive()}
        actions = {uid: target for uid, target in self.actions.items() if uid in active}
        blocked = {target for uid, target in actions.items()
                   if self.players[uid].role == "해커" and uid not in self.contact_attempts
                   and target is not None and self.check(self.players[uid])}
        for uid in blocked:
            self.players[uid].inbox.append(f"{self.day}일 밤 · 누군가의 방해로 능력을 사용하지 못했어요.")
        protected = set()
        articles = []
        for uid, target in actions.items():
            player = self.players[uid]
            if uid in blocked or target is None or player.role == "해커" and uid not in self.contact_attempts:
                continue
            subject = self.players[target]
            if player.role == "기자" and player.used:
                continue
            if not self.check(player):
                if player.role in {"경찰", "탐정", "기자"}:
                    player.inbox.append(f"{self.day}일 밤 · 실마리를 찾지 못했어요.")
                continue
            if uid in self.contact_attempts:
                if subject.role == "마피아":
                    player.connected_day = self.day + 1
                    player.inbox.append(f"{self.day}일 밤 · {subject.name}와 접선했어요! 다음 밤부터 팀 능력과 대화를 사용할 수 있어요.")
                    subject.inbox.append(f"{self.day}일 밤 · {player.role} {player.name}와 접선했어요! 다음 밤부터 함께할 수 있어요.")
                else:
                    player.inbox.append(f"{self.day}일 밤 · 접선하지 못했어요.")
            elif player.role == "의사":
                protected.add(target)
                player.inbox.append(f"{self.day}일 밤 · {subject.name} 보호에 성공했어요.")
            elif player.role == "경찰":
                result = "마피아" if subject.role in MAFIA - {"스파이"} else "시민"
                player.inbox.append(f"{self.day}일 밤 · {subject.name} 조사 결과는 {result}예요.")
            elif player.role == "탐정":
                visited = actions.get(target)
                if self.can_attack(subject):
                    visited = self.attacks.get(target)
                result = self.players[visited].name if visited is not None else "아무도 없음"
                player.inbox.append(f"{self.day}일 밤 · {subject.name}의 행동 대상은 {result}이에요.")
            elif player.role == "기자":
                player.used = True
                articles.append(f"【기사】 {subject.name}의 역할은 {subject.role}!")
                player.inbox.append(f"{self.day}일 밤 · 취재 성공! {subject.name}의 역할은 {subject.role}이에요.")
        manipulated = any(p.role == "해커" and self.team_access(p) and p.player_id not in blocked for p in self.alive())
        self.news = []
        dead = set()
        for uid, victim in self.attacks.items():
            attacker = self.players[uid]
            if uid not in active or uid in blocked or victim is None or not self.can_attack(attacker):
                continue
            if not self.check(attacker, attack=True, automatic=attacker.role == "마피아" and manipulated):
                continue
            if victim in protected:
                attacker.inbox.append(f"{self.day}일 밤 · {self.players[victim].name} 공격이 보호에 막혔어요.")
                continue
            player = self.players[victim]
            if player.role == "군인" and not player.used and self.check(player):
                player.used = True
                player.inbox.append("군인 능력으로 밤 공격을 한 번 버텼어요.")
                attacker.inbox.append(f"{self.day}일 밤 · {player.name}가 공격을 버텼어요.")
            else:
                dead.add(victim)
                attacker.inbox.append(f"{self.day}일 밤 · {player.name} 공격에 성공했어요.")
        for uid in sorted(dead):
            self.players[uid].alive = False
            self.news.append(f"{self.players[uid].name}님이 밤사이 사망했어요.")
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
        self.contact_attempts.clear()
        self.actions.clear()
        self.attacks.clear()
        self.votes.clear()
        self.prepare_night()
        self.news.append("밤이 됐어요! 밤 행동을 골라 주세요.")

    def render(self) -> str:
        narration = {
            "모집": "마피아게임에 참여할 사람을 모집중이에요!",
            "밤": "밤이 됐어요! 다들 눈을 감고, 자기 역할에 맞는 행동을 골라 주세요!",
            "토론": "아침이 밝았어요! 레레가 밤사이 무슨 일이 있었는지 알려드릴게요!",
            "투표": "이제 투표할 시간이에요! 누가 마피아일지 신중하게 골라 주세요!",
            "종료": "마피아게임이 끝났어요! 다들 수고하셨어요!",
        }
        title = "마피아게임 | 모집 중" if self.phase == "모집" else f"마피아게임 | {self.day}일째 · {self.phase}"
        lines = [title, ""]
        if self.phase == "모집":
            lines.extend([f"참여인원 {len(self.players)}/7", "최소 4명 · 최대 7명"])
        else:
            lines.append(f"생존 {len(self.alive())}/{len(self.players)}")
        if self.phase in PHASE_SECONDS:
            lines.append(f"제한시간 {PHASE_SECONDS[self.phase] // 60}분")
            if self.phase == "토론" and self.extension_seconds:
                lines.append(f"추가 연장 {self.extension_seconds // 60}분")
        if self.phase == "토론" and self.extension_notice:
            lines.append(self.extension_notice)
        for index, player in enumerate(self.players.values(), 1):
            status = ""
            if self.phase == "종료":
                status = f" · {player.role} · {'생존' if player.alive else '탈락'}"
            elif not player.alive:
                status = " · 탈락"
            lines.append(f"{index}. {player.name}{status}")
        if not self.players:
            lines.append("아직 참가한 캐릭터가 없어요.")
        if self.phase == "밤":
            lines.extend(["", f"밤 행동 {len(self.actions)}/{len(self.alive())}"])
        elif self.phase == "투표":
            lines.extend(["", f"투표 완료 {len(self.votes)}/{len(self.alive())}"])
        instructions = {
            "밤이 됐어요! 역할을 확인하고 밤 행동을 골라 주세요.",
            "밤이 됐어요! 밤 행동을 골라 주세요.",
            "토론을 마쳤어요. 투표 버튼으로 한 명을 고르거나 기권해 주세요.",
        }
        events = [line for line in self.news if line not in instructions]
        if events:
            lines.extend(["", "진행 결과", *events])
        guides = {
            "모집": "참여 버튼에서 캐릭터를 골라 주세요. 준비되면 모집자가 시작을 눌러 주세요!",
            "밤": "행동 버튼에서 밤 행동을 골라 주세요! 모두 선택하면 아침이 되고, 시간이 끝나면 미선택 대상은 무작위로 정해요.",
            "토론": "채팅으로 자유롭게 이야기를 나눠 주세요! 시간이 부족하면 토론 연장을 요청할 수 있어요.",
            "투표": "행동 버튼에서 캐릭터마다 한 표씩 골라 주세요! 모두 선택하면 진행하고, 시간이 끝나면 미투표는 기권으로 처리해요.",
        }
        message = narration[self.phase] + "\n\n" + code_box("\n".join(lines))
        if self.phase in guides:
            message += "\n" + guides[self.phase]
        return message


def code_box(text: str) -> str:
    fence = "```"
    return fence + "text\n" + text.replace("`", "") + "\n" + fence


def target_candidates(game: Game, player_id: int, kind: str) -> list[int]:
    return [p.player_id for p in game.alive()
            if kind == "vote" or (kind == "action" and game.players[player_id].role == "의사")
            or (p.player_id != player_id and (kind != "attack" or
                not (game.team_access(game.players[player_id]) and game.team_access(p))))]


def unique_most_voted(values: list[int]) -> int | None:
    counts = Counter(values)
    if not counts:
        return None
    leaders = [uid for uid, count in counts.items() if count == max(counts.values())]
    return leaders[0] if len(leaders) == 1 else None


async def refresh(game: Game, *, repost: bool = False) -> None:
    if not game.message:
        return
    options = dict(content=game.render(), view=GameView(game), allowed_mentions=discord.AllowedMentions.none())
    if not repost:
        await game.message.edit(**options)
        return
    previous = game.message
    try:
        game.message = await previous.channel.send(**options)
    except (discord.HTTPException, OSError) as exc:
        print(f"Mafia panel repost failed ({type(exc).__name__}).", flush=True)
        await previous.edit(**options)
        return
    try:
        await previous.channel.get_partial_message(previous.id).delete()
    except (discord.HTTPException, OSError) as exc:
        print(f"Old mafia panel deletion failed ({type(exc).__name__}).", flush=True)
        try:
            await previous.edit(view=None)
        except (discord.HTTPException, OSError):
            pass


def set_phase_timer(game: Game, *, deadline: float | None = None) -> None:
    previous = game.phase_task
    if previous is not None and previous is not asyncio.current_task():
        previous.cancel()
    game.phase_task = None
    game.deadline = 0
    if game.phase in PHASE_SECONDS:
        game.deadline = deadline if deadline is not None else time.time() + PHASE_SECONDS[game.phase]
        game.phase_task = asyncio.create_task(phase_clock(game, game.revision))


async def phase_clock(game: Game, revision: int) -> None:
    try:
        await asyncio.sleep(max(0, game.deadline - time.time() - 30))
        async with game.lock:
            if sessions.get(game.channel_id) is not game or game.revision != revision:
                return
            if game.message is not None and game.deadline > time.time():
                text = f"{game.phase} 시간이 30초 남았어요!"
                if game.phase == "토론":
                    text += " 슬슬 이야기를 마무리해 주세요!"
                else:
                    text += " 아직 선택하지 않았다면 서둘러 주세요!"
                try:
                    await game.message.channel.send(text, allowed_mentions=discord.AllowedMentions.none())
                except (discord.HTTPException, OSError) as exc:
                    print(f"Mafia timer warning failed ({type(exc).__name__}).", flush=True)
        await asyncio.sleep(max(0, game.deadline - time.time()))
        async with game.lock:
            if sessions.get(game.channel_id) is game and game.revision == revision:
                await finish_phase(game, expired=True)
    except asyncio.CancelledError:
        return
    except Exception as exc:
        print(f"Mafia phase timer failed ({type(exc).__name__}).", flush=True)
        print("".join(traceback.format_tb(exc.__traceback__)), flush=True)


async def send_night_results(game: Game) -> None:
    cards: dict[int, list[str]] = {}
    for actor, offset in game.night_inbox_offsets.items():
        player = game.players[actor]
        details = [player.name, f"{game.day}일째 밤 · 행동 결과"]
        if actor in game.actions and (game.actions[actor] is not None or game.needs_night_action(player)):
            target = game.actions[actor]
            name = game.players[target].name if target is not None else "사용하지 않기"
            kind = "접선" if actor in game.contact_attempts else "능력"
            details.append(f"{kind} 대상 · {name}")
        if actor in game.attacks:
            target = game.attacks[actor]
            name = game.players[target].name if target is not None else "공격하지 않기"
            details.append(f"공격 대상 · {name}")
        results = player.inbox[offset:]
        details.extend(["", *(results or ["이번 밤에는 별도 판정 결과가 없어요."])])
        details.append(f"현재 상태 · {'생존' if player.alive else '탈락'}")
        cards.setdefault(player.owner_id, []).append(code_box("\n".join(details)[:1700]))
    for owner, player_cards in cards.items():
        recipient = game.private_recipients.get(owner)
        if recipient is None:
            continue
        chunks = []
        message = "밤이 끝났어요! 캐릭터들의 행동 결과를 알려드릴게요.\n"
        for card in player_cards:
            if len(message) + len(card) + 2 > 1900:
                chunks.append(message)
                message = ""
            message += "\n" + card
        if message:
            chunks.append(message)
        try:
            for chunk in chunks:
                await recipient.followup.send(chunk, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException, OSError) as exc:
            print(f"Mafia private night results failed ({type(exc).__name__}).", flush=True)


async def finish_phase(game: Game, *, expired: bool = False) -> None:
    phase = game.phase
    if phase == "밤":
        if expired:
            game.fill_missing_night_choices()
        game.resolve_night()
    elif phase == "투표":
        if expired:
            for player in game.alive():
                game.votes.setdefault(player.player_id, None)
        game.resolve_vote()
    elif phase == "토론":
        game.phase = "투표"
        game.revision += 1
        game.news = ["토론을 마쳤어요. 이제 투표해 주세요!"]
    else:
        return
    if expired:
        game.news.insert(0, f"{phase} 제한시간이 끝났어요!")
    game.extension_votes = None
    game.extension_seconds = 0
    game.extension_notice = ""
    set_phase_timer(game)
    await update_team_windows(game)
    if phase == "밤":
        await send_night_results(game)
    try:
        await refresh(game, repost=True)
    finally:
        if game.phase == "종료" and sessions.get(game.channel_id) is game:
            sessions.pop(game.channel_id, None)


async def advance_if_ready(game: Game) -> bool:
    if not game.all_choices_ready():
        return False
    await finish_phase(game)
    return True


class MafiaView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        print(f"Mafia interaction failed ({type(error).__name__}; HTTP {getattr(error, 'status', None)}; code {getattr(error, 'code', None)}).", flush=True)
        print("".join(traceback.format_tb(error.__traceback__)), flush=True)
        message = "마피아게임 처리 중 오류가 났어요. 같은 버튼을 다시 눌러 주세요."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception as notify_error:
            print(f"Mafia error notice failed ({type(notify_error).__name__}).", flush=True)


class TargetSelect(discord.ui.Select):
    def __init__(self, game: Game, player_id: int, kind: str):
        options = [discord.SelectOption(label=game.players[target].name[:100], value=str(target))
                   for target in target_candidates(game, player_id, kind)]
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
            if game.deadline and time.time() >= game.deadline:
                await interaction.response.defer()
                await finish_phase(game, expired=True)
                await interaction.followup.send("선택 시간이 끝나 다음 단계로 넘어갔어요.", ephemeral=True)
                return
            target = None if self.values[0] == "skip" else int(self.values[0])
            if target is not None and not game.players[target].alive:
                await interaction.response.send_message("이미 탈락한 대상이에요.", ephemeral=True)
                return
            await interaction.response.defer()
            game.private_recipients[interaction.user.id] = interaction
            collection = game.votes if self.kind == "vote" else game.attacks if self.kind == "attack" else game.actions
            collection[self.player_id] = target
            if self.kind == "contact":
                game.contact_attempts.add(self.player_id)
            elif self.kind == "action":
                game.contact_attempts.discard(self.player_id)
            name = game.players[target].name if target is not None else "기권"
            await interaction.edit_original_response(content=f"**{discord.utils.escape_markdown(game.players[self.player_id].name)}** 선택 완료!\n> {discord.utils.escape_markdown(name)}", view=None)
            if not await advance_if_ready(game):
                await refresh(game)


class TargetView(MafiaView):
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


class ActorView(MafiaView):
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
            game.private_recipients[interaction.user.id] = interaction
            try:
                await interaction.delete_original_response()
            except (discord.HTTPException, OSError) as exc:
                print(f"Mafia join picker cleanup failed ({type(exc).__name__}).", flush=True)
            await refresh(game)


class CharacterJoinView(MafiaView):
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


def team_chat_text(game: Game, day: int) -> str:
    lines = []
    budget = 1300
    for actor, text in reversed(game.team_messages.get(day, [])):
        entry = f"{game.players[actor].name[:60]}\n{text}"
        if len(entry) > budget:
            break
        lines.insert(0, entry)
        budget -= len(entry) + 2
    content = "\n\n".join(lines) or "아직 나눈 이야기가 없어요."
    return f"{day}일째 밤 · 마피아 팀 대화\n\n" + code_box(content)


def chat_allowed(game: Game, owner_id: int, actor: int, day: int) -> bool:
    player = game.players.get(actor)
    return (sessions.get(game.channel_id) is game and game.phase == "밤" and game.day == day
            and (not game.deadline or time.time() < game.deadline) and player is not None and player.owner_id == owner_id and game.team_access(player))


async def update_team_windows(game: Game) -> None:
    for actor, (day, message) in list(game.team_windows.items()):
        player = game.players[actor]
        opened = chat_allowed(game, player.owner_id, actor, day)
        content = team_chat_text(game, day)
        if not opened:
            content += "\n밤 대화가 끝났어요. 다음 밤에 팀 대화를 다시 열어 주세요!"
        try:
            await message.edit(content=content, view=TeamChatView(game, actor, day) if opened else None,
                               allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException, OSError):
            opened = False
        if not opened:
            game.team_windows.pop(actor, None)


async def open_team_chat(interaction: discord.Interaction, game: Game, actor: int) -> None:
    await interaction.response.defer()
    async with game.lock:
        if not chat_allowed(game, interaction.user.id, actor, game.day):
            await interaction.followup.send("밤에 생존한 마피아와 접선한 동료만 팀 대화를 열 수 있어요.", ephemeral=True)
            return
        game.private_recipients[interaction.user.id] = interaction
        previous = game.team_windows.pop(actor, None)
        if previous:
            try:
                await previous[1].edit(view=None)
            except (discord.HTTPException, OSError):
                pass
        message = await interaction.followup.send(
            team_chat_text(game, game.day), view=TeamChatView(game, actor, game.day),
            ephemeral=True, wait=True, allowed_mentions=discord.AllowedMentions.none(),
        )
        game.team_windows[actor] = (game.day, message)


class TeamMessageModal(discord.ui.Modal, title="팀원에게 전할 이야기"):
    text = discord.ui.TextInput(label="할 말", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, game: Game, actor: int, day: int):
        super().__init__(timeout=None)
        self.game, self.actor, self.day = game, actor, day

    async def on_submit(self, interaction: discord.Interaction) -> None:
        game = self.game
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with game.lock:
            if not chat_allowed(game, interaction.user.id, self.actor, self.day):
                await interaction.edit_original_response(content="지금은 이 캐릭터로 밤 대화를 보낼 수 없어요.")
                return
            text = self.text.value.strip()
            if not text:
                await interaction.edit_original_response(content="전할 이야기를 적어 주세요.")
                return
            messages = game.team_messages.setdefault(self.day, [])
            messages.append((self.actor, text))
            del messages[:-50]
            await update_team_windows(game)
            await interaction.edit_original_response(content="팀원들에게 이야기를 전했어요.")

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        print(f"Mafia team message failed ({type(error).__name__}).", flush=True)
        if interaction.response.is_done():
            await interaction.followup.send("전달 결과를 확인하려면 팀 대화에서 새로고침을 눌러 주세요.", ephemeral=True)
        else:
            await interaction.response.send_message("대화를 보내지 못했어요. 팀 대화에서 다시 시도해 주세요.", ephemeral=True)


class TeamChatView(MafiaView):
    def __init__(self, game: Game, actor: int, day: int):
        super().__init__(timeout=None)
        self.game, self.actor, self.day = game, actor, day

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if chat_allowed(self.game, interaction.user.id, self.actor, self.day):
            return True
        await interaction.response.send_message("현재 사용할 수 없는 팀 대화창이에요.", ephemeral=True)
        return False

    @discord.ui.button(label="메시지 쓰기")
    async def write(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(TeamMessageModal(self.game, self.actor, self.day))

    @discord.ui.button(label="새로고침")
    async def reload(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await open_team_chat(interaction, self.game, self.actor)


def role_details(game: Game, player: Player, *, results: bool = True) -> str:
    details = [player.name, f"역할 · {player.role} · {'생존' if player.alive else '탈락'}",
               f"능력 성공률 {game.success_rate(player)}%"]
    if game.can_attack(player):
        details.append(f"공격 성공률 {game.success_rate(player, attack=True)}%")
    if game.phase == "밤" and not game.needs_night_action(player):
        details.append("별도 밤 행동은 자동으로 대기 처리해요.")
    if results and game.team_access(player):
        partners = ", ".join(p.name for p in game.players.values() if game.team_access(p))
        details.extend(["", f"접선한 동료 · {partners}"])
    if results and player.inbox:
        details.extend(["", "전달받은 정보", *player.inbox[-6:]])
    return "\n".join(details)[:1750]


class CharacterActionView(MafiaView):
    def __init__(self, panel: GameView, player: Player):
        super().__init__(timeout=None)
        self.panel, self.player_id = panel, player.player_id
        game = panel.game
        if game.phase == "투표":
            labels = [("투표", "투표")]
        elif player.role == "스파이" and not player.connected_day:
            labels = [("접선", "접선")]
        else:
            passive = player.role in {"마피아", "군인", "스파이"} or player.role == "기자" and player.used
            labels = [] if passive else [("밤 행동", "밤 행동")]
            if player.role == "해커" and not player.connected_day:
                labels.append(("접선", "접선"))
        if game.phase == "밤" and game.can_attack(player):
            labels.append(("마피아 공격", "마피아 공격"))
        if game.phase == "밤" and game.team_access(player):
            labels.append(("팀 대화", "팀 대화"))
        if len(labels) == 1 and labels[0][1] in {"투표", "밤 행동", "접선"}:
            kind = {"투표": "vote", "밤 행동": "action", "접선": "contact"}[labels[0][1]]
            self.add_item(TargetSelect(game, player.player_id, kind))
            return
        for title, action in labels:
            button = discord.ui.Button(label=title)
            button.callback = panel.callback_for(action, player.player_id)
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        game = self.panel.game
        player = game.players.get(self.player_id)
        if (sessions.get(game.channel_id) is game and game.revision == self.panel.revision
                and game.phase in {"밤", "투표"} and player is not None
                and player.alive and player.owner_id == interaction.user.id):
            return True
        await interaction.response.send_message("지금은 이 행동창을 사용할 수 없어요. 새 진행창의 행동 버튼을 눌러 주세요.", ephemeral=True)
        return False


class GameView(MafiaView):
    def __init__(self, game: Game):
        super().__init__(timeout=None)
        self.game = game
        self.revision = game.revision
        self.extension_round = game.extension_round
        labels = ["참여", "시작", "모집 취소"] if game.phase == "모집" else [
            "내 역할 / 결과", "행동", "게임 종료"]
        if game.phase == "토론":
            labels.insert(2, "토론 마치기")
            labels.insert(3, "토론 연장")
            if game.extension_votes is not None:
                labels.extend(["연장 찬성", "연장 반대"])
        if game.phase == "종료":
            labels = []
        for label in labels:
            button = discord.ui.Button(
                label=label, row=0 if len(self.children) < 4 else 1,
                custom_id=f"mafia:{game.channel_id}:{game.revision}:{game.extension_round}:{label}",
            )
            button.callback = self.callback_for(label)
            if label == "행동":
                button.disabled = game.phase not in {"밤", "투표"}
            elif label == "마피아 공격":
                button.disabled = game.phase != "밤"
            elif label in {"접선", "팀 대화"}:
                button.disabled = game.phase != "밤"
            elif label == "투표":
                button.disabled = game.phase != "투표"
            self.add_item(button)

    async def open_join_picker(self, interaction: discord.Interaction) -> None:
        game = self.game
        print("Mafia join: received; sending private character picker.", flush=True)
        await interaction.response.defer()
        picker_message = await interaction.followup.send(
            "참가할 캐릭터 목록을 불러오고 있어요.",
            ephemeral=True, wait=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        print("Mafia join: loading message sent; reading registered characters.", flush=True)
        try:
            choices = await asyncio.wait_for(
                character_registry.get_character_choices_for_user(interaction.user.id), timeout=15,
            )
            print(f"Mafia join: character list ready ({len(choices)}); updating picker.", flush=True)
            async with game.lock:
                if sessions.get(game.channel_id) is not game or game.phase != "모집":
                    await picker_message.edit(content="이미 종료된 모집이에요.", view=None)
                    return
                if len(game.players) >= 7:
                    await picker_message.edit(content="최대 7캐릭터까지 참가할 수 있어요.", view=None)
                    return
                joined = {p.character_value.casefold() for p in game.players.values()}
                choices = [(value, name) for value, name in choices if value.casefold() not in joined]
                if not choices:
                    await picker_message.edit(
                        content="참가할 캐릭터가 없어요. /캐릭터등록으로 등록해 주세요. 이미 참가한 캐릭터는 목록에서 빠져요.",
                        view=None,
                    )
                    return
                await picker_message.edit(
                    content="참가시킬 캐릭터를 골라 주세요.",
                    view=CharacterJoinView(game, interaction.user.id, choices),
                )
                print("Mafia join: character picker displayed.", flush=True)
        except Exception as exc:
            print(f"Mafia character picker failed ({type(exc).__name__}; HTTP {getattr(exc, 'status', None)}; code {getattr(exc, 'code', None)}).", flush=True)
            print("".join(traceback.format_tb(exc.__traceback__)), flush=True)
            await picker_message.edit(
                content="캐릭터 목록을 불러오지 못했어요. /캐릭터목록에서 등록 상태를 확인한 뒤 참여를 다시 눌러 주세요.",
                view=None,
            )

    def callback_for(self, label: str, player_id: int | None = None):
        async def callback(interaction: discord.Interaction) -> None:
            game = self.game
            if label == "참여":
                await self.open_join_picker(interaction)
                return
            if label == "팀 대화" and player_id is not None:
                await open_team_chat(interaction, game, player_id)
                return
            async with game.lock:
                if sessions.get(game.channel_id) is not game or game.phase == "종료" or self.revision != game.revision:
                    await interaction.response.send_message("이미 종료된 게임이에요.", ephemeral=True)
                    return
                if any(p.owner_id == interaction.user.id for p in game.players.values()):
                    game.private_recipients[interaction.user.id] = interaction
                if label == "내 역할 / 결과" and player_id is None:
                    owned = [p for p in game.players.values() if p.owner_id == interaction.user.id]
                    if not owned or game.phase == "모집":
                        await interaction.response.send_message("참가 캐릭터의 역할은 게임 시작 후 확인할 수 있어요.", ephemeral=True)
                        return
                    await interaction.response.defer()
                    chunks = []
                    current = "맡고 있는 캐릭터들의 역할과 결과를 정리해드릴게요!\n"
                    for member in owned:
                        card = code_box(role_details(game, member))
                        if len(current) + len(card) + 2 > 1900:
                            chunks.append(current)
                            current = ""
                        current += "\n" + card
                    if current:
                        chunks.append(current)
                    for chunk in chunks:
                        await interaction.followup.send(chunk, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                    return
                if label == "행동":
                    owned = [p for p in game.alive() if p.owner_id == interaction.user.id]
                    if not owned or game.phase not in {"밤", "투표"}:
                        await interaction.response.send_message("지금 행동할 수 있는 캐릭터가 없어요.", ephemeral=True)
                        return
                    await interaction.response.defer()
                    for member in owned:
                        await interaction.followup.send(
                            code_box(role_details(game, member, results=False)),
                            view=CharacterActionView(self, member), ephemeral=True,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    return
                player = game.players.get(player_id)
                personal = {"내 역할 / 결과", "밤 행동", "마피아 공격", "투표", "접선", "팀 대화"}
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
                if label in {"시작", "모집 취소", "다음 단계", "토론 마치기", "게임 종료"} and interaction.user.id != game.owner_id:
                    await interaction.response.send_message("모집한 사람만 진행할 수 있어요.", ephemeral=True)
                    return
                if label in {"토론 연장", "연장 찬성", "연장 반대"}:
                    voters = {p.owner_id for p in game.alive()}
                    if (game.phase != "토론" or interaction.user.id not in voters
                            or game.deadline and time.time() >= game.deadline):
                        await interaction.response.send_message("토론 시간 안에 생존 캐릭터를 맡은 참가자만 연장에 참여할 수 있어요.", ephemeral=True)
                        return
                    if game.deadline and time.time() >= game.deadline:
                        await interaction.response.defer()
                        await finish_phase(game, expired=True)
                        return
                    if label == "토론 연장":
                        if game.extension_votes is not None:
                            await interaction.response.send_message("이미 토론 연장에 대한 의견을 모으고 있어요.", ephemeral=True)
                            return
                        game.extension_round += 1
                        game.extension_votes = {interaction.user.id: True}
                    else:
                        if game.extension_votes is None or self.extension_round != game.extension_round:
                            await interaction.response.send_message("이미 종료된 연장 투표예요. 새 진행창을 확인해 주세요.", ephemeral=True)
                            return
                        game.extension_votes[interaction.user.id] = label == "연장 찬성"
                    if not all(game.extension_votes.values()):
                        game.extension_votes = None
                        game.extension_notice = "반대 의견이 있어 토론을 연장하지 않았어요."
                    elif voters <= game.extension_votes.keys():
                        game.extension_votes = None
                        game.extension_seconds += 60
                        deadline = game.deadline or time.time() + PHASE_SECONDS["토론"]
                        game.deadline = deadline + 60
                        set_phase_timer(game, deadline=game.deadline)
                        game.extension_notice = "전원 찬성으로 토론을 1분 연장했어요!"
                    else:
                        game.extension_notice = f"토론 연장 요청 · 찬성 {len(game.extension_votes)}/{len(voters)}명"
                    await interaction.response.defer()
                    await refresh(game)
                    return
                if label == "시작" and game.phase == "모집":
                    if len(game.players) < 4:
                        await interaction.response.send_message("경찰·의사를 포함해 최소 4캐릭터가 필요해요.", ephemeral=True)
                        return
                    await interaction.response.defer()
                    try:
                        data = await asyncio.gather(*(
                            character_registry._get_skill_data(p.character_value) for p in game.players.values()
                        ))
                        if any(item is None for item in data):
                            raise ValueError("Character skill data missing")
                        for member, item in zip(game.players.values(), data):
                            member.skill_values = dict(item.values)
                    except Exception as exc:
                        print(f"Mafia skill load failed ({type(exc).__name__}).", flush=True)
                        await interaction.followup.send("캐릭터 기능치를 읽지 못했어요. 잠시 후 시작을 다시 눌러 주세요.", ephemeral=True)
                        return
                    game.start()
                elif label in {"모집 취소", "게임 종료"}:
                    game.phase = "종료"
                    game.news = ["게임을 종료했어요."]
                elif label == "내 역할 / 결과" and player and game.phase != "모집":
                    text = "이 캐릭터의 역할을 살짝 알려드릴게요!\n\n" + code_box(role_details(game, player))
                    await interaction.response.send_message(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                    return
                elif label in {"밤 행동", "마피아 공격", "투표", "접선"} and player and player.alive:
                    expected = "투표" if label == "투표" else "밤"
                    if game.phase != expected:
                        await interaction.response.send_message("지금은 해당 행동을 할 수 없어요.", ephemeral=True)
                        return
                    if label == "마피아 공격" and not game.can_attack(player):
                        await interaction.response.send_message("마피아 진영만 사용할 수 있어요.", ephemeral=True)
                        return
                    if label == "접선" and (player.role not in {"스파이", "해커"} or player.connected_day):
                        await interaction.response.send_message("아직 접선하지 않은 스파이·해커만 시도할 수 있어요.", ephemeral=True)
                        return
                    if label == "밤 행동" and player.role == "스파이" and not player.connected_day:
                        label_kind = "contact"
                    else:
                        label_kind = "action"
                    if label == "밤 행동" and (player.role in {"군인", "마피아"} or player.role == "스파이" and player.connected_day or player.role == "기자" and player.used):
                        game.actions[player.player_id] = None
                        game.contact_attempts.discard(player.player_id)
                        await interaction.response.send_message("오늘 밤은 별도 능력 없이 기다려요. 마피아 진영은 공격도 선택해 주세요.", ephemeral=True)
                        if not await advance_if_ready(game):
                            await refresh(game)
                        return
                    kind = "vote" if label == "투표" else "attack" if label == "마피아 공격" else "contact" if label == "접선" else label_kind
                    await interaction.response.send_message(f"**{discord.utils.escape_markdown(player.name)} · {label}**\n대상을 골라 주세요. 같은 버튼으로 다시 선택하면 변경할 수 있어요.",
                                                            view=TargetView(game, player.player_id, kind), ephemeral=True)
                    return
                elif label in {"다음 단계", "토론 마치기"}:
                    if game.phase != "토론":
                        await interaction.response.send_message("밤 행동과 투표는 모두 선택하면 자동으로 넘어가요.", ephemeral=True)
                        return
                    await interaction.response.defer()
                    await finish_phase(game)
                    return
                else:
                    await interaction.response.send_message("게임 참가자와 생존 여부를 확인해 주세요.", ephemeral=True)
                    return
                if label != "시작":
                    await interaction.response.defer()
                set_phase_timer(game)
                await update_team_windows(game)
                await refresh(game, repost=True)
                if game.phase == "종료":
                    sessions.pop(game.channel_id, None)
        return callback


def install(bot, registry) -> None:
    global character_registry
    character_registry = registry
    print("Mafia UI loaded: private-character-picker v4.", flush=True)

    async def trace_mafia_button(interaction: discord.Interaction) -> None:
        data = interaction.data or {}
        custom_id = data.get("custom_id", "")
        if isinstance(custom_id, str) and custom_id.startswith("mafia:"):
            print(f"Mafia component received ({custom_id}).", flush=True)

    bot.add_listener(trace_mafia_button, "on_interaction")

    @bot.tree.command(name="마피아게임", description="마피아게임을 모집하거나 직업 설명을 확인해요!")
    @app_commands.guild_only()
    @app_commands.rename(mode="구분")
    @app_commands.choices(mode=[app_commands.Choice(name="모집", value="lobby"),
                               app_commands.Choice(name="직업설명", value="roles")])
    async def mafia_game(interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        if mode.value == "roles":
            lines = ["마피아게임 직업 설명", "기본 성공률 30% + 참조 수치 × 0.6 · 최대 90%", ""]
            for role, description in DESCRIPTIONS.items():
                skills = "캐릭터가 가진 사격 중 최고값" if role == "마피아" else "·".join(sorted(ROLE_SKILLS[role])) + " 중 최고값"
                lines.extend([f"{role} · {skills}", description, ""])
            lines.extend(["접선은 성공한 대상이 마피아일 때 완료돼요. 새 능력과 팀 대화는 다음 밤부터 가능해요.",
                          "밤 2분 · 토론 3분 · 투표 1분. 미선택 밤 행동은 무작위, 미투표는 기권이에요."])
            await interaction.response.send_message(
                "레레가 마피아게임 직업을 설명해드릴게요!\n\n" + code_box("\n".join(lines)),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
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
