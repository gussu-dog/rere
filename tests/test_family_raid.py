import sys
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as m

def fixture():
    ps = [m.CombatParticipant(i, str(i), str(i), f'PC{i}', dexterity=80 - i, strength=60, constitution=60, size=60, hp=80, max_hp=80, spirit=65, sanity=65, starting_sanity=65, magic_points=10, position=0, weapons=[m.CombatWeapon('비무장', '근접전 | 격투', '1d3'), m.CombatWeapon('검', '근접전 | 격투', '2')]) for i in (1, 2, 3)]
    h = m.make_raid_enemy('hunter')
    m.randomize_raid_enemy(h, 3)
    h.hp = h.max_hp
    h.dexterity = 75
    h.strength = 75
    h.size = 70
    h.constitution = 85
    h.position = 2
    h.field_symbol = '◎'
    s = m.CombatSession(1, 20, 1, ps + [h], message=NS(id=1, edit=AsyncMock()), phase='combat', mode='레이드', enemy_id='hunter', turn_order=[0, 1, 2, 3])
    m.combat_sessions[20] = s
    return s

async def check():
    s = fixture()
    h = s.participants[3]
    assert h.max_hp == 30 and h.hp == 30
    h.hp = 7
    h.paralysis_stacks = 1
    s.round_number = 3
    s.turn_index = 3
    m.advance_combat_turn(s)
    b = s.participants[4]
    assert s.round_number == 4 and s.family_spawned and (h.hp == 7) and (h.paralysis_stacks == 1)
    assert b.hp == 8 and b.mana_barrier == 40 and (b.magic_points == 19)
    assert not m.combat_opponents(s, 3, 0) and m.combat_opponents(s, 0, 3) and (m.family_targets(s, h) == [4])
    blade = m.CombatWeapon('정글도', '근접전 | 격투', '1d8')
    dmg, text = m.apply_combat_damage(b, 8, h, weapon=blade)
    assert dmg == 0 and b.hp == 8 and (b.mana_barrier == 24)
    m.apply_combat_damage(b, 1, s.participants[0], weapon=s.participants[0].weapons[0])
    assert b.mana_barrier == 0 and b.hp == 8 and b.barrier_rebuild
    b.mana_barrier = 3
    b.barrier_hits = 0
    m.apply_combat_damage(b, 100, s.participants[0])
    assert b.hp == 8 and b.mana_barrier == 0
    b.mana_barrier = 40
    for kinds in [('충격',), ('지속',), ('마비',)]:
        w = m.CombatWeapon('검사', '주문', '1', effects=[m.CombatStatusSpec(kinds, '건강')])
        m.apply_combat_weapon_statuses(s, s.participants[0], b, w)
    assert not b.status_effects and (not b.paralysis_stacks)
    m.apply_combat_domination(s, m.PendingCombatAttack(0, 4, 0, 50, 1))
    assert b.domination_source is None
    b.mana_barrier = 0
    m.apply_combat_damage(b, 8, h)
    assert b.hp == 0
    assert not await m.finish_combat_if_decided(s) and s.family_revenge and (m.family_targets(s, h) == [0, 1, 2])
    h.hp = 0
    assert await m.finish_combat_if_decided(s)
    assert '레이드 성공' in m.render_combat_winner(s)
    s = fixture()
    s.participants[3].hp = 0
    assert not await m.finish_combat_if_decided(s)
    s = fixture()
    m.spawn_family_mage(s)
    b = s.participants[4]
    for seed in range(100):
        m.random.seed(seed)
        s.family_last_spell = 'barrage'
        s.family_events = [{'kind': 'pit'}]
        key, target = m.choose_family_spell(s, b, m.family_targets(s, b))
        assert key not in {'barrage', 'mark', 'pit'} and target != 4
    print('PASS: delayed spawn preserves hunter state, HP8/barrier40, doubled machete damage, two melee hits, no overflow, status immunity, alliance reversal and two-boss victory, early hunter defeat, AI constraints')

async def simulate():
    for seed in range(12):
        m.random.seed(seed)
        s = fixture()
        s.participants[3].weapons = await m.combat_weapons(s.participants[3])
        steps = 0
        seen = set()

        async def publish(session, view):
            session.message.id += 1

        def interact(user):
            return NS(user=NS(id=user), message=s.message, response=NS(defer=AsyncMock(), send_message=AsyncMock(), edit_message=AsyncMock(), is_done=lambda: True), followup=NS(send=AsyncMock()))
        with patch.object(m, 'publish_combat_panel', publish), patch.object(m, 'refresh_combat_turn_weapons', AsyncMock()), patch.object(m.registry, 'resolve_character_reference', AsyncMock(return_value=None)), patch.object(m.registry, 'get_skill_value', AsyncMock(return_value=65)), patch.object(m.registry, 'get_combat_weapons', AsyncMock(return_value=s.participants[0].weapons)):
            while s.phase == 'combat' and steps < 220:
                steps += 1
                if s.pending_attack:
                    attack = s.pending_attack
                    if attack.family_spell:
                        seen.add(attack.family_spell)
                        await m.resolve_family_spell(s)
                    else:
                        await m.CombatDefenseView(s).resolve_roll('회피')
                else:
                    actor = s.participants[s.turn_index]
                    if actor.enemy_id:
                        await m.repost_combat_turn(s)
                    elif not m.combat_is_active(actor) or m.combat_is_shocked(s, actor) or m.combat_is_controlled(s, s.turn_index):
                        if m.combat_is_shocked(s, actor):
                            for e in m.active_combat_statuses(s, actor)[:]:
                                if '충격' in e.spec.kinds:
                                    await m.attempt_combat_status_escape(s, actor, e)
                            await m.CombatView(s).complete_attack_turn('탈출')
                        else:
                            await m.repost_combat_turn(s)
                    elif not s.family_spawned:
                        await m.CombatView(s).complete_attack_turn('대기')
                    else:
                        targets = [i for i, p in enumerate(s.participants) if p.enemy_id and m.combat_is_active(p)]
                        if not targets:
                            await m.finish_combat_if_decided(s)
                            continue
                        target = next((i for i in targets if s.participants[i].enemy_id == 'mage'), targets[0])
                        m.move_combat_position(s, s.turn_index, target, -1, adjacent=True)
                        await m.CombatView(s).resolve_weapon(interact(actor.user_id), 1, 1, target)
            assert s.phase == 'finished', (seed, steps, s.round_number, s.turn_index, s.pending_attack, [(p.character_name, p.hp, p.madness, p.domination_source, p.mana_barrier, p.position, p.silenced) for p in s.participants], s.recent_logs[-3:])
    print('PASS: 12 seeded full raid simulations reached terminal state with live turn/defense/attack processing')
