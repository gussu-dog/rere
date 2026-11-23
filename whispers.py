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

    def save(self, message_id: int, recipient_id: int, sender: str, content: str, avatar_url: str = "") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as database, database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS whispers "
                "(message_id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL, sender TEXT NOT NULL, content TEXT NOT NULL)"
            )
            columns = {row[1] for row in database.execute("PRAGMA table_info(whispers)")}
            if "avatar_url" not in columns:
                database.execute("ALTER TABLE whispers ADD COLUMN avatar_url TEXT NOT NULL DEFAULT ''")
            database.execute("INSERT INTO whispers (message_id, recipient_id, sender, content, avatar_url) VALUES (?, ?, ?, ?, ?)",
                             (message_id, recipient_id, sender, content, avatar_url))

    def read(self, message_id: int) -> tuple[int, str, str, str] | None:
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path)) as database:
            columns = {row[1] for row in database.execute("PRAGMA table_info(whispers)")}
            avatar = "avatar_url" if "avatar_url" in columns else "''"
            return database.execute(
                f"SELECT recipient_id, sender, content, {avatar} FROM whispers WHERE message_id = ?", (message_id,)
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
        recipient_id, sender, content, avatar_url = record
        if interaction.user.id != recipient_id:
            await interaction.followup.send(ephemeral=True, content="이 비밀메시지는 받는 사람만 확인할 수 있어요!")
            return
        card = discord.Embed(description=content)
        card.set_author(name=sender, icon_url=avatar_url or None)
        await interaction.followup.send(ephemeral=True,
            embed=card,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def send_whisper(interaction: discord.Interaction, store: WhisperStore, recipient_id: int, content: str) -> None:
    content = content.strip()
    if not content or len(content) > 1600:
        await interaction.response.send_message("전할 말은 1~1600자로 적어 주세요.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    announcement = None
    try:
        announcement = await interaction.channel.send(
            f"<@{recipient_id}>님에게 비밀메시지가 도착했어요!",
            view=WhisperReadView(store),
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False,
                                                     users=[discord.Object(id=recipient_id)]),
        )
        await asyncio.to_thread(store.save, announcement.id, recipient_id, interaction.user.display_name, content, str(interaction.user.display_avatar.url))
    except (discord.HTTPException, OSError, sqlite3.Error) as error:
        print(f"Whisper delivery failed ({type(error).__name__}).", flush=True)
        if announcement is not None:
            try:
                await announcement.delete()
            except (discord.HTTPException, OSError):
                pass
        await interaction.edit_original_response(
            content="비밀메시지를 보내지 못했어요. 잠시 후 다시 시도해 주세요."
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
    @app_commands.rename(recipient="받는이", content="내용")
    @app_commands.describe(recipient="비밀메시지를 받을 사람", content="상대에게 전할 비밀메시지")
    async def whisper(interaction: discord.Interaction, recipient: discord.Member, content: str) -> None:
        await send_whisper(interaction, store, recipient.id, content)
