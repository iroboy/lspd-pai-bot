import gspread
from oauth2client.service_account import ServiceAccountCredentials
import discord
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

        sheet = get_google_sheets_data('1oojGh0zn2UzxCUtHF_ib2NWPwsvOIgYylaSKOaonORk')  # Подключаемся к таблице
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

# Отправка заявки в дискорд
async def send_to_discord(data, channel, exam_link, results_link, role_mention, role_id, guild):
    session = ExamSession(data, exam_link, results_link, role_mention, role_id, guild)
    await session.send_exam(channel)

# Асинхронное форматирование данных в Discord Embed
async def format_embed(data, msk_time):
    embed = discord.Embed(title="Новая Запись на экзамен!", color=0x00ff00)
    if data:
        last_row = data  # Передаем строку целиком
        embed.add_field(name="Имя Фамилия | Статик", value=last_row[1], inline=False)  # Имя, фамилия, статик экзаменуемого
        embed.add_field(name="Какой экзамен хотите сдавать?", value=last_row[2], inline=False)  # Тип экзамена
        embed.set_footer(text=f"Сообщение отправлено в {msk_time} (МСК)")  # Время отправки в МСК
    return embed

# Класс для управления сессией экзамена
class ExamSession:
    def __init__(self, data, exam_link, results_link, role_mention, role_id, guild):
        self.data = data
        self.exam_link = exam_link
        self.results_link = results_link
        self.role_mention = role_mention  # Упоминание роли
        self.role_id = role_id  # ID роли, которая может принимать экзамен
        self.guild = guild  # Ссылка на гильдию
        self.view = discord.ui.View(timeout=None)  # Создаем новую view для каждой сессии экзамена
        self.finish_view = discord.ui.View()  # View для завершения экзамена
        self.accepted_by = None  # Поле для хранения ID пользователя, принявшего экзамен
        self.candidate_mention = ""


    async def send_exam(self, channel):
        global msg
        msk_time = get_msk_time()  # Получаем текущее время в МСК
        embed = await format_embed(self.data, msk_time)

        # Создаем кнопку для принятия экзамена
        button = discord.ui.Button(label="Принять экзамен", style=discord.ButtonStyle.primary)
        button.callback = self.on_accept_exam  # Привязываем callback к кнопке
        self.view.add_item(button)

        # Отправляем сообщение с пингом роли, вебхуком и кнопкой
        msg = await channel.send(content=f"{self.role_mention}", embed=embed, view=self.view)

    async def on_accept_exam(self, interaction):
        global candidate_mention
        global exam_candidate
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
        exam_candidate_name = self.data[1]  # Имя, фамилия, статик экзаменуемого
        exam_candidate = await find_user_by_name(self.guild, exam_candidate_name)

        # Если пользователь найден, упоминаем его
        if exam_candidate:
            candidate_mention = exam_candidate.mention
        else:
            candidate_mention = ""

        # Создаем кнопку для завершения экзамена
        finish_button = discord.ui.Button(label="Завершить экзамен", style=discord.ButtonStyle.secondary)
        finish_button.callback = self.on_finish_exam  # Привязываем callback к кнопке
        self.finish_view.add_item(finish_button)

        # Отправляем сообщение о принятии экзамена с упоминанием экзаменуемого
        await interaction.followup.send(
            f"{interaction.user.mention} принял экзамен. Экзаменуемый, {candidate_mention} просьба войти в: {self.exam_link}",view=self.finish_view)

        await msg.add_reaction("⏳")

    async def on_finish_exam(self, interaction: discord.Interaction):
        config_exam = await load_config()
        # Проверяем, что экзамен завершает тот же человек, который его принял
        if interaction.user.id != self.accepted_by:
            await interaction.response.send_message("Завершить экзамен может только тот, кто его принял.", ephemeral=True)
            return


        exam_candidate = await find_user_by_name(self.guild, self.data[1])  # Это должен быть дискорд-пользователь


        # Отключаем кнопку "Завершить экзамен"
        for item in self.finish_view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        await msg.clear_reactions()
        await msg.add_reaction("✅")

        await interaction.response.send_modal(ExamCompletionModal(self, exam_candidate, self.candidate_mention, self.finish_view, self.results_link))

# Класс для аудита экзаменов
class ExamCompletionModal(discord.ui.Modal, title="Аудит экзамена"):
    def __init__(self, exam_session, candidate_mention, exam_candidate, finish_view, results_link):
        super().__init__()
        self.exam_session = exam_session  # Передаем текущую сессию экзамена
        self.candidate_mention = candidate_mention  # Теперь есть!
        self.exam_candidate = exam_candidate  # Теперь есть!
        self.finish_view = finish_view
        self.results_link = results_link

        # Поля ввода
        self.add_item(discord.ui.TextInput(label="Какой экзамен?", style=discord.TextStyle.short, placeholder="Устный экзамен и/или Практику + test arest", required=True))
        self.add_item(discord.ui.TextInput(label="Результат?", style=discord.TextStyle.short, placeholder="Сдал / Не сдал", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        config1 = await load_config()
        # Получаем введённые данные
        exam_type = self.children[0].value
        exam_result = self.children[1].value

        # Находим нужный канал
        results_channel = interaction.guild.get_channel(int(config1["results_id"]))
        self.results_channel_link = interaction.guild.get_channel(config1["results_link"])

        if results_channel:
            # Отправляем результат экзамена в указанный канал
            await results_channel.send(
                f"1. {interaction.user.mention} | {interaction.user.display_name.rsplit('|')[1].strip()} | {interaction.user.display_name.rsplit('|')[2].strip()} \n"
                f"2. {self.candidate_mention.mention} | {self.candidate_mention.display_name.rsplit('|')[1].strip()} | {self.candidate_mention.display_name.rsplit('|')[2].strip()} \n"
                f"3. {exam_result.capitalize()} {exam_type.lower()} \n"
            )

        await interaction.response.edit_message(view=self.finish_view)

        # ✅ Закрываем окно, отправляя скрытое сообщение
        await interaction.followup.send(f"{interaction.user.mention} завершил экзамен. {self.candidate_mention.mention} результат можно узнать в канале: {self.results_link}.")

# Поиск пользователя в гильдии по имени
async def find_user_by_name(guild, name_status):
    # Пытаемся найти пользователя по его имени и фамилии из заявки.
    # В Discord нике ожидаем формат: Отдел | Имя Фамилия | Статик.
    # В заявке ожидаем формат: Имя Фамилия | Статик.
    
    # Извлекаем "Имя Фамилия" из заявки (до первого разделителя '|')
    exam_name = name_status.split('|')[0].strip()

    # Итерируемся по всем участникам сервера
    for member in guild.members:
        # Извлекаем "Имя Фамилия" из никнейма участника Discord (между двумя разделителями '|')
        discord_name = member.display_name.split('|')[1].strip() if '|' in member.display_name else None

        # Сравниваем "Имя Фамилия" из заявки и Discord
        if discord_name and discord_name.lower() == exam_name.lower():
            return member  # Если нашли совпадение, возвращаем участника

    return None  # Если не нашли, возвращаем None




# bot.run()
