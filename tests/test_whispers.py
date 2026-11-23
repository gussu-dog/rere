import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, patch
import whispers as w


def run(coroutine):
    try:
        coroutine.send(None)
    except StopIteration:
        return
    raise AssertionError("Unexpected asynchronous work")


async def immediate(function, *args):
    return function(*args)


class WhisperTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "whispers.sqlite3"
        self.store = w.WhisperStore(self.path)

    def test_saved_messages_survive_reopening_and_only_recipient_can_read(self):
        self.store.save(10, 99, "Sender", "Only the recipient can see this")
        reopened = w.WhisperStore(self.path)
        self.assertEqual(reopened.read(10), (99, "Sender", "Only the recipient can see this", "", None))
        view = w.WhisperReadView(reopened)
        self.assertTrue(view.is_persistent())
        interaction = S(user=S(id=100), message=S(id=10),
                        response=S(defer=AsyncMock()), followup=S(send=AsyncMock()))
        with patch.object(w.asyncio, "to_thread", immediate):
            run(view.read.callback(interaction))
            self.assertNotIn("Only the recipient", interaction.followup.send.call_args.kwargs["content"])
            interaction.user.id = 99
            run(view.read.callback(interaction))
            self.assertIn("Only the recipient", interaction.followup.send.call_args.kwargs["embed"].description)
            self.assertEqual(interaction.followup.send.call_args.kwargs["embed"].author.name, "Sender")
            self.assertTrue(interaction.followup.send.call_args.kwargs["ephemeral"])

    def test_compose_keeps_body_out_of_public_announcement(self):
        announcement = S(id=10, edit=AsyncMock(), delete=AsyncMock())
        interaction = S(user=S(id=1, display_name="Sender", display_avatar=S(url="https://example.com/avatar.png")), response=S(defer=AsyncMock(), send_message=AsyncMock()),
                        channel=S(send=AsyncMock(return_value=announcement)),
                        edit_original_response=AsyncMock())
        with patch.object(w.asyncio, "to_thread", immediate):
            run(w.send_whisper(interaction, self.store, 99, "Private text"))
        public = interaction.channel.send.call_args.args[0]
        self.assertIn("<@99>", public)
        self.assertNotIn("Private text", public)
        self.assertEqual(self.store.read(10), (99, "Sender", "Private text", "https://example.com/avatar.png", 1))
        self.assertIsInstance(interaction.channel.send.call_args.kwargs["view"], w.WhisperReadView)
        announcement.edit.assert_not_awaited()
        self.assertTrue(interaction.response.defer.call_args.kwargs["ephemeral"])

    def test_failed_storage_removes_unreadable_announcement(self):
        announcement = S(id=10, delete=AsyncMock(), edit=AsyncMock())
        interaction = S(user=S(id=1, display_name="Sender", display_avatar=S(url="https://example.com/avatar.png")), response=S(defer=AsyncMock()),
                        channel=S(send=AsyncMock(return_value=announcement)),
                        edit_original_response=AsyncMock())
        with patch.object(w.asyncio, "to_thread", immediate), patch.object(self.store, "save", side_effect=OSError):
            run(w.send_whisper(interaction, self.store, 99, "Private text"))
        announcement.delete.assert_awaited_once()
        announcement.edit.assert_not_awaited()

    def test_old_database_stays_readable_and_accepts_avatar(self):
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.path)) as database, database:
            database.execute("CREATE TABLE whispers (message_id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL, sender TEXT NOT NULL, content TEXT NOT NULL)")
            database.execute("INSERT INTO whispers VALUES (1, 99, 'Old sender', 'Old message')")
        self.assertEqual(self.store.read(1), (99, "Old sender", "Old message", "", None))
        self.store.save(2, 99, "New sender", "New message", "https://example.com/avatar.png")
        self.assertEqual(self.store.read(2)[3], "https://example.com/avatar.png")

    def test_sender_can_read_after_reopening_but_other_users_cannot(self):
        self.store.save(10, 99, "Same name", "Secret", sender_id=1)
        view = w.WhisperReadView(w.WhisperStore(self.path))
        for user_id, allowed in ((1, True), (99, True), (100, False)):
            interaction = S(user=S(id=user_id), message=S(id=10),
                            response=S(defer=AsyncMock()), followup=S(send=AsyncMock()))
            with patch.object(w.asyncio, "to_thread", immediate):
                run(view.read.callback(interaction))
            response = interaction.followup.send.call_args.kwargs
            self.assertEqual("embed" in response, allowed)
            self.assertTrue(response["ephemeral"])
