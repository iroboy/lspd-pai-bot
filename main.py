import discord
from discord.ext import commands
import os
import asyncio
import aiohttp
import time
from dotenv import load_dotenv
from pathlib import Path

# ✅ Загрузка переменных окружения
dotenv_path = Path('bot.env')  
load_dotenv(dotenv_path=dotenv_path)

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ Ошибка: Токен не найден! Проверь bot.env файл.")

# ✅ Настройка бота
intents = discord.Intents.default()

intents.messages = True

intents.message_content = True

intents.members = True

intents.guilds = True


bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ Ограничение частоты запросов
last_request_time = 0
rate_limit_delay = 5  # Минимальная задержка между запросами (в секундах)

async def safe_api_request(url, session):
    """Отправка запроса с ожиданием при Rate Limit"""
    global last_request_time

    # Ожидание между запросами
    now = time.time()
    if now - last_request_time < rate_limit_delay:
        await asyncio.sleep(rate_limit_delay - (now - last_request_time))

    async with session.get(url) as response:
        last_request_time = time.time()  # Обновляем время запроса

        if response.status == 429:  # Если нас заблокировали
            retry_after = int(response.headers.get("Retry-After", 10))
            print(f"⚠️ Rate Limit! Ждем {retry_after} сек...")
            await asyncio.sleep(retry_after)  # Ждем перед повтором
            return await safe_api_request(url, session)  # Повторяем запрос

        return await response.json()

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")


COGS = ["cogs.count", "cogs.exams", "cogs.meeting", "cogs.automessage", "cogs.greeting"]
    
# Функция для загрузки когов
async def load_cogs():
    """Загружаем все `cogs`, если они не загружены"""
    for cog in COGS:
        if cog in bot.extensions:  
            print(f"⚠️ {cog} уже загружен, пропускаем...")
            continue
        try:
            await bot.load_extension(cog)
            print(f"✅ Загружен: {cog}")
        except Exception as e:
            print(f"❌ Ошибка при загрузке {cog}: {e}")
            


@bot.event
async def on_message(message):
    """Фильтр частоты сообщений, чтобы не попасть под блок"""
    if message.author == bot.user:
        return
    await asyncio.sleep(2)  # Задержка перед ответом
    await bot.process_commands(message)

async def start_bot():
    """Запуск бота с защитой от Rate Limit"""
    async with aiohttp.ClientSession() as session:
        try:
            await load_cogs()
            await bot.start(TOKEN)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = int(e.response.headers.get("Retry-After", 10))
                print(f"⚠️ Rate Limit! Ждем {retry_after} сек перед повторным запуском...")
                await asyncio.sleep(retry_after)
                await start_bot()
            else:
                raise e

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("🛑 Бот остановлен вручную")
