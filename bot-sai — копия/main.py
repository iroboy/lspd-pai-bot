import discord
from discord.ext import commands
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Настройка бота
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Загрузка когов

@bot.event
async def on_ready():
    print(f'Бот запущен как {bot.user}')





async def main():
    dotenv_path = Path('bot.env')
    load_dotenv(dotenv_path=dotenv_path)
    token = os.getenv('TOKEN')

    if token is None:
        print("Токен не найден! Проверьте файл .env.")
        return

    await bot.load_extension("cogs.exams")
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
