from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import discord


class MainAPI:
    def __init__(self, namespace: dict[str, Any]):
        self.namespace = namespace

    def __getattr__(self, key: str) -> Any:
        return self.namespace[key]


m: MainAPI


def bind(namespace: dict[str, Any]) -> None:
    global m
    m = MainAPI(namespace)


INGREDIENTS = {
    "dough": ("성난 반죽", 20, 45),
    "noodle": ("탈주하는 면발", 16, 50),
    "onion": ("눈물 많은 양파", 8, 35),
    "shrimp": ("튀어 오르는 새우", 12, 55),
    "pot": ("크림소스 냄비", 1, 30),
}


@dataclass
class KitchenState:
    difficulty: int = 2
    quality: int = 100
    completed: set[str] = field(default_factory=set)
    pot_warning: bool = False
    next_ingredient: str = ""
    pot_warning_round: int = 0
    pot_turns: int = 0
    seasoning: bool = False
    dough_anger: int = 0
    dough_touched: bool = False
    last_serial: int = -1
    damage_choice: Any = None
    success: bool = False
    finished: bool = False
    tasting: list[str] = field(default_factory=list)

    @property
    def progress(self) -> int:
        return len(self.completed) * 25


@dataclass
class DamageChoice:
    attack: Any
    index: int
    raw: int
    detail: str
    avoided: set[int]
    chosen: int | None = None


def enemy_kind(member: Any) -> str:
    if member.enemy_id == "kitchen":
        return "dough"
    return member.enemy_id.removeprefix("kitchen_") if member.enemy_id.startswith("kitchen_") else ""


def is_enemy(member: Any) -> bool:
    return bool(enemy_kind(member))


def configure_enemy(member: Any, difficulty: int) -> None:
    kind = enemy_kind(member)
    name, hp, dex = INGREDIENTS[kind]
    member.character_name = name
    member.enemy_skills = {"dex": dex, "con": 60, "str": 40, "size": 50, "fight": 60, "dodge": 15, "gun": 0, "luck": 50, "pow": 30}
    member.max_hp = hp + (3 * max(0, difficulty - 2) if kind != "pot" else 0)
    member.dexterity, member.strength, member.constitution, member.size = dex, 40, 60, 50


def weapons(member: Any) -> list[Any]:
    return [m.CombatWeapon("비무장 · 재료의 저항", "생체 공격", "1d3")]


def spawn(session: Any, kind: str, position: int = 2) -> Any:
    state = session.kitchen_state
    member = m.CombatParticipant(0, "레레의 주방", "레레의 주방 | " + INGREDIENTS[kind][0], INGREDIENTS[kind][0], enemy_id="kitchen_" + kind)
    configure_enemy(member, state.difficulty)
    member.hp = member.max_hp
    member.weapons = weapons(member)
    member.position = position
    member.field_symbol = {"noodle": "ⓑ", "onion": "ⓒ", "shrimp": "ⓓ", "pot": "♨"}[kind]
    member.kitchen_owner = state
    session.participants.append(member)
    return member


def initialize(session: Any, difficulty: int) -> None:
    session.kitchen_state = KitchenState(difficulty=difficulty)
    dough = next(p for p in session.participants if p.enemy_id == "kitchen")
    dough.kitchen_owner = session.kitchen_state
    dough.field_symbol = "ⓐ"
    session.turn_order = sorted(range(len(session.participants)), key=lambda i: -session.participants[i].dexterity)
    session.turn_index = session.turn_order[0]
    m.append_combat_log(session, "완벽한 식사를 만들 거예요! …재료가 조금 활발하긴 하지만요!")


def begin_intermission(session: Any) -> None:
    state = session.kitchen_state
    if state.next_ingredient or state.progress == 100:
        return
    if any(enemy_kind(p) in {"dough", "noodle", "onion", "shrimp"} and m.combat_is_present(p) for p in session.participants):
        return
    state.next_ingredient = next(kind for kind in ("dough", "noodle", "onion", "shrimp") if kind not in state.completed)
    pot = next((p for p in session.participants if enemy_kind(p) == "pot"), None)
    if pot is None:
        pot = spawn(session, "pot", 3)
    pot.hp = pot.max_hp
    state.pot_warning = True
    state.pot_warning_round = session.round_number
    m.append_combat_log(session, "잠깐! 다음 재료 전에 불부터 줄여주세요! 다음 라운드 냄비 차례까지 민첩·요리로 시도해 주세요.")