original_roll = m.roll_combat_d100

async def check_spells():
    for key in m.FAMILY_SPELLS:
        s = fixture()
        m.spawn_family_mage(s)
        s.turn_order = [0, 1, 2, 3, 4]
        s.turn_index = 4
        s.turn_serial = 9
        s.family_last_serial = 9
        mage = s.participants[4]
        mage.mana_barrier = 15
        s.family_ops = [{'kind': 'cast', 'spell': key, 'target': 0}]
        with patch.object(m, 'publish_combat_panel', AsyncMock()), patch.object(m, 'refresh_combat_turn_weapons', AsyncMock()), patch.object(m, 'repost_combat_turn', AsyncMock()), patch.object(m, 'combat_skill_value', AsyncMock(return_value=65)), patch.object(m, 'roll_combat_d100', return_value=(50, [50], 0)):
            await m.take_family_turn(s)
            if key in {'mark', 'pit'}:
                assert s.family_events and s.family_events[0]['due'] == 1
            elif key == 'barrage':
                assert s.pending_attack and len(s.pending_attack.remaining_targets) == 2
            else:
                assert s.pending_attack.family_spell == key
                s.pending_attack.spell_result = '극단적 성공'
                with patch.object(m, 'roll_combat_d100', return_value=(99, [99], 0)):
                    while s.pending_attack and s.pending_attack.family_spell:
                        await m.resolve_family_spell(s)
                pc = s.participants[0]
                if key == 'hold':
                    assert pc.status_effects and m.combat_is_shocked(s, pc)
                    assert not m.maintaining_combat_shock(s, mage)
                    with patch.object(m.random, 'randint', return_value=50):
                        assert original_roll(mage, session=s)[2] == -1
                if key == 'silence':
                    assert pc.silenced
                if key == 'drain':
                    assert pc.magic_points < 10 and mage.mana_barrier > 15
                if key == 'charm':
                    assert pc.domination_source == 4
                if key == 'poison':
                    assert pc.hp < 80 and pc.paralysis_stacks == 1
    s = fixture()
    m.spawn_family_mage(s)
    s.turn_index = 4
    s.turn_serial = 9
    s.participants[4].mana_barrier = 0
    s.participants[4].barrier_rebuild = True
    with patch.object(m, 'publish_combat_panel', AsyncMock()), patch.object(m.CombatView, 'complete_attack_turn', AsyncMock()) as complete, patch.object(m, 'begin_raid_attack', AsyncMock()) as attack, patch.object(m, 'choose_family_spell', return_value=('barrage', 0)):
        await m.take_family_turn(s)
        assert s.participants[4].mana_barrier == 40 and (not s.participants[4].barrier_rebuild)
        complete.assert_not_awaited()
        attack.assert_awaited_once()
    s = fixture()
    m.spawn_family_mage(s)
    s.participants[4].position = 3
    m.move_combat_position(s, 0, 4, -1)
    m.move_combat_position(s, 0, 4, -1)
    assert s.participants[0].position == 2 and m.combat_distance(s, 0, 4) == '근거리'
    print('PASS: all 8 spells, poison resistance/damage, silence, charm, independent shock and caster penalty, drain, warnings, barrage, barrier restoration with same-turn attack, actual one-step movement')
import unittest

class FamilyRaidTests(unittest.TestCase):

    def run_case(self, work):
        with patch.object(m.asyncio, 'sleep', AsyncMock()):
            coroutine = work()
            try:
                coroutine.send(None)
            except StopIteration:
                return
            finally:
                coroutine.close()
                m.combat_sessions.clear()
            self.fail('Unexpected external asynchronous operation')

    def test_phases_barrier_and_ai(self):
        self.run_case(check)

    def test_field_marks_follow_identity_and_expire(self):
        session = fixture()
        m.initialize_combat_field(session)
        session.participants[0].character_name = session.participants[1].character_name = "동명이인"
        session.family_events = [{"kind": "mark", "target": 1, "name": "검은 낙인", "due": 1}]
        field = m.render_combat_field(session)
        self.assertIn("②※", field)
        self.assertNotIn("①※", field)
        session.participants[1].position = 3
        self.assertIn("②※", m.render_combat_field(session).splitlines()[1])
        session.family_events.clear()
        self.assertNotIn("※", m.render_combat_field(session))
        m.combat_sessions.clear()

    def test_complete_battles(self):
        self.run_case(simulate)

    def test_spells_and_movement(self):
        self.run_case(check_spells)
if __name__ == '__main__':
    unittest.main()
