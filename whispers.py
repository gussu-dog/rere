from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path

import discord
from discord import app_commands


class WhisperStore:
    def __init__(self, path: Path):
        self.path = path

    def save(self, message_id: int, recipient_id: int, sender: str, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as database, database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS whispers "
                "(message_id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL, sender TEXT NOT NULL, content TEXT NOT NULL)"
            )
            database.execute("INSERT INTO whispers VALUES (?, ?, ?, ?)",
                             (message_id, recipient_id, sender, content))

    def read(self, message_id: int) -> tuple[int, str, str] | None:
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path)) as database:
            return database.execute(
                "SELECT recipient_id, sender, content FROM whispers WHERE message_id = ?", (message_id,)
            ).fetchone()


class WhisperReadView(discord.ui.View):
    def __init__(self, store: WhisperStore):
        super().__init__(timeout=None)
        self.store = store

    @discord.ui.button(label="확인하기", custom_id="rere:whisper:read", style=discord.ButtonStyle.primary)
    async def read(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        try:
            record = await asyncio.to_thread(self.store.read, interaction.message.id)
        except sqlite3.Error:
            await interaction.followup.send(ephemeral=True, content="비밀메시지를 읽지 못했어요. 잠시 후 다시 눌러 주세요.")
            return
        if record is None:
            await interaction.followup.send(ephemeral=True, content="저장된 비밀메시지를 찾지 못했어요.")
            return
        recipient_id, sender, content = record
        if interaction.user.id != recipient_id:
            await interaction.followup.send(ephemeral=True, content="이 비밀메시지는 받는 사람만 확인할 수 있어요!")
            return
        await interaction.followup.send(ephemeral=True,
            content=f"{discord.utils.escape_markdown(sender)}님으로부터 비밀메시지가 도착했어요!\n\n{content}",
            allowed_mentions=discord.AllowedMentions.none(),
        )


class WhisperComposeModal(discord.ui.Modal, title="비밀메시지 보내기"):
    content = discord.ui.TextInput(label="전할 말", style=discord.TextStyle.paragraph, max_length=1600)

    def __init__(self, store: WhisperStore, sender_id: int, sender: str, recipient_id: int):
        super().__init__()
        self.store, self.sender_id, self.sender, self.recipient_id = store, sender_id, sender, recipient_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.sender_id:
            await interaction.response.send_message("본인의 입력창을 이용해 주세요.", ephemeral=True)
            return
        content = self.content.value.strip()
        if not content:
            await interaction.response.send_message("전할 말을 적어 주세요.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        announcement = None
        saved = False
        try:
            announcement = await interaction.channel.send(
                f"<@{self.recipient_id}>님에게 비밀메시지가 도착했어요!",
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False,
                                                         users=[discord.Object(id=self.recipient_id)]),
            )
            await asyncio.to_thread(self.store.save, announcement.id, self.recipient_id, self.sender, content)
            saved = True
            await announcement.edit(view=WhisperReadView(self.store))
        except (discord.HTTPException, OSError, sqlite3.Error) as error:
            print(f"Whisper delivery failed ({type(error).__name__}).", flush=True)
            if announcement is not None and not saved:
                try:
                    await announcement.delete()
                except (discord.HTTPException, OSError):
                    pass
            await interaction.edit_original_response(
                content="메시지는 저장했지만 확인 버튼을 표시하지 못했어요. 잠시 후 다시 보내 주세요."
                if saved else "비밀메시지를 보내지 못했어요. 잠시 후 다시 시도해 주세요."
            )
            return
        await interaction.edit_original_response(content="비밀메시지를 전했어요!")


def install(bot, data_dir: Path) -> None:
    store = WhisperStore(data_dir / "whispers.sqlite3")
    registered = False

    async def register_view() -> None:
        nonlocal registered
        if not registered:
            bot.add_view(WhisperReadView(store))
            registered = True

    bot.add_listener(register_view, "on_ready")

    @bot.tree.command(name="귓", description="상대에게만 보이는 비밀메시지를 전달해요!")
    @app_commands.guild_only()
    @app_commands.rename(recipient="받는이")
    @app_commands.describe(recipient="비밀메시지를 받을 사람")
    async def whisper(interaction: discord.Interaction, recipient: discord.Member) -> None:
        await interaction.response.send_modal(
            WhisperComposeModal(store, interaction.user.id, interaction.user.display_name, recipient.id)
        )