def advance_recipe(session: Any) -> None:
    state = session.kitchen_state
    if not state.next_ingredient:
        return
    kind = state.next_ingredient
    state.next_ingredient = ""
    state.pot_warning = False
    for member in session.participants:
        if enemy_kind(member) == "pot":
            member.hp = 0
    spawn(session, kind)
    if kind == "noodle":
        spawn(session, "onion")
    state.seasoning = True
    m.append_combat_log(session, f"다음은 {'탈주하는 면발과 눈물 많은 양파' if kind == 'noodle' else INGREDIENTS[kind][0]} 차례예요! 간 맞추기도 할 수 있어요.")


def status(session: Any) -> str:
    state = session.kitchen_state
    text = f"조리 진행도 {state.progress}% · 재료 상태 {state.quality}점"
    if state.pot_warning:
        text += f"\n♨ 중간 조리 · {state.pot_warning_round + 1}라운드 냄비 차례까지 민첩·요리로 불을 줄이세요!"
    if state.seasoning:
        text += "\n간 맞추기 가능 · 지능 성공 시 재료 상태 회복"
    current = session.participants[session.turn_index]
    if current.kitchen_control:
        text += "\n힘 조절 선택 중 · 다음 공격 전 근력 판정"
    return text


def damage_note(target: Any, damage: int, weapon: Any = None) -> str:
    state = target.kitchen_owner
    kind = enemy_kind(target)
    if state is None or kind == "pot":
        return ""
    overkill = max(0, damage - max(0, target.hp))
    state.quality = max(0, state.quality - overkill)
    if kind == "dough" and damage > 0 and weapon is not None:
        state.dough_touched = True
        state.dough_anger = min(3, state.dough_anger + 1)
    return f" · 재료 상태 -{overkill} → {state.quality}점" if overkill else ""


async def event(session: Any, text: str) -> None:
    await m.show_raid_event(session, text)


def dish_name(score: int) -> str:
    if score >= 80:
        return "레레의 완벽한 해물 크림 파스타"
    if score >= 50:
        return "조금 자유로운 해물 크림 파스타"
    if score > 0:
        return "크림소스에 잠긴 무언가"
    return "먹을 수 있는지는 별개의 문제인 무언가"


def ending(session: Any) -> str:
    state = session.kitchen_state
    if state and state.success:
        title = f"요리 완성!\n{dish_name(state.quality)}\n조리 진행도 100% · 최종 완성도 {state.quality}점"
        line = "완성됐어요! 식기 전에 드셔보세요! …원래 이렇게 움직이는 건가요?"
        taste = "\n" + "\n".join(state.tasting) if state.tasting else ""
        return "```text\n" + title + "\n" + line + taste + "\n```"
    title = "주방 대피! 요리를 계속할 사람이 없어요." if not any(not p.enemy_id and m.combat_is_active(p) for p in session.participants) else "요리를 중단했어요."
    return f"```text\n레레의 완벽한 식사 · 종료\n{title}\n조리 진행도 {state.progress if state else 0}% · 재료 상태 {state.quality if state else 100}점\n```"


async def finish_if_decided(session: Any) -> bool:
    state = session.kitchen_state
    if state is None:
        return False
    for member in session.participants[:]:
        kind = enemy_kind(member)
        if not kind or kind == "pot" or member.hp > 0 or kind in state.completed:
            continue
        state.completed.add(kind)
        m.append_combat_log(session, f"【손질 완료】 {member.character_name} · 조리 진행도 {state.progress}%")
        if kind == "onion":
            for player in session.participants:
                if player.enemy_id or not m.combat_is_active(player):
                    continue
                roll, rolls, modifier = m.roll_combat_d100(player, session=session)
                success = m.combat_success_rank(m.coc_combat_check_result(roll, player.constitution)) > 0
                player.kitchen_tears = not success
                m.append_combat_log(session, f"【양파의 최후】 {player.character_name} · 건강 {m.combat_roll_text(player, roll, rolls, modifier, session=session)} / {player.constitution} · " + ("눈물 참기 성공" if success else "눈물! 다음 판정 패널티 +1"))
    begin_intermission(session)
    session.recent_logs = session.recent_logs[-m.COMBAT_RECENT_LOG_LIMIT:]
    players = [p for p in session.participants if not p.enemy_id and m.combat_is_active(p)]
    if players and state.progress < 100 and not session.annihilated:
        return False
    state.success = bool(players) and state.progress == 100 and not session.annihilated
    state.finished = True
    state.damage_choice = None
    if state.success:
        for player in players:
            roll, rolls, modifier = m.roll_combat_d100(player, session=session)
            success = m.combat_success_rank(m.coc_combat_check_result(roll, player.constitution)) > 0
            state.tasting.append(f"{player.field_symbol} {player.character_name} · 시식 건강 [{roll}] / {player.constitution} · " + ("맛있게 먹었어요!" if success else "조용히 물을 찾습니다."))
    session.phase = "finished"
    session.pending_attack = None
    m.combat_sessions.pop(session.channel_id, None)
    if session.message:
        await session.message.edit(content=ending(session), view=None)
    return True


