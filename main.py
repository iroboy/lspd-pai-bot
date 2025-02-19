import gspread
from oauth2client.service_account import ServiceAccountCredentials
import discord
from discord.utils import get
from discord.ext import commands
import json
import asyncio
from discord.ui import Button, View
import aiofiles
import pytz
from datetime import datetime


# Получаем время МСК
def get_msk_time():
    tz_moscow = pytz.timezone('Europe/Moscow')
    msk_time = datetime.now(tz_moscow).strftime("%Y-%m-%d %H:%M:%S")
    return msk_time

# Настройка Discord бота
intents = discord.Intents.default()
# intents.members = True  # Необходимо для поиска пользователей в гильдии
intents.messages = True  # Включаем намерение для сообщений
intents.message_content = True  # Включаем намерение для доступа к содержимому сообщений
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Запуск бота
@bot.event
async def on_ready():
    print(f'Бот запущен как {bot.user}')
    # Загрузка конфигурации
    config = await load_config()
    channel_id = config["channel_id"]
    channel = bot.get_channel(channel_id)
    role_mention = config["role_mention"]
    role_id = config["role_id"]  # Получаем ID роли из конфигурации
    global head_sai, sheet_id_
    head_sai = config["head_sai"]
    sheet_id_ = config["sheet_id"]

    if channel is None:
        print(f"Канал с ID {channel_id} не найден. Проверьте настройки.")
        return

    guild = channel.guild  # Получаем объект гильдии (сервера)

    # Запуск мониторинга Google Sheets
    await check_new_rows(channel, config["sheet_id"], config["exam_link"], config["results_link"], role_mention, role_id, guild)

# Асинхронная загрузка конфигурации
async def load_config():
    async with aiofiles.open('config.json', 'r') as f:
        config_data = await f.read()
    return json.loads(config_data)


# Функция для авторизации и получения данных из Google Sheets
def get_google_sheets_data(sheet_id):

    """Функция подключения к Google Sheets и получения объекта `sheet`."""
    global sheet  # Делаем переменную глобальной

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        print("✅ Успешное подключение к Google Sheets!")
        return sheet
    except Exception as e:
        print(f"❌ Ошибка при подключении к таблице: {e}")
        return None

# Мониторинг Таблицы
async def check_new_rows(channel, sheet_id, exam_link, results_link, role_mention, role_id, guild):
        global last_row_count, sheet
        await bot.wait_until_ready()  # Ждём, пока бот полностью запустится

        sheet = get_google_sheets_data(sheet_id_)  # Подключаемся к таблице
        if sheet:
            last_row_count = len(sheet.get_all_values())  # Запоминаем количество строк

        while not bot.is_closed():
            if sheet:
                try:
                    data = sheet.get_all_values()
                    row_count = len(data)

                    if row_count > last_row_count:
                        new_rows = data[last_row_count:]  # Получаем только новые строки
                        last_row_count = row_count  # Обновляем количество строк

                        for row in new_rows:
                            await send_to_discord(row, channel, exam_link, results_link, role_mention, role_id, guild)



                except Exception as e:
                    print(f"❌ Ошибка при чтении таблицы: {e}")

            await asyncio.sleep(10)  # Проверяем каждые 10 секунд

# Асинхронное форматирование данных в Discord Embed

async def format_embed(data, msk_time):
    embed = discord.Embed(title="Новая Запись на экзамен!", color=0x00ff00)
    global last_row
    if data:
  # Передаем строку целиком
        last_row = data
        embed.add_field(name="Имя Фамилия | Статик", value=last_row[1], inline=False)  # Имя, фамилия, статик экзаменуемого
        embed.add_field(name="Какой экзамен хотите сдавать?", value=last_row[2], inline=False)  # Тип экзамена
        embed.set_footer(text=f"Сообщение отправлено в {msk_time} (МСК)")  # Время отправки в МСК
    return embed



active_sessions = {}  # Храним все сессии {message_id: ExamSession}


# Отправка заявки в дискорд
async def send_to_discord(data, channel, exam_link, results_link, role_mention, role_id, guild):
    session = ExamSession(data, exam_link, results_link, role_mention, role_id, guild)
    await session.send_exam(channel)
