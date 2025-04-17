import discord
from discord.ext import commands, tasks
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import aiofiles
import asyncio
import pytz
import re
from datetime import datetime
from discord.ui import Button, View, Modal, TextInput
from discord.utils import get
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import gspread_asyncio
from google.oauth2.service_account import Credentials
from gspread_asyncio import AsyncioGspreadClientManager

# Поиск   
async def extract_name_from_app(full_name: str):
    """Извлекает имя и фамилию из строки, убирая разделители и числа."""
    full_name = re.sub(r'\s*[|/\\]\s*', ' ', full_name)  # Убираем | / \
    full_name = re.sub(r'\s+\b[Ii]\b\s+', ' ', full_name)  # Убираем I/l, если они стоят отдельно
    full_name = re.sub(r'\d+', '', full_name).strip()  # Убираем цифры

    words = [word for word in full_name.split() if word.isalpha()]  # Оставляем только буквы
    return " ".join(words[:2]) if len(words) >= 2 else ""  # Берем имя + фамилию

async def extract_name_from_nick(nick: str):
    """Удаляет префиксы, лишние разделители, I, l и оставляет только имя + фамилию."""
    
    # Удаляем все возможные префиксы (Cur SAI, Head SAI, Ass.Shr. SAI, D.Head SAI и т. д.)
    nick = re.sub(r'^(Cur.|Head.|Inst|H\.Inst|Ass\.Shrf\.|D\.Head.|Cur|Head|Inst.|H\.Inst.|Ass\.Shr\.|D\.Head|SAI|SA)\s+', '', nick).strip()

    # Если после удаления всё ещё есть "SAI" или "SA", убираем их
    nick = re.sub(r'\b(SAI|SA)\b', '', nick).strip()

    # Убираем "I" или "l", если они стоят отдельно
    nick = re.sub(r'\b[IiLl]\b', '', nick).strip()

    # Убираем разделители (|, /, \), заменяя их на пробел
    nick = re.sub(r'\s*[|/\\]+\s*', ' ', nick).strip()

    # Убираем двойные "II", "I I", "ll", "l l"
    nick = re.sub(r'\b[Ii]{2}\b|\b[Ii]\s+[Ii]\b|\b[Ll]{2}\b|\b[Ll]\s+[Ll]\b', '', nick).strip()

    # Удаляем ID (числа в конце)
    nick = re.sub(r'\s*\d+$', '', nick).strip()

    # Убираем дублирующиеся слова
    words = nick.split()
    unique_words = []
    for word in words:
        if word not in unique_words:
            unique_words.append(word)

    return " ".join(unique_words[:2]) if len(unique_words) >= 2 else ""  # Берём только имя и фамилию

async def find_user_by_name(guild, name_status):
    exam_name = await extract_name_from_app(name_status)  # Извлекаем имя и фамилию из заявки
    
    if not exam_name:
        return None  # Если в заявке нет валидного имени, сразу возвращаем None

    for member in guild.members:
        discord_name = await extract_name_from_nick(member.display_name)  # Извлекаем имя и фамилию из ника в Discord
        
        if discord_name.lower() == exam_name.lower():
            return member  # Если нашли совпадение, возвращаем объект участника
    
    return None  # Если не нашли, возвращаем None

async def extract_name_and_id(nick: str):
    """Очищает ник от префиксов, убирает разделители и возвращает (имя, ID)"""

    # Убираем разделители (| / \) → пробел
    nick = re.sub(r'\s*[\|/\\]+\s*', ' ', nick)

    # Удаляем одиночные "I", "l" (отдельно стоящие, как разделители)
    nick = re.sub(r'\b[IiLl]\b', '', nick).strip()

    # Удаляем префиксы где угодно
    nick = re.sub(
        r'\b(Cur|Head|D\.?Head|Inst|Inst\.?|H\.?Inst|Ass\.?Shrf?|SAI|SA)\b\.?', '', 
        nick, 
        flags=re.IGNORECASE
    )

    # Удаляем лишние пробелы
    nick = re.sub(r'\s+', ' ', nick).strip()

    # Извлекаем ID
    parts = nick.rsplit(' ', 1)
    if len(parts) == 2 and parts[1].isdigit():
        name = parts[0]
        static = parts[1]
    else:
        name = nick
        static = "Нет ID"

    # Убираем дублирующиеся слова
    words = name.split()
    unique_words = []
    for word in words:
        if word not in unique_words:
            unique_words.append(word)

    return " ".join(unique_words), static


