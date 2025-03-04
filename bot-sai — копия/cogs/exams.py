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

async def load_config():
    async with aiofiles.open('config.json', 'rb') as f:
        config_data = await f.read()
    return json.loads(config_data)

# Поиск   
def extract_name_from_app(full_name: str):
    """Извлекает имя и фамилию из строки, игнорируя разделители и числа, но не удаляя I и l внутри имени."""
    
    # Разбиваем строку по разделителям (|, /, \), но НЕ удаляем I и l внутри слов
    full_name = re.sub(r'\s*[|/\\]\s*', ' ', full_name)  # Убираем |, /, \ как разделители
    full_name = re.sub(r'\s+[Il]\s+', ' ', full_name)  # Убираем I и l только если они окружены пробелами
    
    # Удаляем числа
    full_name = re.sub(r'\d+', '', full_name).strip()

    # Разбиваем строку на слова, оставляя только буквы
    words = [word for word in full_name.split() if word.isalpha()]

    # Возвращаем имя и фамилию (первые два слова)
    return " ".join(words[:2]) if len(words) >= 2 else ""

def extract_name_from_nick(nick: str):
    # Удаляем стандартные префиксы (например, SAI, SA, D.Head и т. д.)
    nick = re.sub(r'^(SAI|SA|D\.Head|Head|Cur\.|Ass\.Shr\.)\s+', '', nick).strip()
    # Убираем оставшиеся префиксы до первого разделителя
    nick = re.sub(r'^[^|/\\]*[|/\\]\s*', '', nick).strip()
    # Заменяем разделители (|, /, \) на пробелы
    nick = re.sub(r'\s*[|/\\]+\s*', ' ', nick).strip()
    # Убираем "I" в начале строки или как разделитель
    nick = re.sub(r'^I\s+|(?<=\s)I(?=\s)', '', nick).strip()
    # Удаляем ID (цифры в конце)
    nick = re.sub(r'\s+\d+$', '', nick).strip()

    return nick

async def find_user_by_name(guild, name_status):
    exam_name = extract_name_from_app(name_status)  # Извлекаем имя и фамилию из заявки
    
    if not exam_name:
        return None  # Если в заявке нет валидного имени, сразу возвращаем None

    for member in guild.members:
        discord_name = extract_name_from_nick(member.display_name)  # Извлекаем имя и фамилию из ника в Discord
        
        if discord_name.lower() == exam_name.lower():
            return member  # Если нашли совпадение, возвращаем объект участника
    
    return None  # Если не нашли, возвращаем None

async def extract_name_and_id(nick: str):

    # Удаляем стандартные префиксы (например, SAI, SA, D.Head и т. д.)
    nick = re.sub(r'^(SAI|SA|D\.Head|Head|Cur\.|Ass\.Shr\.)\s+', '', nick).strip()
    # Убираем оставшиеся префиксы до первого разделителя
    nick = re.sub(r'^[^|/\\]*[|/\\]\s*', '', nick).strip()
    # Заменяем разделители (|, /, \) на пробелы
    nick = re.sub(r'\s*[|/\\]+\s*', ' ', nick).strip()
    # Убираем "I" в начале строки или как разделитель
    nick = re.sub(r'^I\s+|(?<=\s)I(?=\s)', '', nick).strip()
    # Удаляем ID (цифры в конце)
    # nick = re.sub(r'\s+\d+$', '', nick).strip()

    cleaned_nick = nick.rsplit(' ', 1)
    name = cleaned_nick[0].strip()
    static = cleaned_nick[1].strip()
    return name, static


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
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        return gspread.authorize(creds)

    async def load_config(self):
        async with aiofiles.open('config.json', 'rb') as f:
            config_data = await f.read()
        
        global config
        config = json.loads(config_data)

        self.channel = self.bot.get_channel(config["channel_id"])
        self.role_mention = config["role_mention"]
        self.role_id = config["role_id"]
        self.head_sai = config["head_sai"]
        self.exam_link = config["exam_link"]
        self.results_link = config["results_link"]
        self.results_id = config["results_id"]
        global head_sai
        head_sai = config["head_sai"]

        # 🎭 Загружаем кастомные эмодзи
        self.custom_yes = config["custom_yes"]
        self.custom_no = config["custom_no"]
        self.custom_wait = config["custom_wait"]

        try:
            self.sheet = self.client.open_by_key(config["sheet_id"]).sheet1
            print("✅ Google-таблица загружена успешно!")
        except Exception as e:
            print(f"❌ Ошибка загрузки таблицы: {e}")

        if self.channel is None:
            print(f"Канал с ID {config['channel_id']} не найден.")

        self.check_new_rows.start()

    @tasks.loop(seconds=60)
    async def check_new_rows(self):
        if not self.sheet or not self.channel:
            return

        try:
            data = self.sheet.get_all_values()
            for i, row in enumerate(data[1:], start=2):
                if len(row) < 4:
                    continue

                text1, text2, status = row[1].strip(), row[2].strip(), row[3].strip().lower()

                if text1 and text2 and status in ["", "false"]:
                    await self.send_to_discord(text1, text2)
                    self.sheet.update_cell(i, 4, "TRUE")

        except Exception as e:
            print(f"❌ Ошибка мониторинга таблицы: {e}")

    async def send_to_discord(self, text1, text2):
        session = ExamSession(self, text1, text2)
        await session.send_exam(self.channel)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_config()