# Класс для управления сессией экзамена
class ExamSession:
    global active_sessions
    def __init__(self, data, exam_link, results_link, role_mention, role_id, guild):
        self.data = data
        self.exam_type = data[2]  # Сохраняем тип экзамена в переменную экземпляра
        self.exam_link = exam_link
        self.results_link = results_link
        self.role_mention = role_mention
        self.role_id = role_id
        self.guild = guild
        self.view = discord.ui.View(timeout=None)
        self.finish_view = discord.ui.View()
        self.accepted_by = None
        self.candidate_mention = ""
        self.msg = None

    async def send_exam(self, channel):
        global msg
        msk_time = get_msk_time()  # Получаем текущее время в МСК
        embed = await format_embed(self.data, msk_time)

        # Создаем кнопку для принятия экзамена
        button = discord.ui.Button(label="Принять экзамен", style=discord.ButtonStyle.primary)
        button.callback = self.on_accept_exam  # Привязываем callback к кнопке

        cancel_button = discord.ui.Button(label="Отменить экзамен", style=discord.ButtonStyle.danger)

        async def cancel_exam_callback(interaction: discord.Interaction):
            # Проверяем, есть ли у пользователя роль, которая может отклонять
            role = discord.utils.get(interaction.user.roles, id=self.role_id)
            if role is None:
                await interaction.response.send_message("У вас нет прав для отклонения экзамена.", ephemeral=True)
                return
            await interaction.response.send_modal(CancelExamModal(self, self.candidate_mention, data=self.data, guild=channel.guild))  # Открываем модальное окно
            for item in self.view.children:
                if isinstance(item, discord.ui.Button):
                    self.view.remove_item(item)

            await interaction.message.edit(view=self.view)

        cancel_button.callback = cancel_exam_callback

        self.view.add_item(button)
        self.view.add_item(cancel_button)

        # Отправляем сообщение с пингом роли, вебхуком и кнопкой
        message = await channel.send(content=f"{self.role_mention}", embed=embed, view=self.view)
    
    async def on_accept_exam(self, interaction):
        # Проверяем, есть ли у пользователя роль, которая может принимать экзамен
        role = discord.utils.get(interaction.user.roles, id=self.role_id)
        if role is None:
            await interaction.response.send_message("У вас нет прав для принятия экзамена.", ephemeral=True)
            return

        # Делаем кнопку недоступной после принятия экзамена
        for item in self.view.children:
            if isinstance(item, discord.ui.Button):
                self.view.remove_item(item)

        

        # Сохраняем ID пользователя, принявшего экзамен
        self.accepted_by = interaction.user.id
        

        await interaction.response.edit_message(view=self.view)

        # Поиск экзаменуемого по имени (данные из второго столбца)
        # global exam_candidate_name
        # global candidate_mention
        exam_candidate_name = self.data[1]  # Имя, фамилия, статик экзаменуемого
        exam_candidate = await find_user_by_name(self.guild, exam_candidate_name)

        # Если пользователь найден, упоминаем его

        if exam_candidate:
            candidate_mention = exam_candidate.mention
            self.candidate_mention = candidate_mention  # Сохраняем в переменную класса
        else:
            candidate_mention = ""
            self.candidate_mention = ""

        # Создаем кнопку для завершения экзамена
        finish_button = discord.ui.Button(label="Завершить экзамен", style=discord.ButtonStyle.green)
        finish_button.callback = self.on_finish_exam  # Привязываем callback к кнопке
        no_show_button = discord.ui.Button(label="Не явился", style=discord.ButtonStyle.danger)
        no_show_button.callback = self.on_no_show  # Привязываем новый callback
        self.finish_view.add_item(finish_button)
        self.finish_view.add_item(no_show_button)

        # Отправляем сообщение о принятии экзамена с упоминанием экзаменуемого
        self.msg = await interaction.followup.send(
            f"{interaction.user.mention} принял экзамен. Экзаменуемый, {candidate_mention} просьба войти в: {self.exam_link}. Инструктор будет ждать Вас 5 минут.",view=self.finish_view)

        
        await self.msg.add_reaction("⏳")
    
    async def on_no_show(self, interaction):
        # Обработчик нажатия на кнопку 'Не явился'
        member = interaction.guild.get_member(interaction.user.id)
        exam_admin_role = get(member.roles, id=head_sai)  # Проверяем, есть ли у пользователя нужная роль

        if interaction.user.id != self.accepted_by and not exam_admin_role:
            await interaction.response.send_message("Только экзаменатор может отметить неявку.", ephemeral=True)
            return
        
        exam_candidate_name = self.data[1]  # Имя, фамилия, статик экзаменуемого
        exam_candidate = await find_user_by_name(self.guild, exam_candidate_name)

        # Если пользователь найден, упоминаем его

        if exam_candidate:
            candidate_mention = exam_candidate.mention
            self.candidate_mention = candidate_mention  # Сохраняем в переменную класса
        else:
            candidate_mention = ""
            self.candidate_mention = ""

        # Делаем обе кнопки недоступными
        for item in self.finish_view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await interaction.response.edit_message(view=self.finish_view)

        await self.msg.clear_reactions()
        await self.msg.add_reaction("❌")
        await interaction.followup.send(f"{candidate_mention} не явился на экзамен. Экзамен отменён.")

    async def on_finish_exam(self, interaction: discord.Interaction):
        member = interaction.guild.get_member(interaction.user.id)
        exam_admin_role = get(member.roles, id=head_sai)

        if interaction.user.id != self.accepted_by and not exam_admin_role:
            await interaction.response.send_message("Вы не можете завершить этот экзамен.", ephemeral=True)
            return

        exam_candidate_name = self.data[1]
        exam_candidate = await find_user_by_name(self.guild, exam_candidate_name)

        if exam_candidate:
            candidate_mention = exam_candidate.mention
            self.candidate_mention = candidate_mention
        else:
            candidate_mention = ""
            self.candidate_mention = ""

        await self.msg.clear_reactions()
        await self.msg.add_reaction("✅")

        # Передаем exam_type в ExamCompletionModal
        await interaction.response.send_modal(
            ExamCompletionModal(self, exam_candidate, self.candidate_mention, self.finish_view, self.results_link, self.exam_type)
        )