async def take_turn(session: Any) -> None:
    state = session.kitchen_state
    if state.last_serial == session.turn_serial:
        return
    state.last_serial = session.turn_serial
    actor = session.participants[session.turn_index]
    await m.publish_combat_panel(session, None)
    if m.combat_is_shocked(session, actor):
        for effect in m.active_combat_statuses(session, actor)[:]:
            if "충격" in effect.spec.kinds:
                await m.attempt_combat_status_escape(session, actor, effect)
        await m.CombatView(session).complete_attack_turn("재료가 구속에서 빠져나오려 해요.")
        return
    if m.maintaining_combat_shock(session, actor):
        await m.CombatView(session).complete_attack_turn("면발이 동료를 휘감고 있어요!")
        return
    players = [i for i, p in enumerate(session.participants) if not p.enemy_id and m.combat_is_active(p)]
    if not players:
        await finish_if_decided(session)
        return
    kind = enemy_kind(actor)
    if kind == "pot":
        if state.pot_warning and session.round_number <= state.pot_warning_round:
            await m.CombatView(session).complete_attack_turn("다음 라운드 냄비 차례까지 불을 줄일 수 있어요!")
            return
        state.pot_turns += 1
        if state.pot_warning:
            state.quality = max(0, state.quality - 10)
            state.pot_warning = False
            await event(session, "【냄비 대분출】 재료 상태 -10 · 뜨거운 크림소스가 넘칩니다!")
            for index in players:
                player = session.participants[index]
                raw, detail = m.roll_damage_formula("1d6")
                damage, health = m.apply_combat_damage(player, raw, actor)
                await event(session, f"{detail}\n【국물 화상 · {damage} 피해】 {player.character_name} · {health}")
                await m.check_combat_major_wound(session, player, damage)
        advance_recipe(session)
        await m.CombatView(session).complete_attack_turn("냄비 처리가 끝났어요. 다음 재료를 손질해 주세요!")
        return
    target = random.choice(players)
    if kind == "shrimp":
        actor.pattern_step += 1
        target = max(players, key=lambda i: abs(session.participants[i].position - actor.position))
        if actor.pattern_step % 2:
            actor.position += 1 if actor.position >= session.participants[target].position else -1
            state.quality = max(0, state.quality - 2)
            await event(session, "【새우 탈주】 새우가 펄쩍 뛰어 달아납니다! 재료 상태 -2")
        else:
            await event(session, "새우가 제자리에서 꼬리를 흔듭니다. 지금이 붙잡을 기회예요!")
    if kind == "noodle":
        target = min(players, key=lambda i: abs(session.participants[i].position - actor.position))
        if m.combat_distance(session, session.turn_index, target) == "근거리":
            roll, rolls, modifier = m.roll_combat_d100(actor, session=session, context="attack")
            result = m.coc_combat_check_result(roll, 60)
            await event(session, f"면발 {m.combat_roll_text(actor, roll, rolls, modifier, session=session)} / 60 【{result}】")
            if m.combat_success_rank(result):
                spec = m.CombatStatusSpec(("충격",), "손놀림")
                weapon = m.CombatWeapon("탈주하는 면발", "근접전 | 격투", "0", effects=[spec])
                m.apply_combat_weapon_statuses(session, actor, session.participants[target], weapon)
            await m.CombatView(session).complete_attack_turn("면발이 꿈틀거려요!")
            return
    if kind == "dough":
        if not state.dough_touched:
            state.dough_anger = 0
        state.dough_touched = False
        actor.weapons[0].damage = f"1d3+{state.dough_anger}" if state.dough_anger else "1d3"
        if state.dough_anger:
            await event(session, f"【부푼 반죽】 다음 반죽 공격 피해 +{state.dough_anger}")
    await m.begin_raid_attack(session, session.turn_index, target, 0)