class ExamSession:
    def __init__(self, cog, text1, text2):
        self.cog = cog
        self.text1 = text1
        self.text2 = text2
        self.exam_type = text2
        self.view = View()
        self.finish_view = View()
        self.msg = None

    async def send_exam(self, channel):
        embed = discord.Embed(title="Новая Запись на экзамен!", color=0x00ff00)
        embed.add_field(name="Имя Фамилия | Статик", value=self.text1, inline=False)
        embed.add_field(name="Какой экзамен хотите сдавать?", value=self.text2, inline=False)
        embed.set_footer(text=f"Сообщение отправлено в {self.cog.get_msk_time()} (МСК)")

        button = Button(label="Принять экзамен", style=discord.ButtonStyle.green)
        button.callback = self.on_accept_exam
        cancel_button = Button(label="Отменить экзамен", style=discord.ButtonStyle.danger)
        cancel_button.callback = self.on_cancel_exam

        self.view.add_item(button)
        self.view.add_item(cancel_button)

        self.msg = await channel.send(content=self.cog.role_mention, embed=embed, view=self.view)

    async def on_accept_exam(self, interaction):
        await interaction.response.defer()  # Ожидаем обработку

        exam_candidate_name = self.text1  
        exam_candidate = await find_user_by_name(interaction.guild, exam_candidate_name)

        # Проверяем, найден ли кандидат
        if exam_candidate:
            candidate_mention = exam_candidate.mention
            self.candidate_mention = candidate_mention  
        else:
            candidate_mention = ""
            self.candidate_mention = ""

        # Проверяем, есть ли у пользователя разрешенные роли
        allowed_roles = {self.cog.role_id, self.cog.head_sai}  # Используем self.cog.*
        user_roles = {role.id for role in interaction.user.roles}  

        if not allowed_roles & user_roles:  
            await interaction.followup.send("У вас нет прав для принятия экзамена.", ephemeral=True)
            return

        if self.candidate_mention == "":
            await interaction.followup.send("Ник введён неверно. Отклоните заявку и попросите кадета правильно ввести ник в заявке.", ephemeral=True)
            return

        # Делаем кнопки недоступными после принятия экзамена
        for item in self.view.children:
            if isinstance(item, discord.ui.Button):
                self.view.remove_item(item)

        # Обновляем сообщение с отключенными кнопками
        await interaction.message.edit(view=self.view)

        # Сохраняем ID пользователя, принявшего экзамен
        self.accepted_by = interaction.user.id

        # Создаём кнопки для завершения экзамена
        finish_button = Button(label="Завершить экзамен", style=discord.ButtonStyle.green)
        finish_button.callback = self.on_finish_exam  

        no_show_button = Button(label="Не пришёл(а)", style=discord.ButtonStyle.danger)
        no_show_button.callback = self.on_no_show  

        self.finish_view.add_item(finish_button)
        self.finish_view.add_item(no_show_button)

        await self.msg.add_reaction(self.cog.custom_wait)

        # Отправляем сообщение с кнопками
        await interaction.followup.send(
            f"{interaction.user.mention} принял экзамен. Экзаменуемый, {candidate_mention} просьба войти в: {self.cog.exam_link}. "
            f"Инструктор будет ждать Вас 5 минут.", view=self.finish_view)

    async def on_finish_exam(self, interaction: discord.Interaction):
        try:
            # Проверяем, может ли пользователь завершить экзамен
            member = interaction.guild.get_member(interaction.user.id)
            exam_admin_role = discord.utils.get(member.roles, id=self.cog.head_sai)

            if interaction.user.id != self.accepted_by and not exam_admin_role:
                await interaction.response.send_message("Вы не можете завершить этот экзамен.", ephemeral=True)
                return

            exam_candidate_name = self.text1
            exam_candidate = await find_user_by_name(interaction.guild, exam_candidate_name)

            if exam_candidate:
                candidate_mention = exam_candidate.mention
                self.candidate_mention = candidate_mention
            else:
                candidate_mention = ""
                self.candidate_mention = ""

            # Отключаем кнопки перед отправкой модального окна
            for item in self.finish_view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            await interaction.message.edit(view=self.finish_view)

            await self.msg.clear_reactions()
            await self.msg.add_reaction(self.cog.custom_yes)

            # Отправляем модальное окно
            await interaction.response.send_modal(
                ExamCompletionModal(
                    self, exam_candidate, self.candidate_mention, self.finish_view, self.cog.results_link, self.exam_type, interaction.guild, self.text1, self.text2
                )
            )

        except Exception as e:
            print(f"❌ Ошибка в on_finish_exam: {e}")
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

    async def on_no_show(self, interaction: discord.Interaction):
        try:
            member = interaction.guild.get_member(interaction.user.id)
            exam_admin_role = discord.utils.get(member.roles, id=self.cog.head_sai)

            if interaction.user.id != self.accepted_by and not exam_admin_role:
                await interaction.response.send_message("Только экзаменатор может отметить неявку.", ephemeral=True)
                return

            exam_candidate_name = self.text1  
            exam_candidate = await find_user_by_name(interaction.guild, exam_candidate_name)

            if exam_candidate:
                candidate_mention = exam_candidate.mention
                self.candidate_mention = candidate_mention  
            else:
                self.candidate_mention = ""

            # Отключаем кнопки
            for item in self.finish_view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            await interaction.message.edit(view=self.finish_view)  # Обновляем сообщение с отключёнными кнопками

            await self.msg.clear_reactions()
            await self.msg.add_reaction(self.cog.custom_no)

            await interaction.response.send_message(f"{candidate_mention} не явился на экзамен. Экзамен отменён.")

        except Exception as e:
            print(f"❌ Ошибка в on_no_show: {e}")
            await interaction.response.send_message(f"❌ Произошла ошибка: {e}", ephemeral=True)

    async def on_cancel_exam(self, interaction: discord.Interaction):
        # Проверяем, есть ли у пользователя разрешенные роли
        allowed_roles = {self.cog.role_id, self.cog.head_sai}  # Используем self.cog.*
        user_roles = {role.id for role in interaction.user.roles}  

        if not allowed_roles & user_roles:  
            await interaction.followup.send("У вас нет прав для принятия экзамена.", ephemeral=True)
            return

        # Открываем модальное окно для отмены экзамена
        await interaction.response.send_modal(CancelExamModal(self))



