import discord
from discord.ext import commands
import json
import os
from pathlib import Path
import aiofiles

TRIGGERS_FILE = Path(__file__).parent / "triggers.json"


async def load_config():
    async with aiofiles.open("config.json", 'r', encoding='utf-8') as f:
        config_data = await f.read()
    return json.loads(config_data)


class TriggerView(discord.ui.View):
    def __init__(self, cog, config):
        super().__init__(timeout=None)
        self.cog = cog
        self.message = None  # Это сообщение с кнопками, установим позже
        self.config = config
        
        self.head_sai = config.get("head_sai")
        
    async def check_user_role(self, interaction: discord.Interaction):
        """Проверка роли пользователя перед нажатием кнопки."""
        has_role = any(role.id == self.cog.head_sai for role in interaction.user.roles)
        if not has_role:
            await interaction.response.send_message("⚠️ У вас нет прав для управления триггерами.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="➕ Добавить", style=discord.ButtonStyle.green)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_user_role(interaction):
        	await interaction.response.send_modal(AddTriggerModal(self.cog))

    @discord.ui.button(label="➖ Удалить", style=discord.ButtonStyle.danger)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_user_role(interaction):
        	await interaction.response.send_modal(RemoveTriggerModal(self.cog))

    @discord.ui.button(label="📋 Список", style=discord.ButtonStyle.blurple)
    async def list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_user_role(interaction):
            if not self.cog.triggers:
                await interaction.response.send_message("❌ Триггеров пока нет.", ephemeral=True)
                return

            embed = discord.Embed(title="📋 Триггеры", color=discord.Color.blurple())
            for trigger, response in self.cog.triggers.items():
                embed.add_field(name=trigger, value=response, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="❌ Удалить сообщение", style=discord.ButtonStyle.red)
    async def delete_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_user_role(interaction):
            if self.message:
                await self.message.delete()
                await interaction.response.send_message("✅ Сообщение удалено.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Не удалось найти сообщение для удаления.", ephemeral=True)



class AddTriggerModal(discord.ui.Modal, title="➕ Добавить триггер"):
    trigger = discord.ui.TextInput(label="Ключевая фраза/слово:", max_length=150, placeholder="Пример: Как повыситься")
    response = discord.ui.TextInput(label="Ответ:", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        # Добавляем новый триггер в словарь и сохраняем в файл
        self.cog.triggers[self.trigger.value.lower()] = self.response.value
        self.cog.save_triggers()  # Сохраняем триггеры
        await interaction.response.send_message(f"✅ Добавлен: `{self.trigger.value}` → `{self.response.value}`", ephemeral=True)


class RemoveTriggerModal(discord.ui.Modal, title="➖ Удалить триггер"):
    trigger = discord.ui.TextInput(label="Ключевая фраза/слово:", max_length=100)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        key = self.trigger.value.lower()
        if key in self.cog.triggers:
            del self.cog.triggers[key]
            self.cog.save_triggers()  # Сохраняем изменения в файл
            await interaction.response.send_message(f"🗑️ Удалён триггер: `{key}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Триггер `{key}` не найден.", ephemeral=True)


class AutoMessage(commands.Cog):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config

        self.allowed_role_id = config.get("cadet_role")
        self.target_channel_id = config.get("automessage_channel")
        self.head_sai = config.get("head_sai")
        
        # Загружаем триггеры
        self.triggers = self.load_triggers()

    def load_triggers(self):
        """Загружает триггеры из файла, если он существует"""
        if os.path.exists(TRIGGERS_FILE):
            with open(TRIGGERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_triggers(self):
        """Сохраняет триггеры в файл"""
        with open(TRIGGERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.triggers, f, indent=4, ensure_ascii=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Проверяем, является ли сообщение командой (это нужно делать перед обработкой триггеров)
        if message.content.startswith(self.bot.command_prefix):
            return

        if message.channel.id != self.target_channel_id:
            return
        
        # Проверка роли
        if self.allowed_role_id:
            has_role = any(role.id == self.allowed_role_id for role in message.author.roles)
            if not has_role:
                return  # Пользователь не имеет нужной роли

        content = message.content.lower()
        for trigger, response in self.triggers.items():
            if trigger in content:
                await message.reply(response)
                break

    @commands.command(name="triggermenu")
    async def trigger_menu(self, ctx):
        # Проверяем, есть ли у пользователя нужная роль
        has_role = any(role.id == self.head_sai for role in ctx.author.roles)
        if not has_role:
            await ctx.send("⚠️ У вас нет прав для управления триггерами.")
            return

        # Логируем, что у пользователя есть роль
        print(f"User {ctx.author} has the required role. Proceeding with trigger menu.")

        try:
            # Удаляем сообщение с командой
            await ctx.message.delete()
            print("Message with command deleted.")

            # Создаем и передаем config в TriggerView
            self_message_view = TriggerView(self, self.config)
            msg = await ctx.send("🔧 Управление триггерами:", view=self_message_view)
            print(f"Message sent with view: {msg.id}")

            # Обновляем сообщение с новым view
            self_message_view.message = msg  # Передаем сообщение в view
            await msg.edit(view=self_message_view)  # Обновляем сообщение с новым view
            print("View updated on message.")

        except Exception as e:
            # Логируем ошибку, если она произошла
            print(f"Error occurred: {e}")
            await ctx.send("❌ Произошла ошибка при обработке команды.")




async def setup(bot):
    config = await load_config()
    await bot.add_cog(AutoMessage(bot, config))
