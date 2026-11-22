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
            view = m.GameView(game)
            run(view.callback_for("토론 마치기")(interaction))
            self.assertEqual(game.phase, "투표")
            game.votes = {p.player_id: None for p in game.alive()}
            run(m.advance_if_ready(game))
            self.assertEqual((game.phase, game.day), ("밤", 2))
            self.assertEqual(game.actions, {1: None, 5: None})
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
            self.assertIn("경찰", interaction.response.send_message.call_args.args[0])
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
        self.assertIn("자동 성공", game.players[1].inbox[-1])
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
        windows = [S(edit=AsyncMock()) for _ in range(2)]
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
        for window in windows:
            text = window.edit.call_args.kwargs["content"]
            self.assertIn("P1", text)
            self.assertIn("P4", text)
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
        self.assertEqual([b.label for b in panel.children], ["내 역할 / 결과", "행동", "게임 종료"])
        self.assertNotIn("공격 선택", game.render())
        mafia = [b.label for b in m.CharacterActionView(panel, game.players[1]).children]
        citizen = [b.label for b in m.CharacterActionView(panel, game.players[2]).children]
        spy = [b.label for b in m.CharacterActionView(panel, game.players[4]).children]
        hacker = [b.label for b in m.CharacterActionView(panel, game.players[5]).children]
        self.assertIn("마피아 공격", mafia)
        self.assertIn("팀 대화", mafia)
        self.assertEqual(citizen, ["밤 행동"])
        self.assertEqual(spy, ["접선"])
        self.assertEqual(hacker, ["밤 행동", "접선"])
        game.players[4].connected_day = 1
        self.assertIn("마피아 공격", [b.label for b in m.CharacterActionView(panel, game.players[4]).children])
        game.phase = "투표"
        self.assertEqual([b.label for b in m.CharacterActionView(panel, game.players[1]).children], ["투표"])

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
        self.assertIn("마피아 공격", [b.label for b in cards[0].kwargs["view"].children])
        self.assertNotIn("마피아 공격", [b.label for b in cards[1].kwargs["view"].children])
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
        self.assertEqual(game.actions, {1: None, 4: None})
        interaction = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock()),
                        edit_original_response=AsyncMock())
        with patch.object(m, "refresh", AsyncMock()) as refresh:
            for actor, kind in [(2, "action"), (3, "action")]:
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
        self.assertEqual(game.actions, {1: None, 2: 1, 3: 1, 4: None})
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
        self.assertIsNone(game.actions[6])
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


    def test_day_action_cards_open_per_character_modal_and_publish_only_dialogue(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.phase = "토론"
        game.players[1].owner_id = game.players[2].owner_id = 99
        m.sessions[10] = game
        game.message = S(channel=S(send=AsyncMock()))
        interaction = S(user=S(id=99), response=S(defer=AsyncMock(), send_message=AsyncMock(), send_modal=AsyncMock()),
                        followup=S(send=AsyncMock()), edit_original_response=AsyncMock())
        panel = m.GameView(game)
        self.assertFalse(next(b for b in panel.children if b.label == "행동").disabled)
        run(panel.callback_for("행동")(interaction))
        cards = interaction.followup.send.call_args_list
        self.assertEqual(len(cards), 2)
        for call in cards:
            self.assertTrue(call.kwargs["ephemeral"])
            self.assertEqual([b.label for b in call.kwargs["view"].children], ["대화하기"])
        run(cards[1].kwargs["view"].children[0].callback(interaction))
        modal = interaction.response.send_modal.call_args.args[0]
        modal.text._value = "저는 어젯밤 P1을 조사했어요."
        run(modal.on_submit(interaction))
        output = game.message.channel.send.call_args.args[0]
        self.assertEqual(output, m.code_box("P2: 저는 어젯밤 P1을 조사했어요."))
        self.assertNotIn("경찰", output)
        self.assertNotIn("ephemeral", game.message.channel.send.call_args.kwargs)
        self.assertIsInstance(game.message.channel.send.call_args.kwargs["allowed_mentions"], m.discord.AllowedMentions)

    def test_day_modal_rejects_wrong_owner_dead_empty_late_and_old_round(self):
        game = fixture(["마피아", "경찰", "의사", "군인"])
        game.phase = "토론"
        game.players[2].owner_id = 99
        m.sessions[10] = game
        game.message = S(channel=S(send=AsyncMock()))
        interaction = S(user=S(id=99), response=S(defer=AsyncMock()),
                        edit_original_response=AsyncMock())
        modal = m.DayMessageModal(game, 2)
        modal.text._value = " "
        run(modal.on_submit(interaction))
        modal.text._value = "말할게요."
        interaction.user.id = 100
        run(modal.on_submit(interaction))
        interaction.user.id = 99
        game.players[2].alive = False
        run(modal.on_submit(interaction))
        game.players[2].alive = True
        game.phase = "밤"
        run(modal.on_submit(interaction))
        game.phase = "토론"
        game.deadline = 10
        with patch.object(m.time, "time", return_value=11):
            run(modal.on_submit(interaction))
        game.deadline = 0
        game.revision += 1
        run(modal.on_submit(interaction))
        game.message.channel.send.assert_not_awaited()


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