class ExamCompletionModal(Modal):
    def __init__(self, exam_session, exam_candidate, candidate_mention, finish_view, results_link, exam_type, guild, text1, text2):
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

            # Отключаем кнопки
            for item in self.finish_view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            await interaction.message.edit(view=self.finish_view)
            await interaction.followup.send(f"{interaction.user.mention} завершил экзамен. Результаты можно узнать в канале {self.exam_session.cog.results_link}")
        
        except Exception as e:
            print(f"❌ Ошибка в on_submit: {e}")
            await interaction.followup.send(f"❌ Произошла ошибка: {e}", ephemeral=True)


class CancelExamModal(Modal):
    def __init__(self, exam_session):
        super().__init__(title="Отмена экзамена")
        self.exam_session = exam_session
        self.reason = TextInput(label="Причина отмены", placeholder="Пример: Неверно введён никнейм.", required=True)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        # # Проверяем, может ли пользователь отменить экзамен
        # allowed_roles = {self.exam_session.cog.role_id, self.exam_session.cog.head_sai}
        # user_roles = {role.id for role in interaction.user.roles}

        # if allowed_roles & user_roles:
        #     await interaction.response.send_message("❌ У вас нет прав для отмены экзамена.", ephemeral=True)
        #     return

        # Отключаем кнопки в основном сообщении
        for item in self.view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await self.exam_session.msg.edit(view=self.exam_session.view)  # Обновляем сообщение заявки

        await self.exam_session.msg.clear_reactions()
        await self.exam_session.msg.add_reaction(self.exam_session.cog.custom_no)  # ❌ Добавляем кастомный эмодзи

        await interaction.response.send_message(
            f"❌ Экзамен был отменён по следующей причине: **{self.reason.value}**\n"
            f"-# *Отменён инструктором {interaction.user.mention}*."
        )


async def setup(bot):
    await bot.add_cog(Exams(bot))
