import discord
from discord.ext import commands
import aiofiles
import json
import asyncio

class Meetings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = None  # ID канала будет загружаться из config.json
        self.flood_sai_link = None
        self.head_sai = None  # Роли, которые могут управлять собранием
        self.votes = {"Требуется": {}, "Не требуется": {}}  # Сохранение голосов
        self.sai_role = None

    async def load_config(self):
        # """Загружает конфигурацию из config.json"""
        async with aiofiles.open("config.json", "r", encoding="utf-8") as f:
            config_data = await f.read()

        config = json.loads(config_data)
        self.channel_id = config.get("news_channel")  # ID канала для сообщений
        self.flood_sai_link = config["flood_sai_link"]
        self.head_sai = config["head_sai"]  # Роли, которые могут управлять собранием
        self.sai_role_mention = config["role_mention"]
        self.sai_role = config["role_id"]
        self.custom_yes = config["custom_yes"]
        self.custom_no = config["custom_no"]
        self.custom_wait = config["custom_wait"]
        self.custom_ding = config["custom_ding"]

    @commands.command(name="meeting")
    async def meeting_command(self, ctx):
        # """Отправляет сообщение о встрече с кнопками голосования"""
        await self.load_config()  # Загружаем конфиг

        # Проверяем, есть ли у пользователя нужная роль
        allowed_roles = set(self.head_sai) if isinstance(self.head_sai, list) else {int(self.head_sai)}
        user_roles = {role.id for role in ctx.author.roles}

        if not allowed_roles & user_roles:
            msg = await ctx.reply(f"{self.custom_no} У вас нет роли, чтобы выполнить эту команду.")
            await asyncio.sleep(4)
            await msg.delete()
            return
    

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            await ctx.send_reply("❌ Ошибка: Канал для встреч не найден. Проверьте `config.json`!")
            return

        embed = discord.Embed(
            title=f"{self.custom_ding} Приветствую, коллеги!",
            description=f"**Требуется ли Вам собрание с\n*руководством отдела* на этой неделе?**\n\n" + f"*Голосовать можно 1 раз за любой вариант. Свой голос можно менять.*",
            color=discord.Color.green()
        )
        embed.set_footer(text="Свой голос можно отдать внизу! Приятного дня! ✌️")

        view = MeetingView(self)  # Передаём `Meetings` в `MeetingView`
        await channel.send(self.sai_role_mention, embed=embed, view=view)
        msg1 = await ctx.send_reply("✅ Напоминание отправлено!")
        await asyncio.sleep(5)
        await msg1.delete()
        await ctx.message.delete()

    @commands.command(name="meeting_results")
    async def meeting_results(self, ctx):
        try:
            await self.load_config()  # Загружаем конфиг перед отправкой
            # Проверяем, есть ли у пользователя нужная роль
            allowed_roles = set(self.head_sai) if isinstance(self.head_sai, list) else {int(self.head_sai)}
            user_roles = {role.id for role in ctx.author.roles}

            if not allowed_roles & user_roles:
                msg = await ctx.reply(f"{self.custom_no} У вас нет роли, чтобы выполнить эту команду.")
                await asyncio.sleep(4)
                await msg.delete()
                return

            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                await ctx.send("❌ Ошибка: Канал не найден. Проверьте `config.json`!")
                return

            yes_count = len(self.votes["Требуется"])
            no_count = len(self.votes["Не требуется"])

            results = f"{self.custom_yes} **Требуется:** *{yes_count} голос(ов)*\n" \
                      f"{self.custom_no} **Не требуется:** *{no_count} голос(ов)*\n"

            embed = discord.Embed(title=f"{self.custom_ding} Итоги голосования:", description=results, color=discord.Color.blue())

            view = ManageMeetingView(self)  # Добавляем кнопки управления собранием
            await ctx.send(embed=embed, view=view)

            await ctx.message.delete()
        except Exception as error:
            print(f"Произошла ошибка: {error}")


