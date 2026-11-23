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
    def setUp(self):
        rolls = patch.object(m.random, "randint", return_value=1)
        rolls.start()
        self.addCleanup(rolls.stop)
        self.addCleanup(m.sessions.clear)
        timers = patch.object(m, "set_phase_timer")
        timers.start()
        self.addCleanup(timers.stop)

    def test_all_supported_player_counts_have_required_roles(self):
        for count in range(4, 8):
            game = fixture([""] * count)
            game.start()
            roles = [p.role for p in game.alive()]
            self.assertEqual(roles.count("마피아"), 1)
            self.assertEqual(roles.count("경찰"), 1)
            self.assertEqual(roles.count("의사"), 1)
            self.assertEqual(sum(role in m.MAFIA for role in roles), 2 if count >= 6 else 1)
            self.assertTrue(all(role in m.DESCRIPTIONS for role in roles))
            self.assertEqual(len(set(roles)), count)

    def test_spy_investigation_and_dead_reporter_publication(self):
        game = fixture(["스파이", "경찰", "기자", "의사", "마피아", "탐정"])
        game.actions = {1: None, 2: 1, 3: 1, 4: 4, 5: None, 6: 2}
        game.attacks = {5: 3}
        game.resolve_night()
        self.assertIn("시민", game.players[2].inbox[-1])
        self.assertFalse(game.players[3].alive)
        self.assertTrue(game.players[3].used)
        self.assertTrue(any("스파이" in line for line in game.news))
        self.assertIn("P1", game.players[6].inbox[-1])

    def test_hacker_blocks_protection_and_investigation(self):
        game = fixture(["해커", "경찰", "의사", "마피아", "탐정", "기자"])
        game.actions = {1: 3, 2: 1, 3: 2}
        game.attacks = {4: 2}
        game.resolve_night()
        self.assertFalse(game.players[2].alive)
        self.assertIn("방해", game.players[3].inbox[-1])
        game = fixture(["해커", "경찰", "의사", "마피아", "탐정", "기자"])
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
        self.assertEqual(game.phase, "최후변론")
        game.execution_votes = {p.player_id: True for p in game.alive() if p.player_id != game.nominee}
        game.resolve_execution()
        self.assertEqual(game.phase, "종료")
        self.assertIn("시민 진영 승리!", game.news)

    def test_public_controls_phase_flow_and_stale_click(self):
        game = fixture(["마피아", "경찰", "의사", "탐정", "군인", "기자"])
        m.sessions[10] = game
        game.message = S(edit=AsyncMock())
        interaction = S(user=S(id=1), response=S(defer=AsyncMock(), send_message=AsyncMock()))
        view = m.GameView(game)
        with patch.object(m, "refresh", AsyncMock()):
            run(view.callback_for("다음 단계")(interaction))
            self.assertEqual(game.phase, "밤")
            for player in game.alive():
                game.actions[player.player_id] = None
            game.attacks = {1: None}
            run(m.advance_if_ready(game))
            self.assertEqual(game.phase, "토론")
            run(view.callback_for("토론 마치기")(interaction))
            self.assertEqual(game.phase, "토론")
            game.players[1].owner_id = game.players[2].owner_id = 1
            for player in game.alive():
                player.owner_id = 1
            view = m.GameView(game)
            run(view.callback_for("토론 단축")(interaction))
            self.assertEqual(game.phase, "투표")
            game.votes = {p.player_id: None for p in game.alive()}
            run(m.advance_if_ready(game))
            self.assertEqual((game.phase, game.day), ("밤", 2))
            self.assertEqual(game.actions, {1: None})
            self.assertFalse(game.attacks)

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
            self.assertIn("P2", interaction.response.send_message.call_args.args[0])
            self.assertNotIn("경찰", interaction.response.send_message.call_args.args[0])
            run(panel.callback_for("내 역할 / 결과", 4)(interaction))
            self.assertNotIn("기자", interaction.response.send_message.call_args.args[0])
        m.sessions.clear()

    def test_character_registration_is_per_character_and_checks_duplicates(self):
        game = m.Game(10, 99)
        m.sessions[10] = game
        choices = [("sheet|하나", "시트 | 하나"), ("sheet|둘", "시트 | 둘")]
        interaction = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock()),
                        edit_original_response=AsyncMock(), delete_original_response=AsyncMock())
        select = m.CharacterJoinSelect(game, 99, choices, 0)
        select.game, select.owner_id, select.choices = game, 99, choices
        outsider = S(user=S(id=100), response=S(send_message=AsyncMock()))
        run(select.callback(outsider))
        self.assertFalse(game.players)
        self.assertTrue(outsider.response.send_message.call_args.kwargs["ephemeral"])
        with patch.object(m, "character_registry", S(get_character_choices_for_user=AsyncMock(return_value=choices))), patch.object(m, "refresh", AsyncMock()):
            for index in (0, 1, 0):
                select._values = [str(index)]
                run(select.callback(interaction))
            self.assertEqual(interaction.delete_original_response.await_count, 2)
            self.assertEqual(len(game.players), 2)
            self.assertEqual({p.owner_id for p in game.players.values()}, {99})
            self.assertEqual(len({p.player_id for p in game.players.values()}), 2)
            game.phase = "밤"
            select._values = ["1"]
            run(select.callback(interaction))
            self.assertEqual(len(game.players), 2)
        m.sessions.clear()

    def test_participation_posts_private_picker_and_reports_lookup_errors(self):
        game = m.Game(10, 99)
        m.sessions[10] = game
        panel = object.__new__(m.GameView)
        panel.game, panel.revision = game, 0
        picker_message = S(edit=AsyncMock())
        interaction = S(user=S(id=99), response=S(defer=AsyncMock()),
                        followup=S(send=AsyncMock(return_value=picker_message)))
        async def immediate(awaitable, timeout):
            self.assertFalse(game.lock.locked())
            return await awaitable
        choices = [("sheet|one", "one")]
        with patch.object(m.asyncio, "wait_for", immediate), patch.object(m, "CharacterJoinView", return_value="picker"), patch.object(m, "character_registry", S(get_character_choices_for_user=AsyncMock(return_value=choices))):
            run(panel.callback_for("참여")(interaction))
            self.assertEqual(picker_message.edit.call_args.kwargs["view"], "picker")
            self.assertTrue(interaction.followup.send.call_args.kwargs["ephemeral"])
            self.assertTrue(interaction.followup.send.call_args.kwargs["wait"])
            self.assertEqual(len(game.players), 0)
        with patch.object(m.asyncio, "wait_for", immediate), patch.object(m, "character_registry", S(get_character_choices_for_user=AsyncMock(side_effect=TimeoutError))):
            run(panel.callback_for("참여")(interaction))
            self.assertIsNone(picker_message.edit.call_args.kwargs["view"])
            self.assertIn("불러오지 못", picker_message.edit.call_args.kwargs["content"])
        with patch.object(m.asyncio, "wait_for", immediate), patch.object(m, "character_registry", S(get_character_choices_for_user=AsyncMock(return_value=[]))):
            run(panel.callback_for("참여")(interaction))
            self.assertIn("참가할 캐릭터가 없", picker_message.edit.call_args.kwargs["content"])
        m.sessions.clear()

    def test_skill_rates_and_attack_uses_best_firearm(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        for value, expected in [(0, 30), (20, 42), (50, 60), (80, 78), (100, 90), (150, 90)]:
            game.players[1].skill_values = {"사격 | 권총": value, "사격 | 라/산": 0}
            self.assertEqual(game.success_rate(game.players[1], attack=True), expected)
        game.players[1].skill_values = {"사격 | 권총": 40, "사격 | 라/산": 80}
        self.assertEqual(game.success_rate(game.players[1], attack=True), 78)
        game.players[3].skill_values = {"응급처치": 30, "의료": 70}
        self.assertEqual(game.success_rate(game.players[3]), 72)
        game.players[2].skill_values = {"과학 | 수사과학": 80, "추적": 20, "관찰력": 50}
        self.assertEqual(game.success_rate(game.players[2]), 78)
        with patch.object(m.random, "randint", return_value=79):
            self.assertFalse(game.check(game.players[2]))

    def test_contact_is_hidden_until_success_and_starts_next_night(self):
        game = fixture(["마피아", "스파이", "의사", "경찰", "군인", "탐정"])
        self.assertFalse(game.team_access(game.players[2]))
        self.assertFalse(game.can_attack(game.players[2]))
        options = m.TargetSelect(game, 1, "attack").options
        self.assertIn("2", [o.value for o in options])
        game.actions = {2: 1}
        game.contact_attempts = {2}
        game.resolve_night()
        self.assertEqual(game.players[2].connected_day, 2)
        self.assertIn("스파이", game.players[1].inbox[-1])
        self.assertFalse(game.team_access(game.players[2]))
        game.day, game.phase = 2, "밤"
        self.assertTrue(game.team_access(game.players[2]))
        self.assertTrue(game.can_attack(game.players[2]))
        self.assertNotIn("2", [o.value for o in m.TargetSelect(game, 1, "attack").options])
        game.attacks = {1: 3, 2: 4}
        game.actions.clear()
        game.resolve_night()
        self.assertFalse(game.players[3].alive)
        self.assertFalse(game.players[4].alive)

    def test_hacker_guarantees_only_mafia_roll_and_protection_still_works(self):
        game = fixture(["마피아", "해커", "의사", "군인", "경찰", "탐정"])
        game.players[2].connected_day = 1
        game.attacks = {1: 5}
        with patch.object(m.random, "randint", return_value=100):
            game.resolve_night()
        self.assertFalse(game.players[5].alive)
        self.assertTrue(any("자동 성공" in item for item in game.players[1].inbox))
        game = fixture(["마피아", "해커", "의사", "군인", "경찰", "탐정"])
        game.players[2].connected_day = 1
        game.actions = {3: 5}
        game.attacks = {1: 5}
        game.resolve_night()
        self.assertTrue(game.players[5].alive)

    def test_team_chat_private_access_modal_broadcast_and_morning_closure(self):
        game = fixture(["마피아", "스파이", "해커", "경찰", "의사", "군인"])
        m.sessions[10] = game
        for player in game.players.values():
            player.owner_id = player.player_id + 100
        game.players[2].connected_day = 1
        windows = [S(edit=AsyncMock(), delete=AsyncMock()) for _ in range(2)]
        def interaction(actor, window):
            return S(user=S(id=game.players[actor].owner_id),
                     response=S(defer=AsyncMock(), send_message=AsyncMock(), send_modal=AsyncMock()),
                     followup=S(send=AsyncMock(return_value=window)),
                     edit_original_response=AsyncMock())
        first, second = interaction(1, windows[0]), interaction(2, windows[1])
        panel = m.GameView(game)
        run(panel.callback_for("팀 대화", 1)(first))
        run(m.open_team_chat(second, game, 2))
        self.assertTrue(first.followup.send.call_args.kwargs["ephemeral"])
        self.assertEqual(len(game.team_windows), 2)
        outsider = interaction(3, S(edit=AsyncMock()))
        run(m.open_team_chat(outsider, game, 3))
        self.assertEqual(len(game.team_windows), 2)
        self.assertNotIn("view", outsider.followup.send.call_args.kwargs)
        chat_view = first.followup.send.call_args.kwargs["view"]
        run(chat_view.write.callback(first))
        modal = first.response.send_modal.call_args.args[0]
        modal.text._value = "이번에는 P4를 노릴게."
        run(modal.on_submit(first))
        for receiver in (first, second):
            text = receiver.followup.send.call_args.args[0]
            self.assertIn("P1", text)
            self.assertIn("P4", text)
            self.assertTrue(receiver.followup.send.call_args.kwargs["ephemeral"])
        for window in windows:
            window.delete.assert_awaited_once()
        self.assertEqual(game.team_messages[1], [(1, "이번에는 P4를 노릴게.")])
        run(modal.on_submit(outsider))
        self.assertEqual(len(game.team_messages[1]), 1)
        game.phase = "토론"
        run(m.update_team_windows(game))
        self.assertFalse(game.team_windows)
        self.assertTrue(all(window.edit.call_args.kwargs["view"] is None for window in windows))
        run(modal.on_submit(first))
        self.assertEqual(len(game.team_messages[1]), 1)
        game.phase, game.day = "밤", 2
        self.assertFalse(m.chat_allowed(game, first.user.id, 1, 1))

    def test_expired_chat_window_does_not_stop_other_updates(self):
        game = fixture(["마피아", "스파이", "경찰", "의사"])
        m.sessions[10] = game
        game.players[2].connected_day = 1
        stale = S(edit=AsyncMock(side_effect=OSError))
        live = S(edit=AsyncMock())
        game.team_windows = {1: (1, stale), 2: (1, live)}
        run(m.update_team_windows(game))
        self.assertNotIn(1, game.team_windows)
        self.assertIn(2, game.team_windows)
        live.edit.assert_awaited_once()

    def test_public_panel_has_only_generic_actions_and_private_buttons_match_roles(self):
        game = fixture(["마피아", "경찰", "의사", "스파이", "해커", "군인"])
        m.sessions[10] = game
        panel = m.GameView(game)
        self.assertEqual([b.label for b in panel.children], ["내 단서 / 결과", "행동", "게임 종료"])
        self.assertNotIn("공격 선택", game.render())
        mafia = m.CharacterActionView(panel, game.players[1]).children
        citizen = m.CharacterActionView(panel, game.players[2]).children
        spy = m.CharacterActionView(panel, game.players[4]).children
        hacker = m.CharacterActionView(panel, game.players[5]).children
        self.assertEqual(len(mafia), 1)
        self.assertIsInstance(mafia[0], m.TargetSelect)
        self.assertEqual(mafia[0].kind, "hidden")
        self.assertEqual(len(citizen), 1)
        self.assertIsInstance(citizen[0], m.TargetSelect)
        self.assertEqual(citizen[0].kind, "hidden")
        self.assertEqual(len(spy), 1)
        self.assertIsInstance(spy[0], m.TargetSelect)
        self.assertEqual(spy[0].kind, "hidden")
        self.assertEqual(len(hacker), 1)
        self.assertEqual(hacker[0].kind, "hidden")
        game.players[4].connected_day = 1
        self.assertEqual(m.CharacterActionView(panel, game.players[4]).children[0].kind, "hidden")
        self.assertIn("팀 대화", [getattr(b, "label", None) for b in m.CharacterActionView(panel, game.players[1]).children])
        self.assertIn("팀 대화", [getattr(b, "label", None) for b in m.CharacterActionView(panel, game.players[4]).children])
        game.players[4].alive = False
        self.assertEqual(m.CharacterActionView(panel, game.players[1]).children[0].kind, "hidden")
        game.players[4].alive = True
        game.phase = "투표"
        self.assertEqual(m.CharacterActionView(panel, game.players[1]).children[0].kind, "vote")

    def test_role_summary_and_action_cards_include_all_owned_characters_privately(self):
        game = fixture(["마피아", "경찰", "의사", "기자"])
        m.sessions[10] = game
        game.players[1].owner_id = game.players[2].owner_id = 99
        game.players[3].owner_id = game.players[4].owner_id = 100
        panel = m.GameView(game)
        interaction = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock()),
                        followup=S(send=AsyncMock()))
        run(panel.callback_for("내 역할 / 결과")(interaction))
        messages = interaction.followup.send.call_args_list
        summary = "".join(call.args[0] for call in messages)
        self.assertIn("P1", summary)
        self.assertIn("P2", summary)
        self.assertNotIn("P3", summary)
        self.assertTrue(all(call.kwargs["ephemeral"] for call in messages))
        self.assertTrue(all(len(call.args[0]) <= 1900 for call in messages))
        interaction.followup.send.reset_mock()
        run(panel.callback_for("행동")(interaction))
        self.assertEqual(interaction.followup.send.await_count, 2)
        self.assertTrue(all(call.kwargs["ephemeral"] for call in interaction.followup.send.call_args_list))
        cards = interaction.followup.send.call_args_list
        self.assertEqual(cards[0].kwargs["view"].children[0].kind, "hidden")
        self.assertNotIn("마피아 공격", [getattr(b, "label", None) for b in cards[1].kwargs["view"].children])
        game.revision += 1
        run(cards[0].kwargs["view"].interaction_check(interaction))
        self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])

    def test_phase_repost_sends_new_panel_before_deleting_old(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        events = []
        new = S()
        deletion = S(delete=AsyncMock(side_effect=lambda: events.append("delete")))
        channel = S(send=AsyncMock(side_effect=lambda **kwargs: events.append("send") or new),
                    get_partial_message=lambda message_id: deletion)
        previous = S(channel=channel, id=22, edit=AsyncMock())
        game.message = previous
        run(m.refresh(game, repost=True))
        self.assertIs(game.message, new)
        self.assertEqual(events, ["send", "delete"])
        self.assertIsInstance(channel.send.call_args.kwargs["view"], m.GameView)
        channel.send = AsyncMock(side_effect=OSError)
        game.message = previous
        run(m.refresh(game, repost=True))
        self.assertIs(game.message, previous)
        previous.edit.assert_awaited_once()

    def test_last_required_selection_advances_once_and_passive_roles_do_not_wait(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        m.sessions[10] = game
        for p in game.players.values():
            p.owner_id = 99
        game.prepare_night()
        self.assertEqual(game.actions, {1: None})
        interaction = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock()),
                        edit_original_response=AsyncMock(), followup=S(send=AsyncMock()))
        with patch.object(m, "refresh", AsyncMock()) as refresh:
            for actor, kind in [(2, "action"), (3, "action"), (4, "action")]:
                select = m.TargetSelect(game, actor, kind)
                select._values = ["skip"]
                run(select.callback(interaction))
                self.assertEqual(game.phase, "밤")
            select = m.TargetSelect(game, 1, "attack")
            select._values = ["skip"]
            run(select.callback(interaction))
            self.assertEqual(game.phase, "토론")
            revision = game.revision
            run(select.callback(interaction))
            self.assertEqual(game.revision, revision)
            self.assertTrue(refresh.call_args.kwargs["repost"])
            self.assertNotIn("토론 마치기", [b.label for b in m.GameView(fixture(["군인"])).children])

    def test_timer_warns_at_thirty_seconds_and_expires_night(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        m.sessions[10] = game
        game.deadline = 120
        game.message = S(channel=S(send=AsyncMock()))
        clock = [0]
        async def sleep(seconds):
            clock[0] += seconds
        with patch.object(m.time, "time", side_effect=lambda: clock[0]), patch.object(m.asyncio, "sleep", sleep), patch.object(m, "refresh", AsyncMock()), patch.object(m.random, "choice", side_effect=lambda items: items[0]):
            run(m.phase_clock(game, game.revision))
        self.assertEqual(clock[0], 120)
        self.assertIn("30초", game.message.channel.send.call_args.args[0])
        self.assertEqual(game.phase, "토론")
        self.assertEqual(game.actions, {1: None, 2: 1, 3: 1, 4: 1})
        self.assertEqual(game.attacks, {1: 2})

    def test_discussion_and_vote_deadlines_and_stale_timer(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        m.sessions[10] = game
        game.phase = "토론"
        with patch.object(m, "refresh", AsyncMock()):
            run(m.finish_phase(game, expired=True))
            self.assertEqual(game.phase, "투표")
            game.votes = {1: 2}
            run(m.finish_phase(game, expired=True))
            self.assertTrue(game.players[2].alive)
            self.assertEqual(game.phase, "최후변론")
            run(m.finish_phase(game, expired=True))
            self.assertEqual(game.phase, "처형 투표")
            game.execution_votes = {1: True, 3: True, 4: False}
            run(m.finish_phase(game, expired=True))
            self.assertFalse(game.players[2].alive)
            self.assertEqual(game.day, 2)
        game.message = S(channel=S(send=AsyncMock()))
        game.deadline = 10
        async def sleep(_seconds):
            pass
        with patch.object(m.asyncio, "sleep", sleep):
            run(m.phase_clock(game, game.revision - 1))
        game.message.channel.send.assert_not_called()

    def test_timeout_randomizes_missing_targets_but_preserves_explicit_skips(self):
        game = fixture(["마피아", "경찰", "의사", "스파이", "해커", "군인"])
        game.actions = {2: None}
        game.attacks = {1: None}
        with patch.object(m.random, "choice", side_effect=lambda items: items[-1]):
            game.fill_missing_night_choices()
        self.assertIsNone(game.actions[2])
        self.assertIsNone(game.attacks[1])
        self.assertIsNotNone(game.actions[3])
        self.assertIsNotNone(game.actions[4])
        self.assertIsNotNone(game.actions[5])
        self.assertIn(4, game.contact_attempts)
        self.assertNotIn(5, game.contact_attempts)
        self.assertIsNotNone(game.actions[6])
        self.assertTrue(game.all_choices_ready())
        self.assertFalse(game.players[2].inbox)
        self.assertIn("자동", game.players[3].inbox[-1])
        counts = {p.player_id: len(p.inbox) for p in game.alive()}
        game.fill_missing_night_choices()
        self.assertEqual(counts, {p.player_id: len(p.inbox) for p in game.alive()})

    def test_automatic_attack_excludes_known_allies_and_doctor_can_protect_self(self):
        game = fixture(["마피아", "스파이", "의사", "경찰"])
        game.players[2].connected_day = 1
        self.assertEqual(m.target_candidates(game, 1, "attack"), [3, 4])
        self.assertIn(3, m.target_candidates(game, 3, "action"))
        self.assertNotIn(4, m.target_candidates(game, 4, "action"))
        with patch.object(m.random, "choice", side_effect=lambda items: items[0]):
            game.fill_missing_night_choices()
        self.assertEqual(game.attacks, {1: 3, 2: 3})



    def test_day_uses_normal_chat_and_unanimous_extension_counts_users_once(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.phase, game.deadline = "토론", 1000
        m.sessions[10] = game
        game.players[1].owner_id = game.players[2].owner_id = 99
        game.players[3].owner_id = game.players[4].owner_id = 100
        def interaction(uid):
            return S(user=S(id=uid), response=S(defer=AsyncMock(), send_message=AsyncMock()))
        panel = m.GameView(game)
        self.assertFalse(next(b for b in panel.children if b.label == "행동").disabled)
        self.assertFalse(hasattr(m, "DayMessageModal"))
        with patch.object(m, "refresh", AsyncMock()), patch.object(m.time, "time", return_value=100):
            run(panel.callback_for("토론 연장")(interaction(99)))
            self.assertEqual(game.discussion_votes, {99: True})
            self.assertEqual(game.deadline, 1000)
            vote_panel = m.GameView(game)
            run(vote_panel.callback_for("찬성")(interaction(100)))
            self.assertIsNone(game.discussion_votes)
            self.assertEqual(game.deadline, 1300)
            self.assertEqual(game.extension_seconds, 300)
            m.set_phase_timer.assert_called_once_with(game, deadline=1300)
            self.assertIn("전원 찬성", game.render())

    def test_extension_veto_stale_poll_and_spectator(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.phase, game.deadline = "토론", 1000
        for actor, p in game.players.items():
            p.owner_id = actor
        m.sessions[10] = game
        def interaction(uid):
            return S(user=S(id=uid), response=S(defer=AsyncMock(), send_message=AsyncMock()))
        with patch.object(m, "refresh", AsyncMock()), patch.object(m.time, "time", return_value=100):
            outsider = interaction(99)
            run(m.GameView(game).callback_for("토론 연장")(outsider))
            self.assertIsNone(game.discussion_votes)
            run(m.GameView(game).callback_for("토론 연장")(interaction(1)))
            first_poll = m.GameView(game)
            run(first_poll.callback_for("반대")(interaction(2)))
            self.assertIsNone(game.discussion_votes)
            self.assertEqual(game.deadline, 1000)
            run(m.GameView(game).callback_for("토론 연장")(interaction(1)))
            run(first_poll.callback_for("찬성")(interaction(2)))
            self.assertEqual(game.discussion_votes, {1: True})
            run(m.finish_phase(game))
            self.assertEqual(game.phase, "투표")
            self.assertIsNone(game.discussion_votes)


    def test_night_results_are_grouped_by_owner_and_only_include_current_night(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.players[1].owner_id = game.players[2].owner_id = 99
        game.players[3].owner_id = game.players[4].owner_id = 100
        for p in game.alive():
            p.inbox.append("지난 밤에 있었던 일")
        game.prepare_night()
        first, second = S(followup=S(send=AsyncMock())), S(followup=S(send=AsyncMock()))
        game.private_recipients = {99: first, 100: second}
        game.actions = {1: None, 2: 1, 3: 3, 4: None}
        game.attacks = {1: 3}
        game.resolve_night()
        run(m.send_night_results(game))
        text = "".join(call.args[0] for call in first.followup.send.call_args_list)
        self.assertIn("P1", text)
        self.assertIn("P2", text)
        self.assertIn("능력 대상", text)
        self.assertNotIn("지난 밤", text)
        self.assertNotIn("P4", text)
        self.assertIn("보호에 막혔", text)
        self.assertTrue(all(call.kwargs["ephemeral"] for call in first.followup.send.call_args_list))
        self.assertTrue(all(len(call.args[0]) <= 1900 for call in first.followup.send.call_args_list))
        own_text = "".join(call.args[0] for call in second.followup.send.call_args_list)
        self.assertIn("P4", own_text)
        self.assertNotIn("조사 결과", own_text)

    def test_expired_private_notification_does_not_block_other_players(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.prepare_night()
        for index, p in game.players.items():
            p.owner_id = index
        bad = S(followup=S(send=AsyncMock(side_effect=OSError)))
        good = S(followup=S(send=AsyncMock()))
        game.private_recipients = {1: bad, 2: good}
        run(m.send_night_results(game))
        good.followup.send.assert_awaited_once()

    def test_role_guide_command_and_compact_character_cards(self):
        import main
        command = main.bot.tree.get_command("마피아게임")
        self.assertEqual([choice.name for choice in command.parameters[0].choices], ["모집", "직업설명"])
        interaction = S(response=S(send_message=AsyncMock()))
        run(command.callback(interaction, S(value="roles")))
        text = interaction.response.send_message.call_args.args[0]
        self.assertTrue(all(role in text for role in m.DESCRIPTIONS))
        self.assertLessEqual(len(text), 2000)
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.players[2].inbox = ["새로운 조사 결과"]
        details = m.role_details(game, game.players[2], results=False)
        self.assertNotIn(m.DESCRIPTIONS["경찰"], details)
        self.assertNotIn("새로운 조사 결과", details)
        self.assertIn("새로운 조사 결과", m.role_details(game, game.players[2]))

    def test_hacker_selecting_mafia_automatically_contacts_without_blocking(self):
        game = fixture(["마피아", "해커", "경찰", "의사", "군인", "탐정"])
        game.actions = {2: 1}
        game.attacks = {1: 3}
        game.resolve_night()
        self.assertIn(2, game.contact_attempts)
        self.assertEqual(game.players[2].connected_day, 2)
        self.assertFalse(game.players[3].alive)
        self.assertFalse(any("방해" in item for item in game.players[1].inbox))
        self.assertTrue(any("접선" in item for item in game.players[1].inbox))
        failed = fixture(["마피아", "해커", "경찰", "의사", "군인", "탐정"])
        failed.actions = {2: 1}
        with patch.object(m.random, "randint", return_value=100):
            failed.resolve_night()
        self.assertEqual(failed.players[2].connected_day, 0)
        self.assertFalse(any("방해" in item for item in failed.players[1].inbox))

    def test_soldier_intercepts_once_and_failed_health_kills_soldier_not_target(self):
        game = fixture(["마피아", "군인", "경찰", "스파이", "의사", "탐정"])
        self.assertTrue(game.needs_night_action(game.players[2]))
        game.players[4].connected_day = 1
        game.actions = {2: 3}
        game.attacks = {1: 3, 4: 3}
        game.resolve_night()
        self.assertTrue(game.players[2].alive)
        self.assertTrue(game.players[2].used)
        self.assertFalse(game.players[3].alive)
        self.assertFalse(game.needs_night_action(game.players[2]))
        failed = fixture(["마피아", "군인", "경찰", "의사", "탐정", "기자"])
        failed.actions = {2: 3}
        failed.attacks = {1: 3}
        with patch.object(m.random, "randint", side_effect=[1, 100]):
            failed.resolve_night()
        self.assertFalse(failed.players[2].alive)
        self.assertTrue(failed.players[3].alive)
        self.assertIn("탈락", failed.players[2].inbox[-1])

    def test_shortening_discussion_requires_every_owner_and_veto_preserves_time(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.phase, game.deadline = "토론", 1000
        game.players[1].owner_id = game.players[2].owner_id = 99
        game.players[3].owner_id = game.players[4].owner_id = 100
        m.sessions[10] = game
        def interaction(owner):
            return S(user=S(id=owner), response=S(defer=AsyncMock(), send_message=AsyncMock()))
        with patch.object(m.time, "time", return_value=100), patch.object(m, "refresh", AsyncMock()):
            run(m.GameView(game).callback_for("토론 단축")(interaction(99)))
            self.assertEqual(game.phase, "토론")
            run(m.GameView(game).callback_for("반대")(interaction(100)))
            self.assertEqual(game.phase, "토론")
            self.assertEqual(game.deadline, 1000)
            run(m.GameView(game).callback_for("토론 단축")(interaction(99)))
            run(m.GameView(game).callback_for("찬성")(interaction(100)))
            self.assertEqual(game.phase, "투표")
        self.assertEqual(m.PHASE_SECONDS["토론"], 600)

    def test_role_card_shows_one_rate_and_never_lists_self_as_contact(self):
        game = fixture(["마피아", "스파이", "경찰", "의사"])
        mafia = game.players[1]
        mafia.skill_values = {"사격 | 권총": 25}
        alone = m.role_details(game, mafia)
        self.assertNotIn("마피아", alone)
        self.assertNotIn("성공률", alone)
        self.assertNotIn("접선한 동료", alone)
        game.players[2].connected_day = 1
        self.assertIn("접선한 동료 · P2", m.role_details(game, mafia))
        self.assertNotIn("접선한 동료 · P1", m.role_details(game, mafia))
        spy = game.players[2]
        spy.skill_values = {"은밀행동": 80, "사격 | 권총": 20}
        connected = m.role_details(game, spy)
        self.assertNotIn("스파이", connected)
        self.assertNotIn("성공률", connected)
        self.assertIn("접선한 동료 · P1", connected)
        spy.connected_day = 0
        self.assertNotIn("성공률", m.role_details(game, spy))
        self.assertNotIn("접선한 동료", m.role_details(game, spy))

    def test_team_chat_closes_when_only_one_connected_player_survives(self):
        game = fixture(["마피아", "스파이", "경찰", "의사"])
        m.sessions[10] = game
        self.assertFalse(game.team_chat_available(game.players[1]))
        game.players[2].connected_day = game.day + 1
        self.assertFalse(game.team_chat_available(game.players[1]))
        game.players[2].connected_day = game.day
        self.assertTrue(game.team_chat_available(game.players[1]))
        first, second = S(edit=AsyncMock()), S(edit=AsyncMock())
        game.team_windows = {1: (game.day, first), 2: (game.day, second)}
        game.players[2].alive = False
        self.assertFalse(m.chat_allowed(game, game.players[1].owner_id, 1, game.day))
        run(m.update_team_windows(game))
        self.assertFalse(game.team_windows)
        self.assertIsNone(first.edit.call_args.kwargs["view"])
        self.assertIsNone(second.edit.call_args.kwargs["view"])

    def test_medium_is_random_citizen_role_and_can_select_dead_characters(self):
        game = fixture([""] * 4)
        with patch.object(m.random, "sample", return_value=["영매"]), patch.object(m.random, "shuffle"):
            game.start()
        self.assertEqual([p.role for p in game.players.values()], ["마피아", "경찰", "의사", "영매"])
        medium = game.players[4]
        self.assertTrue(game.needs_night_action(medium))
        medium.skill_values = {"정신": 80}
        self.assertEqual(game.success_rate(medium), 78)
        game.players[2].alive = False
        self.assertIn(2, m.target_candidates(game, 4, "action"))
        self.assertNotIn(2, m.target_candidates(game, 3, "action"))
        self.assertNotIn(2, m.target_candidates(game, 1, "attack"))
        medium.owner_id = 99
        m.sessions[10] = game
        choice = m.TargetSelect(game, 4, "action")
        choice._values = ["2"]
        interaction = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock()), edit_original_response=AsyncMock())
        with patch.object(m, "refresh", AsyncMock()):
            run(choice.callback(interaction))
        self.assertEqual(game.actions[4], 2)

    def test_medium_hears_only_written_will_or_empty_whisper(self):
        game = fixture(["마피아", "영매", "의사", "경찰", "군인", "기자"])
        game.players[6].alive = False
        game.players[6].last_words = "경찰의 말을 다시 생각해 봐."
        game.actions = {2: 6}
        game.resolve_night()
        result = game.players[2].inbox[-1]
        self.assertIn("P6", result)
        self.assertIn("경찰의 말을 다시 생각해 봐.", result)
        self.assertNotIn("P1", result)
        self.assertNotIn(6, game.night_history.get(2, set()))
        game.players[6].last_words = ""
        game.resolve_night()
        self.assertIn("희미한 숨소리", game.players[2].inbox[-1])

    def test_medium_tracks_failed_night_actions_but_not_votes_or_blocked_actions(self):
        game = fixture(["마피아", "영매", "경찰", "해커", "의사", "기자"])
        game.actions = {3: 6}
        game.attacks = {1: 6}
        with patch.object(m.random, "randint", return_value=100):
            game.resolve_night()
        self.assertEqual(game.night_history[3], {6})
        self.assertEqual(game.night_history[1], {6})
        game.votes = {1: 5}
        game.resolve_vote()
        self.assertNotIn(5, game.night_history[1])
        game.players[6].alive = False
        game.actions, game.attacks = {2: 3}, {}
        game.resolve_night()
        result = game.players[2].inbox[-1]
        self.assertIn("P3", result)
        self.assertIn("P6", result)
        self.assertNotIn("기자", result)
        blocked = fixture(["마피아", "영매", "경찰", "해커", "의사", "기자"])
        blocked.actions = {3: 6, 4: 3}
        blocked.resolve_night()
        self.assertNotIn(3, blocked.night_history)

    def test_last_words_prompt_is_private_and_reveals_no_killer(self):
        game = fixture(["마피아", "영매", "의사", "경찰", "군인", "기자"])
        game.players[6].owner_id = 99
        game.prepare_night()
        game.attacks = {1: 6}
        recipient = S(followup=S(send=AsyncMock()))
        game.private_recipients = {99: recipient}
        m.sessions[10] = game
        with patch.object(m, "refresh", AsyncMock()):
            run(m.finish_phase(game))
        messages = recipient.followup.send.call_args_list
        self.assertEqual(len(messages), 2)
        self.assertTrue(all(call.kwargs["ephemeral"] for call in messages))
        self.assertFalse(any("P1" in call.args[0] for call in messages))
        prompt = messages[-1]
        self.assertIn("P6", prompt.args[0])
        self.assertIsInstance(prompt.kwargs["view"], m.LastWordsView)
        self.assertEqual(prompt.kwargs["view"].children[0].label, "유언 남기기")
        reader = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock()), followup=S(send=AsyncMock()))
        run(m.GameView(game).callback_for("행동")(reader))
        self.assertIsInstance(reader.followup.send.call_args.kwargs["view"], m.LastWordsView)

    def test_last_words_modal_checks_owner_death_and_length(self):
        game = fixture(["마피아", "영매", "의사", "경찰"])
        game.players[3].owner_id = 99
        game.players[3].alive = False
        source = S(delete_original_response=AsyncMock())
        modal = m.LastWordsModal(game, 3, source)
        interaction = S(user=S(id=99), response=S(defer=AsyncMock()), edit_original_response=AsyncMock())
        modal.text._value = "한 명의 말만 믿지 마."
        run(modal.on_submit(interaction))
        self.assertEqual(game.players[3].last_words, "한 명의 말만 믿지 마.")
        source.delete_original_response.assert_awaited_once()
        self.assertFalse(m.last_words_allowed(game, 99, 3))
        reader = S(user=S(id=99), response=S(send_message=AsyncMock()))
        run(m.GameView(game).callback_for("행동")(reader))
        reader.response.send_message.assert_awaited_once()
        modal.text._value = "x" * 101
        run(modal.on_submit(interaction))
        self.assertNotEqual(game.players[3].last_words, "x" * 101)
        interaction.user.id = 100
        modal.text._value = "다른 사람의 글"
        run(modal.on_submit(interaction))
        self.assertEqual(game.players[3].last_words, "한 명의 말만 믿지 마.")
        interaction.user.id = 99
        game.players[3].alive = True
        run(modal.on_submit(interaction))
        self.assertEqual(game.players[3].last_words, "한 명의 말만 믿지 마.")

    def test_hidden_roles_use_the_same_options_and_short_failure_clues(self):
        game = fixture(["마피아", "경찰", "의사", "스파이", "기자", "군인", "영매"])
        game.players[6].alive = False
        panel = m.GameView(game)
        expected = None
        for player in game.alive():
            select = m.CharacterActionView(panel, player).children[0]
            self.assertEqual(select.kind, "hidden")
            options = [(option.value, option.label) for option in select.options]
            if expected is None:
                expected = options
            self.assertEqual(options, expected)
            card = m.role_details(game, player, results=False)
            self.assertNotIn(player.role, card)
            self.assertNotIn("성공률", card)
        with patch.object(m.random, "randint", return_value=100):
            for player in game.alive():
                self.assertFalse(game.check(player))
                self.assertEqual(player.inbox[-1], m.FAILURE_HINTS[player.role])
                self.assertLessEqual(len(player.inbox[-1]), 25)
        self.assertEqual(m.FAILURE_HINTS["경찰"], m.FAILURE_HINTS["기자"])
        self.assertEqual(m.FAILURE_HINTS["탐정"], m.FAILURE_HINTS["기자"])
        self.assertEqual(m.FAILURE_HINTS["스파이"], m.FAILURE_HINTS["해커"])

    def test_hidden_choices_route_to_real_abilities_and_wait_for_every_character(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.night_selections = {}
        game.prepare_night()
        game.choose_night_target(1, 2)
        self.assertEqual(game.attacks, {1: 2})
        game.choose_night_target(2, 1)
        game.choose_night_target(3, 3)
        self.assertEqual(game.actions[3], 3)
        self.assertFalse(game.all_choices_ready())
        game.choose_night_target(4, 2)
        self.assertTrue(game.all_choices_ready())
        game.resolve_night()
        self.assertTrue(game.players[2].alive)
        self.assertTrue(game.players[4].used)
        game.votes = {p.player_id: None for p in game.alive()}
        game.resolve_vote()
        self.assertEqual(game.night_selections, {})

    def test_hidden_invalid_target_preserves_secret_and_timeout_choices_are_valid(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.night_selections = {}
        game.prepare_night()
        game.choose_night_target(1, 1)
        self.assertIn(1, game.invalid_selections)
        self.assertIsNone(game.attacks[1])
        with patch.object(m.random, "choice", side_effect=lambda values: values[0]):
            game.fill_missing_night_choices()
        self.assertTrue(game.all_choices_ready())
        game.resolve_night()
        self.assertIn("공격이 빗나갔어요.", game.players[1].inbox)
        for player in game.players.values():
            self.assertTrue(player.alive)

    def test_game_start_activates_hidden_choices_and_roles_reveal_only_at_ending(self):
        game = fixture([""] * 4)
        with patch.object(m.random, "sample", return_value=["영매"]), patch.object(m.random, "shuffle"):
            game.start()
        self.assertEqual(game.night_selections, {})
        self.assertFalse(game.all_choices_ready())
        self.assertNotIn("경찰", game.render())
        self.assertNotIn("영매", game.render())
        game.phase = "종료"
        self.assertIn("마피아", game.render())
        self.assertIn("영매", game.render())

    def test_team_chat_repost_sends_new_private_window_before_deleting_old(self):
        game = fixture(["마피아", "스파이", "경찰", "의사"])
        m.sessions[10] = game
        game.players[1].owner_id = 99
        game.players[2].owner_id = 100
        game.players[2].connected_day = 1
        order = []
        first_old = S(edit=AsyncMock(), delete=AsyncMock(side_effect=lambda: order.append("delete")))
        second_old = S(edit=AsyncMock(), delete=AsyncMock())
        first_new, second_new = S(edit=AsyncMock(), delete=AsyncMock()), S(edit=AsyncMock(), delete=AsyncMock())
        def send_first(*args, **kwargs):
            order.append("send")
            return first_new
        first = S(followup=S(send=AsyncMock(side_effect=send_first)))
        second = S(followup=S(send=AsyncMock(return_value=second_new)))
        game.private_recipients = {99: first, 100: second}
        game.team_windows = {1: (1, first_old), 2: (1, second_old)}
        run(m.update_team_windows(game, repost=True))
        self.assertEqual(order, ["send", "delete"])
        self.assertIs(game.team_windows[1][1], first_new)
        self.assertIs(game.team_windows[2][1], second_new)
        self.assertTrue(first.followup.send.call_args.kwargs["ephemeral"])
        self.assertTrue(first.followup.send.call_args.kwargs["wait"])
        game.private_recipients[99] = S(followup=S(send=AsyncMock(side_effect=OSError)))
        run(m.update_team_windows(game, repost=True))
        self.assertIs(game.team_windows[1][1], first_new)
        first_new.edit.assert_awaited_once()

    def test_defense_verdict_tie_abstention_and_same_day(self):
        for ballots in ({1: True, 3: False}, {}):
            game = fixture(["마피아", "경찰", "의사", "군인"])
            game.phase = "투표"
            game.votes = {1: 2, 2: 2, 3: 2, 4: None}
            game.resolve_vote()
            self.assertEqual((game.phase, game.day, game.nominee), ("최후변론", 1, 2))
            self.assertTrue(game.players[2].alive)
            self.assertIn("P2", game.render())
            self.assertFalse(game.all_choices_ready())
            game.phase = "처형 투표"
            game.execution_votes = ballots
            game.resolve_execution()
            self.assertTrue(game.players[2].alive)
            self.assertEqual((game.phase, game.day, game.nominee), ("밤", 2, None))

    def test_execution_controls_reject_nominee_and_accept_owned_characters(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.phase, game.nominee = "처형 투표", 2
        for p in game.players.values():
            p.owner_id = 42
        m.sessions[10] = game
        interaction = S(user=S(id=42), response=S(send_message=AsyncMock(), defer=AsyncMock()),
                        followup=S(send=AsyncMock()))
        panel = m.GameView(game)
        self.assertIn("처형 찬성", [b.label for b in panel.children])
        run(panel.callback_for("처형 찬성", 2)(interaction))
        self.assertEqual(game.execution_votes, {})
        with patch.object(m, "refresh", AsyncMock()):
            for pid in (1, 3):
                run(panel.callback_for("처형 찬성", pid)(interaction))
            self.assertFalse(game.all_choices_ready())
            run(panel.callback_for("처형 반대", 4)(interaction))
        self.assertFalse(game.players[2].alive)
        self.assertEqual(game.phase, "밤")


class TimerSchedulingTests(unittest.TestCase):
    def test_new_phase_replaces_timer_and_end_cancels_it(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        previous = S(cancel=unittest.mock.Mock())
        next_task = S(cancel=unittest.mock.Mock())
        game.phase_task = previous
        def create_task(coroutine):
            coroutine.close()
            return next_task
        with patch.object(m.asyncio, "current_task", return_value=None), patch.object(m.asyncio, "create_task", side_effect=create_task) as schedule, patch.object(m.time, "time", return_value=100):
            m.set_phase_timer(game)
            previous.cancel.assert_called_once()
            self.assertEqual(game.deadline, 220)
            self.assertIs(game.phase_task, next_task)
            game.phase = "종료"
            m.set_phase_timer(game)
            next_task.cancel.assert_called_once()
            self.assertIsNone(game.phase_task)
            self.assertEqual(game.deadline, 0)
            schedule.assert_called_once()


if __name__ == "__main__":
    unittest.main()