async def check_control(session: Any, attack: Any) -> None:
    if session.enemy_id != "kitchen" or attack.kitchen_checked:
        return
    attack.kitchen_checked = True
    actor = session.participants[attack.attacker_index]
    if actor.enemy_id or not actor.kitchen_control:
        return
    actor.kitchen_control = False
    roll, rolls, modifier = m.roll_combat_d100(actor, session=session)
    result = m.coc_combat_check_result(roll, actor.strength)
    attack.kitchen_control = m.combat_success_rank(result) > 0
    await event(session, f"{actor.character_name} · 힘 조절 근력 {m.combat_roll_text(actor, roll, rolls, modifier, session=session)} / {actor.strength}\n【{result}】 " + ("명중 시 적용 피해를 정할 수 있어요." if attack.kitchen_control else "명중 시 피해가 전부 적용돼요!"))


async def limit_damage(session: Any, attack: Any, index: int, raw: int, detail: str, avoided: set[int]) -> tuple[int, str] | None:
    if session.enemy_id != "kitchen" or not attack.kitchen_control or not is_enemy(session.participants[attack.target_index]):
        return raw, detail
    state = session.kitchen_state
    choice = state.damage_choice
    if choice is None:
        if raw <= 0:
            return raw, detail
        choice = DamageChoice(attack, index, raw, detail, set(avoided))
        state.damage_choice = choice
    if choice.chosen is not None:
        state.damage_choice = None
        return choice.chosen, f"{choice.detail} → 힘 조절 {choice.chosen}"
    target = session.participants[attack.target_index]
    session.briefing = f"힘 조절 성공! {target.field_symbol} {target.character_name} · HP {target.hp}\n굴린 피해 {choice.detail} = {choice.raw} · 적용할 피해를 선택해 주세요."
    await session.message.edit(content=m.render_combat_session(session), view=DamageView(session, choice))
    return None


class KitchenView(discord.ui.View):
    def __init__(self, session: Any):
        super().__init__(timeout=None)
        self.session = session
        self.serial = session.turn_serial
        self.attack = session.pending_attack

    async def valid(self, interaction: discord.Interaction, user: int | None = None) -> bool:
        s = self.session
        if (m.combat_sessions.get(s.channel_id) is not s or s.phase != "combat" or s.turn_serial != self.serial
                or s.pending_attack is not self.attack or interaction.message.id != s.message.id):
            await interaction.response.send_message("이미 처리된 선택이에요. 현재 화면을 확인해 주세요.", ephemeral=True)
            return False
        actor = s.participants[s.turn_index]
        if interaction.user.id != (user if user is not None else m.combat_actor_user(s, actor)):
            await interaction.response.send_message("현재 차례인 캐릭터만 선택할 수 있어요.", ephemeral=True)
            return False
        return True


class DamageModal(discord.ui.Modal, title="적용할 피해"):
    amount = discord.ui.TextInput(label="0부터 굴린 피해까지", max_length=8)

    def __init__(self, view: DamageView):
        super().__init__()
        self.owner = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            amount = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message("적용할 피해를 정수로 입력해 주세요.", ephemeral=True)
            return
        await self.owner.choose(interaction, amount)


