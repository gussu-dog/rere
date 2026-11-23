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
        self.assertEqual(reopened.read(10), (99, "Sender", "Only the recipient can see this"))
        view = w.WhisperReadView(reopened)
        self.assertTrue(view.is_persistent())
        interaction = S(user=S(id=100), message=S(id=10),
                        response=S(defer=AsyncMock()), edit_original_response=AsyncMock())
        with patch.object(w.asyncio, "to_thread", immediate):
            run(view.read.callback(interaction))
            self.assertNotIn("Only the recipient", interaction.edit_original_response.call_args.kwargs["content"])
            interaction.user.id = 99
            run(view.read.callback(interaction))
            self.assertIn("Only the recipient", interaction.edit_original_response.call_args.kwargs["content"])
            self.assertTrue(interaction.response.defer.call_args.kwargs["ephemeral"])

    def test_compose_keeps_body_out_of_public_announcement(self):
        modal = w.WhisperComposeModal(self.store, 1, "Sender", 99)
        modal.content._value = "Private text"
        announcement = S(id=10, edit=AsyncMock(), delete=AsyncMock())
        interaction = S(user=S(id=1), response=S(defer=AsyncMock(), send_message=AsyncMock()),
                        channel=S(send=AsyncMock(return_value=announcement)),
                        edit_original_response=AsyncMock())
        with patch.object(w.asyncio, "to_thread", immediate):
            run(modal.on_submit(interaction))
        public = interaction.channel.send.call_args.args[0]
        self.assertIn("<@99>", public)
        self.assertNotIn("Private text", public)
        self.assertEqual(self.store.read(10), (99, "Sender", "Private text"))
        self.assertIsInstance(announcement.edit.call_args.kwargs["view"], w.WhisperReadView)
        self.assertTrue(interaction.response.defer.call_args.kwargs["ephemeral"])

    def test_failed_storage_removes_unreadable_announcement(self):
        modal = w.WhisperComposeModal(self.store, 1, "Sender", 99)
        modal.content._value = "Private text"
        announcement = S(id=10, delete=AsyncMock(), edit=AsyncMock())
        interaction = S(user=S(id=1), response=S(defer=AsyncMock()),
                        channel=S(send=AsyncMock(return_value=announcement)),
                        edit_original_response=AsyncMock())
        with patch.object(w.asyncio, "to_thread", immediate), patch.object(self.store, "save", side_effect=OSError):
            run(modal.on_submit(interaction))
        announcement.delete.assert_awaited_once()
        announcement.edit.assert_not_awaited()