async def load_config():
    async with aiofiles.open('config.json', 'r', encoding='utf-8') as f:
        config_data = await f.read()
    return json.loads(config_data)

class Exams(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = self.init_gspread()
        self.sheet = None
        self.channel = None
        self.role_mention = None
        self.role_id = None
        self.head_sai = None
        self.exam_link = None
        self.results_link = None
        self.active_sessions = {}

    def get_msk_time(self):
        """Возвращает текущее московское время."""
        tz_moscow = pytz.timezone('Europe/Moscow')
        return datetime.now(tz_moscow).strftime("%H:%M")

    
    def init_gspread(self):
        # """Подключаемся к Google Sheets"""
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"⚠️ Ошибка подключения к Google Sheets: {e}")
            return None
    
    
    async def load_config(self):
        # """Загружает конфигурацию из config.json"""
        async with aiofiles.open('config.json', 'r', encoding='utf-8') as f:
            config_data = await f.read()
        
        global config
        config = json.loads(config_data)

        channel_id = config["channel_id"]  # Преобразуем в int
        await self.bot.wait_until_ready()  # ✅ Ждём, пока бот загрузит данные

        self.channel = self.bot.get_channel(channel_id)
        self.role_mention = config["role_mention"]
        self.role_id = config["role_id"]
        self.head_sai = config["head_sai"]
        self.exam_link = config["exam_link"]
        self.results_link = config["results_link"]
        self.results_id = config["results_id"]

        # 🎭 Загружаем кастомные эмодзи
        self.custom_yes = config["custom_yes"]
        self.custom_no = config["custom_no"]
        self.custom_wait = config["custom_wait"]
        self.custom_ding = config["custom_ding"]

        try:
            self.sheet = self.client.open_by_key(config["sheet_id"]).sheet1
            print("✅ Google-таблица загружена успешно!")
        except Exception as e:
            print(f"❌ Ошибка загрузки таблицы: {e}")

        if self.channel is None:
            print(f"Канал с ID {config['channel_id']} не найден.")

        self.check_new_rows.start()

    @tasks.loop(seconds=50)
    async def check_new_rows(self):
       # """Проверяет новые заявки в Google Sheets каждые 50 секунд"""
        heartbeat_counter = 0  

        # Если таблица ещё не подключена, пробуем подключиться
        if self.sheet is None:
            print("🔄 Переподключение к Google Sheets...")
            self.sheet = self.client.open_by_key(config["sheet_id"]).sheet1

        while True:
            try:
                if self.sheet is None:
                    print("🔴 Ошибка: Нет соединения с Google Sheets! Переподключаемся...")
                    self.sheet = self.client.open_by_key(config["sheet_id"]).sheet1
                    await asyncio.sleep(10)
                    continue  

                # Проверяем соединение раз в 5 минут
                if heartbeat_counter >= 240:
                    print(f"{self.get_msk_time()} 💓 Heartbeat: Проверяем соединение с Google Sheets...")
                    try:
                        _ = self.sheet.get_all_values()
                        print(f"{self.get_msk_time()} ✔ Heartbeat: соединение прекрасное, продолжаем работу...")
                    except gspread.exceptions.APIError:
                        print(f"{self.get_msk_time()} ⚠️ Heartbeat: соединение потеряно, переподключаемся...")
                        self.sheet = self.client.open_by_key(config["sheet_id"]).sheet1  

                    heartbeat_counter = 0  

                # Получаем данные
                data = self.sheet.get_all_values()
                for i, row in enumerate(data[1:], start=2):  
                    if len(row) < 4:  
                        continue

                    text1, text2, status = row[1].strip(), row[2].strip(), row[3].strip().lower()

                    if text1 and text2 and status in ["", "false"]:  
                        await self.send_to_discord(text1, text2)
                        self.sheet.update_cell(i, 4, "true")  

                heartbeat_counter += 1  
                await asyncio.sleep(50)
            
            
            
            except Exception as e:
                print(f"❌ Ошибка: {e}")
                await asyncio.sleep(10)  # Пауза при ошибке

    async def send_to_discord(self, text1, text2):
        """Создаёт `ExamSession` и отправляет в канал"""
        session = ExamSession(self, text1, text2)
        await session.send_exam(self.channel)

    @commands.Cog.listener()
    async def on_ready(self):
        # Теперь мы вызываем load_config в on_ready, после того как бот полностью инициализируется
        await self.load_config()