class DamageView(KitchenView):
    def __init__(self, session: Any, choice: DamageChoice):
        super().__init__(session)
        self.choice = choice

    async def choose(self, interaction: discord.Interaction, amount: int) -> None:
        async with self.session.lock:
            actor = self.session.participants[self.choice.attack.attacker_index]
            if not await self.valid(interaction, m.combat_actor_user(self.session, actor)):
                return
            if self.session.kitchen_state.damage_choice is not self.choice or self.choice.chosen is not None:
                await interaction.response.send_message("이미 피해를 선택했어요.", ephemeral=True)
                return
            if not 0 <= amount <= self.choice.raw:
                await interaction.response.send_message(f"0부터 {self.choice.raw}까지 입력해 주세요.", ephemeral=True)
                return
            await interaction.response.defer()
            self.choice.chosen = amount
            await m.CombatView(self.session).apply_incoming_hits(self.choice.avoided)
            await m.CombatView(self.session).complete_attack_turn("힘 조절 피해가 적용됐어요.")

    @discord.ui.button(label="초과 피해 없이", style=discord.ButtonStyle.primary)
    async def safe(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.choose(interaction, min(self.choice.raw, self.session.participants[self.choice.attack.target_index].hp))

    @discord.ui.button(label="직접 입력", style=discord.ButtonStyle.secondary)
    async def custom(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self.valid(interaction, m.combat_actor_user(self.session, self.session.participants[self.choice.attack.attacker_index])):
            await interaction.response.send_modal(DamageModal(self))

    @discord.ui.button(label="전부 적용", style=discord.ButtonStyle.danger)
    async def full(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.choose(interaction, self.choice.raw)


def action_options(session: Any) -> list[discord.SelectOption]:
    state = session.kitchen_state
    current = session.participants[session.turn_index]
    options = [discord.SelectOption(label="힘 조절 취소" if current.kitchen_control else "다음 공격 힘 조절", value="control", description="공격 전 근력 판정 · 성공하면 적용 피해 선택")]
    for i, target in enumerate(session.participants):
        kind = enemy_kind(target)
        if kind not in {"dough", "noodle", "onion", "shrimp"} or not m.combat_is_active(target) or m.combat_distance(session, session.turn_index, i) != "근거리":
            continue
        skills = ["민첩", "예술/공예 | 요리"] if kind == "shrimp" else ["손놀림", "예술/공예 | 요리"]
        for skill in skills:
            options.append(discord.SelectOption(label=f"{target.field_symbol} {target.character_name} 손질 · {skill}"[:100], value=f"prep:{i}:{skill}", description="성공 시 초과 피해 없이 1d6+2 손질 · 턴 종료"))
    if state.pot_warning:
        for skill in ("민첩", "예술/공예 | 요리"):
            options.append(discord.SelectOption(label=f"불 줄이기 · {skill}", value=f"cool:{skill}", description="실패하면 1d3 화상 · 다른 동료 재시도 가능"))
    if state.seasoning:
        options.append(discord.SelectOption(label="간 맞추기 · 지능", value="season", description="성공 재료 상태 +8 · 실패 -6 · 턴 종료"))
    return options


class KitchenActions(discord.ui.Select):
    def __init__(self, session: Any):
        super().__init__(placeholder="주방에서 할 행동", options=action_options(session), row=3)
        self.session = session
        self.serial = session.turn_serial

    async def callback(self, interaction: discord.Interaction) -> None:
        await use_action(self.session, interaction, self.values[0], self.serial)


async def skill_value(actor: Any, skill: str) -> int | None:
    if skill == "민첩":
        return actor.dexterity
    return await m.combat_skill_value(actor, skill)


async def use_action(session: Any, interaction: discord.Interaction, value: str, serial: int) -> None:
    async with session.lock:
        check = KitchenView(session)
        check.serial = serial
        if not await check.valid(interaction):
            return
        actor = session.participants[session.turn_index]
        if session.pending_attack is not None or m.combat_is_shocked(session, actor) or m.pending_combat_status_check(session, actor):
            await interaction.response.send_message("먼저 현재 판정과 상태 처리를 끝내 주세요.", ephemeral=True)
            return
        if actor.madness == "도주":
            await interaction.response.send_message("도주 중에는 거리 넓히기만 가능해요.", ephemeral=True)
            return
        state = session.kitchen_state
        if value == "control":
            actor.kitchen_control = not actor.kitchen_control
            await interaction.response.edit_message(content=m.render_combat_session(session), view=m.CombatView(session))
            return
        if m.maintaining_combat_shock(session, actor):
            await interaction.response.send_message("구속을 유지하는 동안에는 다른 행동을 할 수 없어요.", ephemeral=True)
            return
        valid = {option.value for option in action_options(session)}
        if value not in valid:
            await interaction.response.send_message("현재 가능한 주방 행동을 다시 선택해 주세요.", ephemeral=True)
            return
        parts = value.split(":")
        skill = "지능" if value == "season" else parts[-1]
        if value.startswith("prep:"):
            target = session.participants[int(parts[1])]
        else:
            target = next(p for p in session.participants if enemy_kind(p) == "pot")
        try:
            score = await skill_value(actor, skill)
            if score is None:
                raise ValueError("시트에 기능치가 없어요.")
        except Exception:
            await interaction.response.send_message(f"시트에서 {skill} 값을 읽지 못했어요. 다른 기능을 고르거나 다시 시도해 주세요. 턴은 소모하지 않았어요.", ephemeral=True)
            return
        await interaction.response.defer()
        roll, rolls, modifier = m.roll_combat_d100(actor, session=session)
        result = m.coc_combat_check_result(roll, score)
        success = m.combat_success_rank(result) > 0
        await event(session, f"{actor.character_name} · {skill} {m.combat_roll_text(actor, roll, rolls, modifier, session=session)} / {score} 【{result}】")
        if value == "season":
            state.seasoning = False
            state.quality = min(100, state.quality + 8) if success else max(0, state.quality - 6)
            await event(session, f"【간 맞추기】 재료 상태 {state.quality}점 · " + ("좋은 향이 나요!" if success else "…설탕이었나 봐요!"))
        elif value.startswith("cool:") and success:
            state.pot_warning = False
            advance_recipe(session)
            await event(session, "【불 줄이기 성공】 냄비가 얌전해졌어요! 다음 재료를 준비해 주세요.")
        elif value.startswith("prep:") and success:
            raw, detail = m.roll_damage_formula("1d6+2")
            damage, health = m.apply_combat_damage(target, min(raw, target.hp), actor)
            await event(session, f"손질 {detail}\n【안전한 손질 · {damage}】 {target.character_name} · {health}")
        else:
            if value.startswith("prep:"):
                state.quality = max(0, state.quality - 3)
            raw, detail = m.roll_damage_formula("1d3")
            damage, health = m.apply_combat_damage(actor, raw, target)
            await event(session, f"{detail}\n【{'뜨거워요!' if value.startswith('cool:') else '재료의 반격!'} · {damage} 피해】 {actor.character_name} · {health}")
            await m.check_combat_major_wound(session, actor, damage)
        await m.CombatView(session).complete_attack_turn("주방 일을 마쳤어요.")


class NoodleEscape(discord.ui.Select):
    def __init__(self, session: Any, effect: Any):
        super().__init__(placeholder="면발에서 벗어나기", options=[discord.SelectOption(label="손놀림으로 풀기", value="손놀림"), discord.SelectOption(label="근접전으로 뜯기", value="근접전 | 격투", description="성공하면 빠르게 해제 · 재료 상태 -5")])
        self.session = session
        self.effect = effect
        self.serial = session.turn_serial

    async def callback(self, interaction: discord.Interaction) -> None:
        session = self.session
        async with session.lock:
            check = KitchenView(session)
            check.serial = self.serial
            if not await check.valid(interaction):
                return
            actor = session.participants[session.turn_index]
            if self.effect not in m.active_combat_statuses(session, actor):
                await interaction.response.send_message("이미 면발이 풀렸어요.", ephemeral=True)
                return
            skill = self.values[0]
            try:
                score = await skill_value(actor, skill)
                if score is None:
                    raise ValueError("탈출 기능치를 읽지 못했어요.")
            except Exception:
                await interaction.response.send_message("탈출 기능치를 읽지 못했어요. 다시 시도해 주세요.", ephemeral=True)
                return
            await interaction.response.defer()
            roll, rolls, modifier = m.roll_combat_d100(actor, session=session)
            result = m.coc_combat_check_result(roll, score)
            if m.combat_success_rank(result):
                actor.status_effects.remove(self.effect)
                if skill != "손놀림":
                    session.kitchen_state.quality = max(0, session.kitchen_state.quality - 5)
            await event(session, f"【면발 탈출 · {result}】 {actor.character_name} · {skill} [{roll}] / {score}")
            await m.CombatView(session).complete_attack_turn("면발에서 빠져나오려 했어요.")


def escape_control(session: Any) -> Any:
    actor = session.participants[session.turn_index]
    effects = m.active_combat_statuses(session, actor)
    if len(effects) == 1 and effects[0].weapon.name == "탈주하는 면발":
        return NoodleEscape(session, effects[0])
    return m.CombatStatusEscapeSelect(session)