class MeetingView(discord.ui.View):
    # """Класс для кнопок 'Требуется' и 'Нет, не требуется'"""
    
    def __init__(self, cog):
        super().__init__(timeout=None)  # Кнопки остаются активными
        self.cog = cog  # Ссылка на `Meetings`


    async def load_config(self):
    # """Загружает конфигурацию из config.json"""
        async with aiofiles.open("config.json", "r", encoding="utf-8") as f:
            config_data = await f.read()



    @discord.ui.button(label="Требуется", style=discord.ButtonStyle.green)
    async def require_meeting(self, interaction: discord.Interaction, button: discord.ui.Button):
        # """Обрабатывает нажатие на кнопку 'Требуется'"""
        user = interaction.user
        # Проверяем, есть ли у пользователя нужная роль
        allowed_roles = set(self.cog.sai_role) if isinstance(self.cog.sai_role, list) else {int(self.cog.sai_role)}
        user_roles = {role.id for role in user.roles}

        if not allowed_roles & user_roles:
            await interaction.response.send_message(f"{self.cog.custom_no} Вы не работник SAI, чтобы голосовать.", ephemeral=True)
            return

        if user.id in self.cog.votes["Требуется"]:
            await interaction.response.send_message(f"{self.cog.custom_ding} Вы уже проголосовали за **Требуется!**", ephemeral=True)
            return
        
        if user.id in self.cog.votes["Не требуется"]:
            self.cog.votes["Не требуется"].pop(user.id)

        self.cog.votes["Требуется"][user.id] = True
        await interaction.response.send_message(f"{self.cog.custom_yes} Вы успешно проголосовали за **Требуется.**", ephemeral=True)

    @discord.ui.button(label="Не требуется", style=discord.ButtonStyle.red)
    async def not_require_meeting(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
                
            await self.load_config()  # Загружаем конфиг перед отправкой
            # """Обрабатывает нажатие на кнопку 'Нет, не требуется'"""
            user = interaction.user

            # Проверяем, есть ли у пользователя нужная роль
            allowed_roles = set(self.cog.sai_role) if isinstance(self.cog.sai_role, list) else {int(self.cog.sai_role)}
            user_roles = {role.id for role in user.roles}

            if not allowed_roles & user_roles:
                await interaction.response.send_message(f"{self.cog.custom_no} Вы не работник SAI, чтобы голосовать.", ephemeral=True)
                return

            if user.id in self.cog.votes["Не требуется"]:
                await interaction.response.send_message(f"{self.cog.custom_ding} Вы уже проголосовали за **Не требуется!**", ephemeral=True)
                return
            
            if user.id in self.cog.votes["Требуется"]:
                self.cog.votes["Требуется"].pop(user.id)

            self.cog.votes["Не требуется"][user.id] = True
            await interaction.response.send_message(f"{self.cog.custom_yes} Вы успешно проголосовали за **Не требуется.**", ephemeral=True)
        except Exception as e:
            print(e)




class ManageMeetingView(discord.ui.View):
    # """Кнопки 'Провести собрание' и 'Отменить собрание'"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Провести собрание", style=discord.ButtonStyle.green, emoji="✅")
    async def schedule_meeting(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:

            # """Открывает модальное окно для выбора даты и времени"""
            user_roles = {role.id for role in interaction.user.roles}
            if self.cog.head_sai not in user_roles:
                await interaction.response.send_message(f"{self.cog.custom_no} У вас нет прав для назначения собрания.", ephemeral=True)
                return

            modal = MeetingModal(self.cog)
            await interaction.response.send_modal(modal)  # ✅ Отправляем модальное окно

            # ⏳ Убираем кнопки, редактируя сообщение
            if interaction.message:
                await interaction.message.edit(view=None)
        except Exception as error:
            print(f"Произошла ошибка: {error}")

    @discord.ui.button(label="Отменить собрание", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_meeting(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # """Отправляет сообщение об отмене собрания"""
            user_roles = {role.id for role in interaction.user.roles}
            if self.cog.head_sai not in user_roles:
                await interaction.response.send_message(f"{self.cog.custom_no} У вас нет прав для отмены собрания.", ephemeral=True)
                return

            # ⏳ Убираем кнопки, редактируя сообщение
            if interaction.message:
                await interaction.message.edit(view=None)

            channel = self.cog.bot.get_channel(self.cog.channel_id)
            if channel:
                results = f"**Собрания на этой неделе не будет. Те, кто проголосовал *ЗА*,\nпросьба обратиться к руководству и задать вопрос,\nили задать его здесь: {self.cog.flood_sai_link}**"
                embed = discord.Embed(title=f"{self.cog.custom_ding} Итоги голосования:", description=results, color=discord.Color.blue())
                embed.set_footer(text="Спасибо за внимание, до новых встреч! 🤝")
                await channel.send(embed=embed)
                await interaction.response.send_message("✅ Собрание отменено.", ephemeral=True)
        except Exception as error:
            print(f"Произошла ошибка: {error}")



class MeetingModal(discord.ui.Modal):
    # """Модальное окно для выбора дня и времени собрания"""

    def __init__(self, cog):
        super().__init__(title="Запланировать собрание")  # ✅ Заголовок модального окна
        self.cog = cog

        self.day = discord.ui.TextInput(
            label="День собрания",
            placeholder="Например: Пятница",
            required=True
        )
        self.add_item(self.day)  # ✅ Добавляем поле ввода

        self.time = discord.ui.TextInput(
            label="Время собрания",
            placeholder="Например: 15:00",
            required=True
        )
        self.add_item(self.time)  # ✅ Добавляем поле ввода

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # """Отправляет сообщение о запланированном собрании"""
            channel = self.cog.bot.get_channel(self.cog.channel_id)
            if channel:
                desc = f"**День собрания:** _{self.day}_\n"
                desc += f"**Время собрания:** _{self.time}_ по МСК\n\n"
                desc += "**Просьба поставить реакцию внизу, кто будет, а кто нет!**"
                embed = discord.Embed(description=desc, color=discord.Color.blue())
                embed.set_footer(text="Спасибо за внимание, до встречи на собрании! 🤝")
                msg = await channel.send(f"||{self.cog.sai_role_mention}||\n## Собрание на этой неделе *__состоится!__*", embed=embed)
                await msg.add_reaction(self.cog.custom_yes)
                await msg.add_reaction(self.cog.custom_no)
                await interaction.response.send_message(f"{self.cog.custom_yes} Собрание запланировано!", ephemeral=True)
        except Exception as error:
            print(f"Произошла ошибка: {error}")


async def setup(bot):
    await bot.add_cog(Meetings(bot))