class ExamSession:
    def __init__(self, cog, text1, text2):
        self.cog = cog
        self.text1 = text1
        self.text2 = text2
        self.exam_type = text2
        self.msg = None
        self.accepted_by = None
        self.candidate_mention = ""

        # Начальные кнопки
        self.initial_view = View(timeout=None)
        accept_btn = Button(label="Принять экзамен", style=discord.ButtonStyle.green, emoji=self.cog.custom_yes)
        accept_btn.callback = self.on_accept_exam
        cancel_btn = Button(label="Отклонить экзамен", style=discord.ButtonStyle.danger, emoji=self.cog.custom_no)
        cancel_btn.callback = self.on_cancel_exam
        self.initial_view.add_item(accept_btn)
        self.initial_view.add_item(cancel_btn)

        # Кнопки после принятия
        self.finish_view = View(timeout=None)
        finish_btn = Button(label="Завершить экзамен", style=discord.ButtonStyle.green, emoji=self.cog.custom_yes)
        finish_btn.callback = self.on_finish_exam
        no_show_btn = Button(label="Не явился", style=discord.ButtonStyle.danger, emoji=self.cog.custom_no)
        no_show_btn.callback = self.on_no_show
        self.finish_view.add_item(finish_btn)
        self.finish_view.add_item(no_show_btn)

        # Финальная кнопка
        self.processed_view = View(timeout=None)
        processed_btn = Button(label="Экзамен обработан", style=discord.ButtonStyle.secondary, disabled=True)
        self.processed_view.add_item(processed_btn)

    
    async def send_dm_to_candidate(self, kind: str, *, reason=None, instructor=None):
        # """
        # kind: 'start' | 'cancelled' | 'no_show'
        # reason: причина отмены (для 'cancelled')
        # instructor: упоминание экзаменатора
        # """
        member = await find_user_by_name(self.msg.guild, self.text1)
        if not member:
            return

        try:
            if kind == "start":
                msg = (
                    f"{self.cog.custom_ding} Приветствую! Вас ожидают на **{self.exam_type}**.\n"
                    f"Инструктор будет ждать в голосовом канале: {self.cog.exam_link}\n"
                    f"Пожалуйста, зайдите в течении **5 минут**."
                )
            elif kind == "cancelled":
                msg = (
                    f"{self.cog.custom_ding} Ваш **{self.exam_type}** был отменён.\n"
                    f"**Причина:** *{reason}*\n"
                    f"**Отменил(а)**: {instructor or 'Инструктор SAI'}"
                )
            elif kind == "no_show":
                msg = (
                    f"{self.cog.custom_no} Вы не явились на **{self.exam_type}**.\n"
                    f"Экзамен был отменён. Пожалуйста, будьте более внимательны.\n"
                    f"Чтобы попасть на **{self.exam_type}** подайте заявку ещё раз."
                )
            else:
                return

            await member.send(msg)

        except discord.Forbidden:
            print(f"📪 Не удалось отправить ЛС {member.display_name}")

    
    
    async def send_exam(self, channel):
        embed = discord.Embed(title="Новая Запись на экзамен!", color=0x00ff00)
        embed.add_field(name="Имя Фамилия | Статик", value=self.text1, inline=False)
        embed.add_field(name="Какой экзамен хотите сдавать?", value=self.text2, inline=False)
        embed.set_footer(text=f"Сообщение отправлено в {self.cog.get_msk_time()} (МСК)")

        self.msg = await channel.send(content=self.cog.role_mention, embed=embed, view=self.initial_view)

    async def on_accept_exam(self, interaction):
        await interaction.response.defer()
        try:
            # ✅ Получаем роли пользователя
            member = interaction.user
            user_roles = {role.id for role in member.roles}  

            # ✅ Разрешённые роли (может быть списком или числом)
            allowed_roles = set(self.cog.role_id) if isinstance(self.cog.role_id, list) else {self.cog.role_id}
            admin_roles = set(self.cog.head_sai) if isinstance(self.cog.head_sai, list) else {self.cog.head_sai}

            # ✅ Проверяем, есть ли хотя бы одна из ролей
            if not (allowed_roles & user_roles or admin_roles & user_roles):
                await interaction.followup.send(f"{self.cog.custom_no} У вас нет прав для принятия экзамена.", ephemeral=True)
                return
            

            exam_candidate = await find_user_by_name(interaction.guild, self.text1)
            self.candidate_mention = exam_candidate.mention if exam_candidate else ""

            if not self.candidate_mention:
                # Отправляем уведомление о причине отмены
                await interaction.followup.send(
                    f"{self.cog.custom_no} Экзамен был отменён. Возможные причины: *неверно введён никнейм в заявке, участник не находится на сервере.*\n"
                    f"-# *Отменён инструктором {interaction.user.mention}*."
                )

                await self.msg.edit(view=self.processed_view)
                return

            self.accepted_by = interaction.user.id
            await self.msg.edit(view=self.finish_view)
            await self.msg.edit(content=f"{self.cog.role_mention} | Экзаменатор: {interaction.user.mention}")

            await self.send_dm_to_candidate("start")
            await interaction.followup.send(f"{self.cog.custom_yes} Сообщение о приглашении на экзамен было успешно отправлено. Заходите в экзаменационную и ожидайте.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

    async def on_finish_exam(self, interaction: discord.Interaction):
        try:
            # Проверяем, может ли пользователь завершить экзамен
            member = interaction.guild.get_member(interaction.user.id)
            exam_admin_role = discord.utils.get(member.roles, id=self.cog.head_sai)

            if interaction.user.id != self.accepted_by and not exam_admin_role:
                await interaction.response.send_message(f"{self.cog.custom_no} Вы не можете завершить этот экзамен.", ephemeral=True)
                return

            exam_candidate = await find_user_by_name(interaction.guild, self.text1)
            self.candidate_mention = exam_candidate.mention if exam_candidate else ""

            for item in self.finish_view.children:
                item.disabled = True

            await interaction.response.send_modal(
                ExamCompletionModal(
                    self, exam_candidate, self.candidate_mention, self.finish_view,
                    self.cog.results_link, self.exam_type, interaction.guild,
                    self.text1, self.text2, self.cog
                )
            )

            await self.msg.edit(view=self.processed_view)

        except Exception as e:
            print(f"❌ Ошибка в on_finish_exam: {e}")
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

    async def on_no_show(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()

            member = interaction.guild.get_member(interaction.user.id)
            exam_admin_role = discord.utils.get(member.roles, id=self.cog.head_sai)

            if interaction.user.id != self.accepted_by and not exam_admin_role:
                await interaction.response.send_message(f"{self.cog.custom_no} Только экзаменатор может отметить неявку.", ephemeral=True)
                return

            exam_candidate = await find_user_by_name(interaction.guild, self.text1)
            self.candidate_mention = exam_candidate.mention if exam_candidate else ""

            for item in self.finish_view.children:
                item.disabled = True

            await self.msg.edit(view=self.finish_view)

            await self.msg.edit(view=self.processed_view)

            await self.send_dm_to_candidate("no_show")
            await interaction.followup.send(f"{self.cog.custom_yes} Сообщение человеку было успешно отправлено.", ephemeral=True)

        except Exception as e:
            print(f"❌ Ошибка в on_no_show: {e}")
            await interaction.response.send_message(f"❌ Произошла ошибка: {e}", ephemeral=True)

    async def on_cancel_exam(self, interaction: discord.Interaction):
        try:
            member = interaction.guild.get_member(interaction.user.id)
            user_roles = {role.id for role in member.roles}

            allowed_roles = set()
            if isinstance(self.cog.role_id, list):
                allowed_roles.update(self.cog.role_id)
            else:
                allowed_roles.add(self.cog.role_id)

            if isinstance(self.cog.head_sai, list):
                allowed_roles.update(self.cog.head_sai)
            else:
                allowed_roles.add(self.cog.head_sai)

            if not allowed_roles & user_roles:
                await interaction.response.send_message(f"{self.cog.custom_no} У вас нет прав на отклонение экзамена.", ephemeral=True)
                return

            await interaction.response.send_modal(CancelExamModal(self, self.cog))
            await self.msg.edit(view=self.processed_view)


        except Exception as e:
            print(f"❌ Ошибка в on_cancel_exam: {e}")
            await interaction.response.send_message(f"❌ Произошла ошибка: {e}", ephemeral=True)

class ExamCompletionModal(Modal):
    def __init__(self, exam_session, exam_candidate, candidate_mention, finish_view, results_link, exam_type, guild, text1, text2, cog):
        super().__init__(title="Завершение экзамена")
        self.exam_session = exam_session
        self.exam_candidate = exam_candidate
        self.candidate_mention = candidate_mention
        self.finish_view = finish_view
        self.results_link = results_link
        self.exam_type = exam_type  
        self.guild = guild
        self.text1 = text1
        self.text2 = text2
        self.cog = cog

        # Поле ввода результата
        self.result = TextInput(label="Результат", placeholder="Сдал(а) / Не сдал(а)", required=True)
        self.add_item(self.result)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()  # Закрываем модальное окно
            exam_result = self.result.value.capitalize()

            # Получаем канал результатов
            results_channel = interaction.guild.get_channel(int(self.exam_session.cog.results_id))

            if not results_channel:
                await interaction.followup.send("Ошибка: канал результатов не найден!", ephemeral=True)
                return

            # Определяем никнеймы
            self.exam_candidate = await find_user_by_name(self.guild, self.text1)
            if self.exam_candidate:
                self.candidate_mention = self.exam_candidate.mention
            else:
                self.candidate_mention = "Не найден"

            nick_sai, static_sai = await extract_name_and_id(interaction.user.display_name)
            nick_sa, static_sa = await extract_name_and_id(self.exam_candidate.display_name)

            if results_channel:
                await results_channel.send(
                    f"1. {interaction.user.mention} | {nick_sai} | {static_sai} \n"
                    f"2. {self.exam_candidate.mention} | {nick_sa} | {static_sa} \n"
                    f"3. {exam_result} {self.exam_type.lower()} \n"
                )
            else:
                await interaction.response.send_message("Ошибка: канал результатов не найден!", ephemeral=True)
                return

        
        except Exception as e:
            print(f"❌ Ошибка в on_submit: {e}")
            await interaction.followup.send(f"❌ Произошла ошибка: {e}", ephemeral=True)

class CancelExamModal(Modal):
    def __init__(self, exam_session, cog):
        self.cog = cog
        super().__init__(title="Отмена экзамена")
        self.exam_session = exam_session
        self.reason = TextInput(label="Причина отмены", placeholder="Пример: Неверно введён никнейм.", required=True)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()  # Закрываем модальное окно

            # Меняем кнопки на "Экзамен обработан"
            await self.exam_session.msg.edit(view=self.exam_session.processed_view)


            await self.exam_session.send_dm_to_candidate("cancelled", reason=self.reason.value, instructor=interaction.user.mention)
            await interaction.followup.send(f"{self.cog.custom_yes} Сообщение об отмене было успешно отправлено человеку.", ephemeral=True)


        except Exception as e:
            print(f"❌ Ошибка в on_submit: {e}")
            await interaction.followup.send(f"❌ Произошла ошибка: {e}", ephemeral=True)

async def setup(bot):
    cog = Exams(bot)
    await bot.add_cog(cog)  # Загружаем ког