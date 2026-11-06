import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as m
import kitchen_raid as k


def fixture():
    players = [m.CombatParticipant(i, str(i), str(i), f"PC{i}", dexterity=80-i, strength=60, constitution=70, size=60,
                                   hp=80, max_hp=80, sanity=70, starting_sanity=70, spirit=65, magic_points=15,
                                   weapons=[m.CombatWeapon("비무장", "근접전 | 격투", "1d3"), m.CombatWeapon("검", "근접전 | 도검", "1d6")]) for i in (1, 2)]
    dough = m.make_raid_enemy("kitchen")
    m.randomize_raid_enemy(dough, 2)
    dough.hp = dough.max_hp
    dough.weapons = k.weapons(dough)
    s = m.CombatSession(1, 91, 1, players+[dough], message=NS(id=9, edit=AsyncMock()), phase="combat", mode="레이드", enemy_id="kitchen")
    m.initialize_combat_field(s)
    k.initialize(s, 2)
    s.turn_index = 0
    m.combat_sessions[91] = s
    return s


def interaction(session, user=1):
    return NS(user=NS(id=user), message=session.message,
              response=NS(defer=AsyncMock(), send_message=AsyncMock(), edit_message=AsyncMock(), send_modal=AsyncMock(), is_done=lambda: True),
              followup=NS(send=AsyncMock()))


