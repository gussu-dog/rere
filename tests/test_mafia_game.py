import unittest
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, patch
import mafia_game as m


def fixture(roles):
    return m.Game(10, 1, {i: m.Player(i, f"P{i}", role) for i, role in enumerate(roles, 1)}, phase="밤")


def run(coroutine):
    try:
        coroutine.send(None)
    except StopIteration:
        return
    raise AssertionError("Unexpected asynchronous work")


class MafiaTests(unittest.TestCase):
    def test_all_supported_player_counts_have_required_roles(self):
        for count in range(4, 8):
            game = fixture([""] * count)
            game.start()
            roles = [p.role for p in game.alive()]
            self.assertEqual(roles.count("경찰"), 1)
            self.assertEqual(roles.count("의사"), 1)
            self.assertEqual(sum(role in m.MAFIA for role in roles), 2 if count == 7 else 1)
            self.assertTrue(all(role in m.DESCRIPTIONS for role in roles))
            self.assertEqual(len(set(roles)), count)

    def test_spy_investigation_and_dead_reporter_publication(self):
        game = fixture(["스파이", "경찰", "기자", "의사", "군인", "탐정"])
        game.actions = {1: None, 2: 1, 3: 1, 4: 4, 5: None, 6: 2}
        game.attacks = {1: 3}
        game.resolve_night()
        self.assertIn("시민", game.players[2].inbox[-1])
        self.assertFalse(game.players[3].alive)
        self.assertTrue(game.players[3].used)
        self.assertTrue(any("스파이" in line for line in game.news))
        self.assertIn("P1", game.players[6].inbox[-1])

    def test_hacker_blocks_protection_and_investigation(self):
        game = fixture(["해커", "경찰", "의사", "군인", "탐정", "기자"])
        game.actions = {1: 3, 2: 1, 3: 2}
        game.attacks = {1: 2}
        game.resolve_night()
        self.assertFalse(game.players[2].alive)
        self.assertIn("방해", game.players[3].inbox[-1])
        game = fixture(["해커", "경찰", "의사", "군인", "탐정", "기자"])
        game.actions = {1: 2, 2: 1}
        game.resolve_night()
        self.assertEqual(len(game.players[2].inbox), 1)
        self.assertIn("방해", game.players[2].inbox[0])

    def test_soldier_survives_once_doctor_protects_and_ties_skip(self):
        game = fixture(["마피아", "의사", "군인", "경찰", "기자", "탐정"])
        game.attacks = {1: 3}
        game.resolve_night()
        self.assertTrue(game.players[3].alive)
        game.resolve_night()
        self.assertFalse(game.players[3].alive)
        game.attacks = {1: 4}
        game.actions = {2: 4}
        game.resolve_night()
        self.assertTrue(game.players[4].alive)
        self.assertIsNone(m.unique_most_voted([2, 3]))
        game.votes = {1: 1, 2: 1}
        game.resolve_vote()
        self.assertEqual(game.phase, "종료")
        self.assertIn("시민 진영 승리!", game.news)

    def test_public_controls_phase_flow_and_stale_click(self):
        game = fixture(["마피아", "경찰", "의사", "탐정", "군인", "기자"])
        m.sessions[10] = game
        game.message = S(edit=AsyncMock())
        interaction = S(user=S(id=1), response=S(defer=AsyncMock(), send_message=AsyncMock()))
        with patch.object(m.discord.ui.View, "__init__", return_value=None), patch.object(m.GameView, "add_item"):
            # Pure phase callbacks do not depend on Discord's event loop.
            view = object.__new__(m.GameView)
            view.game = game
            view.revision = 0
            for player in game.alive():
                game.actions[player.player_id] = None
            game.attacks = {1: None}
            with patch.object(m, "refresh", AsyncMock()):
                run(view.callback_for("다음 단계")(interaction))
                self.assertEqual(game.phase, "토론")
                run(view.callback_for("다음 단계")(interaction))
                self.assertEqual(game.phase, "토론")
                view.revision = game.revision
                run(view.callback_for("다음 단계")(interaction))
                self.assertEqual(game.phase, "투표")
                game.votes = {p.player_id: None for p in game.alive()}
                view.revision = game.revision
                run(view.callback_for("다음 단계")(interaction))
                self.assertEqual((game.phase, game.day), ("밤", 2))
                self.assertFalse(game.actions)
                self.assertFalse(game.attacks)
        m.sessions.clear()

    def test_one_owner_controls_multiple_independent_characters(self):
        game = fixture(["마피아", "경찰", "의사", "기자"])
        m.sessions[10] = game
        for player in game.players.values():
            player.owner_id = 99
        game.players[4].owner_id = 100
        interaction = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock()),
                        edit_original_response=AsyncMock())
        with patch.object(m, "refresh", AsyncMock()):
            for actor, target, kind in [(1, 4, "attack"), (2, 1, "action"), (3, 2, "action")]:
                select = m.TargetSelect(game, actor, kind)
                select.game, select.player_id, select.kind = game, actor, kind
                select.revision, select._values = game.revision, [str(target)]
                run(select.callback(interaction))
            self.assertEqual(game.attacks, {1: 4})
            self.assertEqual(game.actions, {2: 1, 3: 2})
            select.player_id = 4
            run(select.callback(interaction))
            self.assertNotIn(4, game.actions)
            self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])
            panel = object.__new__(m.GameView)
            panel.game, panel.revision = game, game.revision
            run(panel.callback_for("내 역할 / 결과", 2)(interaction))
            self.assertIn("경찰", interaction.response.send_message.call_args.args[0])
            run(panel.callback_for("내 역할 / 결과", 4)(interaction))
            self.assertNotIn("기자", interaction.response.send_message.call_args.args[0])
        m.sessions.clear()

    def test_character_registration_is_per_character_and_checks_duplicates(self):
        game = m.Game(10, 99)
        m.sessions[10] = game
        choices = [("sheet|하나", "시트 | 하나"), ("sheet|둘", "시트 | 둘")]
        interaction = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock()),
                        edit_original_response=AsyncMock())
        select = m.CharacterJoinSelect(game, 99, choices, 0)
        select.game, select.owner_id, select.choices = game, 99, choices
        with patch.object(m, "character_registry", S(get_character_choices_for_user=AsyncMock(return_value=choices))), patch.object(m, "refresh", AsyncMock()):
            for index in (0, 1, 0):
                select._values = [str(index)]
                run(select.callback(interaction))
            self.assertEqual(len(game.players), 2)
            self.assertEqual({p.owner_id for p in game.players.values()}, {99})
            self.assertEqual(len({p.player_id for p in game.players.values()}), 2)
            game.phase = "밤"
            select._values = ["1"]
            run(select.callback(interaction))
            self.assertEqual(len(game.players), 2)
        m.sessions.clear()


if __name__ == "__main__":
    unittest.main()
