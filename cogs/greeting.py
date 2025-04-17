import discord
from discord.ext import commands
import json

# Загрузка конфигурации из файла
async def load_config():
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

class RolePingCog(commands.Cog):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.target_role_id = config.get("role_id")  # ID роли, которую нужно отслеживать
        self.allowed_channel_id = config.get("flood_sai")  # Канал, куда нужно отправлять сообщение
        self.custom_ding = config.get("custom_ding")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Следим за изменением ролей у пользователя"""
        # Проверяем, была ли добавлена нужная роль
        if self.target_role_id in [role.id for role in after.roles] and self.target_role_id not in [role.id for role in before.roles]:
            # Роль была добавлена, отправляем сообщение
            await self.send_role_ping_message(after)

    async def send_role_ping_message(self, member):
        """Отправляем сообщение с упоминанием пользователя после получения роли"""
        channel = self.bot.get_channel(self.allowed_channel_id)
        if channel:
            await channel.send(f"{self.custom_ding} Приветствую, **{member.mention}**! Добро пожаловать в отдел **SAI**. Хорошей и продуктивной работы 🤝")

async def setup(bot):
    config = await load_config()
    await bot.add_cog(RolePingCog(bot, config))