class KitchenRaidTests(unittest.TestCase):
    def run_case(self, work):
        with patch.object(m.asyncio, "sleep", AsyncMock()):
            coroutine = work()
            try:
                coroutine.send(None)
            except StopIteration:
                return
            finally:
                coroutine.close()
                m.combat_sessions.clear()
            self.fail("Unexpected network or event-loop operation")

    def test_progress_overkill_and_zero_quality_completion(self):
        async def check():
            s = fixture()
            self.assertEqual((s.kitchen_state.progress, s.kitchen_state.quality), (0, 100))
            self.assertNotIn(5, m.combat_targets(s))
            dough = s.participants[2]
            m.apply_combat_damage(dough, dough.hp+5, s.participants[0], weapon=s.participants[0].weapons[1])
            self.assertEqual(s.kitchen_state.quality, 95)
            self.assertFalse(await m.finish_combat_if_decided(s))
            self.assertEqual(s.kitchen_state.progress, 25)
            self.assertEqual(k.enemy_kind(s.participants[-1]), "noodle")
            count = len(s.participants)
            await m.finish_combat_if_decided(s)
            self.assertEqual(len(s.participants), count)
            s.kitchen_state.quality = 0
            self.assertFalse(await m.finish_combat_if_decided(s))
            for p in s.participants:
                if k.enemy_kind(p) in {"onion", "shrimp", "noodle"}:
                    p.hp = 0
            self.assertTrue(await m.finish_combat_if_decided(s))
            self.assertTrue(s.kitchen_state.success)
            self.assertEqual(s.kitchen_state.progress, 100)
            self.assertIn("먹을 수 있는지는 별개의 문제", k.ending(s))
        self.run_case(check)

    def test_force_control_succeeds_or_fails_once(self):
        async def check():
            for roll, expected in [(1, True), (99, False)]:
                s = fixture()
                actor = s.participants[0]
                actor.kitchen_control = True
                attack = m.PendingCombatAttack(0, 2, 1, 65, 1)
                with patch.object(m, "roll_combat_d100", return_value=(roll, [roll], 0)) as dice:
                    await k.check_control(s, attack)
                    await k.check_control(s, attack)
                    self.assertEqual(dice.call_count, 1)
                self.assertEqual(attack.kitchen_control, expected)
                self.assertFalse(actor.kitchen_control)
        self.run_case(check)

    def test_damage_choice_is_authorized_and_does_not_reroll(self):
        async def check():
            s = fixture()
            s.participants[2].hp = 3
            s.pending_attack = m.PendingCombatAttack(0, 2, 1, 65, 1, hits=[(40, "보통 성공", 1)], kitchen_control=True, kitchen_checked=True)
            with patch.object(m, "roll_weapon_damage", return_value=(20, "1d20 [20]")) as roll, patch.object(m, "repost_combat_turn", AsyncMock()), patch.object(m, "refresh_combat_turn_weapons", AsyncMock()):
                await m.CombatView(s).apply_incoming_hits()
                view = s.message.edit.call_args.kwargs["view"]
                self.assertIsInstance(view, k.DamageView)
                await m.CombatView(s).complete_attack_turn()
                self.assertEqual(s.turn_index, 0)
                await view.choose(interaction(s, 2), 2)
                self.assertEqual(s.participants[2].hp, 3)
                await view.choose(interaction(s), 2)
                self.assertEqual(s.participants[2].hp, 1)
                self.assertEqual(s.kitchen_state.quality, 100)
                self.assertEqual(roll.call_count, 1)
                await view.choose(interaction(s), 2)
                self.assertEqual(s.participants[2].hp, 1)
                self.assertEqual(s.turn_index, 1)
        self.run_case(check)

    def test_real_weapon_path_checks_strength_before_attack(self):
        async def check():
            for strength_roll, controlled in [(1, True), (99, False)]:
                s = fixture()
                s.participants[0].kitchen_control = True
                s.participants[0].position = 1
                s.participants[2].hp = 3
                rolls = [(strength_roll, [strength_roll], 0), (50, [50], 0), (99, [99], 0)]
                with patch.object(m.registry, "get_skill_value", AsyncMock(return_value=65)), patch.object(m.registry, "resolve_character_reference", AsyncMock(return_value=None)), patch.object(m.random, "randrange", return_value=1), patch.object(m, "roll_combat_d100", side_effect=rolls), patch.object(m, "roll_weapon_damage", return_value=(20, "1d20 [20]")), patch.object(m, "repost_combat_turn", AsyncMock()), patch.object(m, "refresh_combat_turn_weapons", AsyncMock()):
                    await m.CombatView(s).resolve_weapon(interaction(s), 1, 1, 2)
                if controlled:
                    self.assertIsNotNone(s.kitchen_state.damage_choice)
                    self.assertEqual(s.participants[2].hp, 3)
                else:
                    self.assertIsNone(s.kitchen_state.damage_choice)
                    self.assertEqual(s.participants[2].hp, 0)
                    self.assertEqual(s.kitchen_state.quality, 83)
        self.run_case(check)

    def test_multiple_hits_each_get_their_own_damage_choice(self):
        async def check():
            s = fixture()
            target = s.participants[2]
            target.hp = 10
            s.pending_attack = m.PendingCombatAttack(0, 2, 1, 65, 2, hits=[(40, "보통 성공", 1), (40, "보통 성공", 2)], kitchen_control=True, kitchen_checked=True)
            with patch.object(m, "roll_weapon_damage", return_value=(6, "1d6 [6]")) as roll, patch.object(m, "repost_combat_turn", AsyncMock()), patch.object(m, "refresh_combat_turn_weapons", AsyncMock()):
                await m.CombatView(s).apply_incoming_hits()
                await s.message.edit.call_args.kwargs["view"].choose(interaction(s), 3)
                self.assertEqual(target.hp, 7)
                self.assertIsNotNone(s.kitchen_state.damage_choice)
                await s.message.edit.call_args.kwargs["view"].choose(interaction(s), 6)
                self.assertEqual(target.hp, 1)
                self.assertEqual(roll.call_count, 2)
                self.assertEqual(s.turn_index, 1)
        self.run_case(check)

    def test_area_spell_resets_damage_cursor_for_each_ingredient(self):
        async def check():
            s = fixture()
            actor = s.participants[0]
            actor.weapons = [m.CombatWeapon("독안개", "주문", "5", health_resisted_spell=True, area=True)]
            before = [s.participants[i].hp for i in (2, 3, 4)]
            s.pending_attack = m.PendingCombatAttack(0, 2, 0, 65, 1, hits=[(0, "보통 성공", 1)], kitchen_control=True,
                                                    kitchen_checked=True, spell_result="보통 성공", spell_defenses={2: 0, 3: 0, 4: 0}, remaining_targets=[3, 4])
            with patch.object(m, "roll_combat_d100", return_value=(50, [50], 0)), patch.object(m, "repost_combat_turn", AsyncMock()), patch.object(m, "refresh_combat_turn_weapons", AsyncMock()):
                await m.CombatView(s).apply_incoming_hits()
                for _ in range(3):
                    self.assertIsNotNone(s.kitchen_state.damage_choice)
                    await s.message.edit.call_args.kwargs["view"].choose(interaction(s), 1)
            self.assertEqual([s.participants[i].hp for i in (2, 3, 4)], [hp-1 for hp in before])
            self.assertEqual(s.kitchen_state.quality, 100)
            self.assertEqual(s.turn_index, 1)
        self.run_case(check)

    def test_failed_fire_control_allows_next_player_to_retry(self):
        async def check():
            s = fixture()
            s.kitchen_state.pot_warning = True
            with patch.object(m, "roll_combat_d100", side_effect=[(99, [99], 0), (1, [1], 0)]), patch.object(m, "roll_damage_formula", return_value=(3, "1d3 [3]")), patch.object(m, "repost_combat_turn", AsyncMock()), patch.object(m, "refresh_combat_turn_weapons", AsyncMock()):
                await k.use_action(s, interaction(s), "cool:민첩", s.turn_serial)
                self.assertTrue(s.kitchen_state.pot_warning)
                self.assertEqual(s.participants[0].hp, 77)
                self.assertEqual(s.turn_index, 1)
                await k.use_action(s, interaction(s, 2), "cool:민첩", s.turn_serial)
                self.assertFalse(s.kitchen_state.pot_warning)
            self.assertEqual(s.kitchen_state.quality, 100)
        self.run_case(check)

    def test_safe_preparation_and_missing_skill_do_not_damage_quality(self):
        async def check():
            s = fixture()
            s.participants[0].position = 1
            with patch.object(m.registry, "get_skill_value", AsyncMock(return_value=None)):
                await k.use_action(s, interaction(s), "prep:3:예술/공예 | 요리", s.turn_serial)
                self.assertEqual(s.turn_index, 0)
                self.assertEqual(s.participants[3].hp, 8)
            with patch.object(m.registry, "get_skill_value", AsyncMock(return_value=65)), patch.object(m, "roll_combat_d100", return_value=(1, [1], 0)), patch.object(m, "roll_damage_formula", return_value=(8, "1d6+2 [6]+2")), patch.object(m, "repost_combat_turn", AsyncMock()), patch.object(m, "refresh_combat_turn_weapons", AsyncMock()):
                await k.use_action(s, interaction(s), "prep:3:손놀림", s.turn_serial)
            self.assertEqual(s.kitchen_state.quality, 100)
            self.assertIn("onion", s.kitchen_state.completed)
        self.run_case(check)

    def test_noodle_escape_and_single_use_onion_penalty(self):
        async def check():
            for skill, quality in [("손놀림", 100), ("근접전 | 격투", 95)]:
                s = fixture()
                noodle = k.spawn(s, "noodle")
                spec = m.CombatStatusSpec(("충격",), "손놀림")
                weapon = m.CombatWeapon("탈주하는 면발", "근접전 | 격투", "0", effects=[spec])
                m.apply_combat_weapon_statuses(s, noodle, s.participants[0], weapon)
                effect = s.participants[0].status_effects[0]
                select = k.NoodleEscape(s, effect)
                select._values = [skill]
                with patch.object(m.registry, "get_skill_value", AsyncMock(return_value=65)), patch.object(m, "roll_combat_d100", return_value=(1, [1], 0)), patch.object(m, "repost_combat_turn", AsyncMock()), patch.object(m, "refresh_combat_turn_weapons", AsyncMock()):
                    await select.callback(interaction(s))
                self.assertFalse(s.participants[0].status_effects)
                self.assertEqual(s.kitchen_state.quality, quality)
            actor = s.participants[1]
            actor.kitchen_tears = True
            with patch.object(m.random, "randint", return_value=50):
                self.assertEqual(m.roll_combat_d100(actor, session=s)[2], -1)
                self.assertEqual(m.roll_combat_d100(actor, session=s)[2], 0)
        self.run_case(check)

    def test_full_kitchen_battles_reach_an_ending(self):
        async def check():
            for seed in range(12):
                m.random.seed(seed)
                s = fixture()
                async def publish(session, view):
                    session.message.id += 1
                with patch.object(m, "publish_combat_panel", publish), patch.object(m.registry, "resolve_character_reference", AsyncMock(return_value=None)), patch.object(m.registry, "get_skill_value", AsyncMock(return_value=65)), patch.object(m, "refresh_combat_turn_weapons", AsyncMock()):
                    steps = 0
                    while s.phase == "combat" and steps < 400:
                        steps += 1
                        if s.pending_attack:
                            await m.CombatDefenseView(s).resolve_roll("회피")
                            continue
                        actor = s.participants[s.turn_index]
                        if actor.enemy_id or not m.combat_is_active(actor):
                            await m.repost_combat_turn(s)
                        elif m.combat_is_shocked(s, actor):
                            select = k.escape_control(s)
                            select._values = ["손놀림"]
                            await select.callback(interaction(s, actor.user_id))
                        elif s.kitchen_state.pot_warning:
                            await k.use_action(s, interaction(s, actor.user_id), "cool:민첩", s.turn_serial)
                        else:
                            choices = [o.value for o in k.action_options(s) if o.value.startswith("prep:")]
                            if choices:
                                await k.use_action(s, interaction(s, actor.user_id), choices[0], s.turn_serial)
                            else:
                                targets = m.combat_targets(s)
                                if targets:
                                    m.move_combat_position(s, s.turn_index, targets[0], -1)
                                await m.CombatView(s).complete_attack_turn("재료에게 접근")
                    self.assertEqual(s.phase, "finished", (seed, s.round_number, steps))
                    self.assertTrue(s.kitchen_state.finished)
                    self.assertTrue(s.kitchen_state.success or not any(not p.enemy_id and m.combat_is_active(p) for p in s.participants))
        self.run_case(check)

    def test_pot_warning_explosion_and_party_failure(self):
        async def check():
            s = fixture()
            s.turn_index = 5
            with patch.object(m, "publish_combat_panel", AsyncMock()), patch.object(m.CombatView, "complete_attack_turn", AsyncMock()), patch.object(m, "roll_damage_formula", return_value=(4, "1d6 [4]")):
                await k.take_turn(s)
                self.assertTrue(s.kitchen_state.pot_warning)
                s.turn_serial += 1
                await k.take_turn(s)
                self.assertFalse(s.kitchen_state.pot_warning)
                self.assertEqual(s.kitchen_state.quality, 90)
                self.assertEqual(s.participants[0].hp, 76)
                self.assertEqual(s.participants[1].hp, 76)
            for p in s.participants[:2]:
                p.unconscious = True
            self.assertTrue(await m.finish_combat_if_decided(s))
            self.assertFalse(s.kitchen_state.success)
            self.assertIn("주방 대피", k.ending(s))
        self.run_case(check)


if __name__ == "__main__":
    unittest.main()