# Класс для аудита экзаменов
class ExamCompletionModal(discord.ui.Modal, title="Аудит экзамена"):
    def __init__(self, exam_session, candidate_mention, exam_candidate, finish_view, results_link, exam_type):
        super().__init__()
        self.exam_session = exam_session  # Передаем текущую сессию экзамена
        self.candidate_mention = candidate_mention  # Теперь есть!
        self.exam_candidate = exam_candidate  # Теперь есть!
        self.finish_view = finish_view
        self.results_link = results_link
        self.exam_type = exam_type

        # Поля ввода
        self.add_item(discord.ui.TextInput(label="Результат?", style=discord.TextStyle.short, placeholder="Сдал(а) / Не сдал(а)", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        config1 = await load_config()
        exam_result = self.children[0].value

        results_channel = interaction.guild.get_channel(int(config1["results_id"]))

        if results_channel:
            await results_channel.send(
                f"1. {interaction.user.mention} | {interaction.user.display_name.rsplit('|')[1].strip()} | {interaction.user.display_name.rsplit('|')[2].strip()} \n"
                f"2. {self.candidate_mention.mention} | {self.candidate_mention.display_name.rsplit('|')[1].strip()} | {self.candidate_mention.display_name.rsplit('|')[2].strip()} \n"
                f"3. {exam_result.capitalize()} {self.exam_type.lower()} \n"  # Используем self.exam_type
            )

        for item in self.finish_view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await interaction.response.edit_message(view=self.finish_view)
        await interaction.followup.send(f"{interaction.user.mention} завершил экзамен. {self.candidate_mention.mention} результат можно узнать в канале: {self.results_link}.")

class CancelExamModal(discord.ui.Modal, title="Отмена экзамена"):
    def __init__(self, exam_instance, candidate_mention, data, guild):
        super().__init__()
        self.exam_instance = exam_instance  # Сохраняем экзамен
        self.candidate_mention = candidate_mention
        self.data = data
        self.guild = guild

        self.reason = discord.ui.TextInput(label="Причина отмены:", style=discord.TextStyle.paragraph, required=True, placeholder="Пример: Неверно указан никнейм.")
        self.add_item(self.reason)

    
    async def on_submit(self, interaction: discord.Interaction):
        # Поиск экзаменуемого по имени (данные из второго столбца)

        exam_candidate = await find_user_by_name(self.guild, self.data[1])  # Это должен быть дискорд-пользователь
        # Если пользователь найден, упоминаем его
        if exam_candidate:
            candidate_mention = exam_candidate.mention  # Сохраняем в переменную класса
        else:
            candidate_mention = ""


        await interaction.response.defer()

        # Отправляем уведомление об отмене
        await interaction.followup.send(f"{candidate_mention}, экзамен был отменён по следующей причине: **{self.reason.value}**")




#  Поиск по имене в гильдии
async def find_user_by_name(guild, name_status):
    # Разбиваем строку на части по разделителям | и /
    if '|' in name_status:
        exam_name = name_status.split('|')[0].strip()  # Берем имя и фамилию до символа |
    elif '/' in name_status:
        exam_name = name_status.split('/')[0].strip()  # Берем имя и фамилию до символа /
    else:
        exam_name = name_status.strip()  # Просто берем имя и фамилию, если нет разделителей

    # Итерируемся по всем участникам сервера
    for member in guild.members:
        # Если ник в формате "Отдел | Имя Фамилия | Статик", извлекаем только "Имя Фамилия"
        if '|' in member.display_name:
            discord_name = member.display_name.split('|')[1].strip()
        elif '/' in member.display_name:
            # Если ник в формате "Отдел / Имя Фамилия", извлекаем "Имя Фамилия"
            discord_name = " ".join(member.display_name.split('/')[:2]).strip()
        else:
            # Если нет разделителей, просто берём имя и фамилию из первых двух слов
            discord_name = " ".join(member.display_name.split()[:2]).strip()

        # Сравниваем имена (игнорируя регистр)
        if discord_name.lower() == exam_name.lower():
            return member  # Если нашли совпадение, возвращаем объект участника

    return None  # Если не нашли, возвращаем None



# bot.run('')

