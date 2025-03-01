import discord
from discord.ext import commands
import json
import asyncio
import aiofiles
import pytz
from datetime import datetime, timedelta
from collections import defaultdict


exams = 'устный экзамен, практический экзамен + test arest'


# Настройка Discord бота
intents = discord.Intents.default()
# intents.members = True  # Необходимо для поиска пользователей в гильдии
intents.messages = True  # Включаем намерение для сообщений
intents.message_content = True  # Включаем намерение для доступа к содержимому сообщений
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def load_config():
    async with aiofiles.open('config.json', 'r') as f:
        config_data = await f.read()
    return json.loads(config_data)


@bot.event
async def on_ready():
    print(f'Бот запущен как {bot.user}')
    config = await load_config()
    global head_sai, curator_sai, sai_role
    head_sai = config["head_sai"] # Пример роли, замените на вашу роль
    curator_sai = config["curator_sai"]  # Пример роли, замените на вашу роль
    sai_role = config["role_id"]

tz_moscow = pytz.timezone('Europe/Moscow')


# Функция для получения времени последней субботы в 22:00 по МСК
def get_last_saturday():
    # Текущее время в Москве
    now_msk = datetime.now(tz_moscow)

    # Определяем, сколько дней прошло с последней субботы
    days_since_saturday = (now_msk.weekday() - 5) % 7  # 5 - суббота

    # Если сегодня суббота, берём предыдущую
    if days_since_saturday == 0:
        days_since_saturday = 7  

    # Получаем дату прошлой субботы
    last_saturday = now_msk - timedelta(days=days_since_saturday)

    # Устанавливаем время 22:00
    last_saturday_at_22_00 = last_saturday.replace(hour=22, minute=0, second=0, microsecond=0)

    return last_saturday_at_22_00.astimezone(tz_moscow)  # Возвращаем в МСК


# Команда для подсчета авторов сообщений
@bot.command()
async def count_authors(ctx):
    # Проверяем роль пользователя
    has_role = any(role.id in (head_sai, curator_sai) for role in ctx.author.roles)

    if not has_role:
        msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
        await asyncio.sleep(4)
        await msg.delete()
        return
    
    await ctx.message.delete()
    
    last_saturday = get_last_saturday()
    now_msk = datetime.now(tz_moscow)

    # Делаем наивные даты
    last_saturday_naive = last_saturday.replace(tzinfo=None)
    now_msk_naive = now_msk.replace(tzinfo=None)

    message_counts = defaultdict(int)

    async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive, limit=1000):  
        user_id = message.author.id
        message_counts[user_id] += 1

    if not message_counts:
        await ctx.send("⚠️ За указанный период не найдено сообщений.")
        return
    
    other_tags = 0

    response = f"📊  Статистика сообщений в период с **{str(last_saturday_naive.day).zfill(2)}-{str(last_saturday_naive.month).zfill(2)} {str(last_saturday_naive.hour).zfill(2)}:{str(last_saturday_naive.minute).zfill(2)}** по **{str(now_msk.day).zfill(2)}-{str(now_msk.month).zfill(2)} {str(now_msk.hour).zfill(2)}:{str(now_msk.minute).zfill(2)}:**\n"
    for user_id, count in message_counts.items():
        member = ctx.guild.get_member(user_id)  # Получаем объект участника сервера

        if member:
            global username
            username = member.display_name  # Никнейм на сервере
        else:
            user = await bot.fetch_user(user_id)  # Запасной вариант (если не на сервере)
            username = user.name  # Глобальное имя
            other_tags +=1

        response += f"**{username}**: **{count}** сообщений\n"
        
    response += f"\nДругих сообщений: **{other_tags}** сообщений\n" + f"Всего сообщений: **{sum(message_counts.values()) + other_tags}** сообщений"
    await ctx.author.send(response)


# Команда для подсчета количества упоминаний
@bot.command()
async def count_mentions(ctx):
    # Проверяем роль пользователя
    has_role = any(role.id in (head_sai, curator_sai) for role in ctx.author.roles)

    if not has_role:
        msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
        await asyncio.sleep(4)
        await msg.delete()
        return
    
    await ctx.message.delete()
    
        
    last_saturday = get_last_saturday()
    now_msk = datetime.now(tz_moscow)

    # Делаем наивные даты
    last_saturday_naive = last_saturday.replace(tzinfo=None)
    now_msk_naive = now_msk.replace(tzinfo=None)

    mention_counts = defaultdict(int)
    all_tags = 0
    other_tags = 0

    async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive):
        for user in message.mentions:
            member = ctx.guild.get_member(user.id)
            if member:
                has_role_ = any(role.id == sai_role for role in member.roles)

                if has_role_:
                    if exams in message.content.lower():
                        mention_counts[user.id] += 2
                        all_tags += 2
                    else:
                        mention_counts[user.id] += 1
                        all_tags += 1
                else:
                    all_tags += 1
                    other_tags += 1

    if not mention_counts:
        await ctx.send(f"⚠️ За указанный период не найдено упоминаний пользователей.")
        return
    else:
        # Инициализируем переменную перед использованием
        response = f"📊  Результат упоминаний в период с **{str(last_saturday_naive.day).zfill(2)}-{str(last_saturday_naive.month).zfill(2)} {str(last_saturday_naive.hour).zfill(2)}:{str(last_saturday_naive.minute).zfill(2)}** по **{str(now_msk.day).zfill(2)}-{str(now_msk.month).zfill(2)} {str(now_msk.hour).zfill(2)}:{str(now_msk.minute).zfill(2)}:**\n"
        
        # Сортируем упоминания по количеству
        sorted_mentions = sorted(mention_counts.items(), key=lambda x: x[1], reverse=True)

        for user_id, count in sorted_mentions:
            member = ctx.guild.get_member(user_id)  # Получаем member, а не user, чтобы получить ник на сервере
            if member:  # Убедимся, что member найден
                response += f"**{member.display_name}**: **{count}** упоминаний\n"  # Здесь используем member.display_name для отображения ника на сервере

        # Добавляем статистику по упоминаниям
        response += f"\nДругих упоминаний: **{other_tags}** упоминаний\n"
        response += f"Всего упоминаний: **{all_tags}** упоминаний"
        

        await ctx.author.send(response)


# Команда для подсчета количества поставленных реакций
@bot.command()
async def count_reactions(ctx):
    # Проверка роли для выполнения команды
    has_role = any(role.id in (head_sai, curator_sai) for role in ctx.author.roles)

    if not has_role:
        msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
        await asyncio.sleep(4)  # Ждём 7 секунд
        await msg.delete()
        return
    
    await ctx.message.delete()
    last_saturday = get_last_saturday()
    now_msk = datetime.now(tz_moscow)

    # Делаем наивные даты
    last_saturday_naive = last_saturday.replace(tzinfo=None)
    now_msk_naive = now_msk.replace(tzinfo=None)

    # Словарь для подсчёта реакций
    reaction_counts = defaultdict(int)
    other_tags = 0

    # Ищем сообщения в канале с фильтром времени
    async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive):
        # Проверяем, что сообщение отправлено ботом или вебхуком
        if message.author.bot or message.webhook_id:
            # Проходим по всем реакциям на сообщение
            for reaction in message.reactions:
                async for user in reaction.users():
                    # Проверяем, есть ли у пользователя нужная роль
                    has_role_ = any(role.id == sai_role for role in user.roles)

                    if has_role_:
                        reaction_counts[user.id] += 1  # Увеличиваем счётчик для пользователя
                    else:
                        other_tags += 1

    # Если нет реакций
    if not reaction_counts:
        await ctx.send("⚠️ За указанный период не найдено реакций от пользователей с нужными ролями.")
        return
    else:
        response = f"📊  Поставленные реакции в период с **{str(last_saturday_naive.day).zfill(2)}-{str(last_saturday_naive.month).zfill(2)} {str(last_saturday_naive.hour).zfill(2)}:{str(last_saturday_naive.minute).zfill(2)}** по **{str(now_msk.day).zfill(2)}-{str(now_msk.month).zfill(2)} {str(now_msk.hour).zfill(2)}:{str(now_msk.minute).zfill(2)}:**\n"
        for user_id, count in reaction_counts.items():
            # user = await bot.fetch_user(user_id)  # Получаем пользователя
            # username = user.display_name if user else user.name  # Получаем ник на сервере
            member = ctx.guild.get_member(user_id)  # Получаем объект участника сервера

            if member:
                username = member.display_name  # Никнейм на сервере
            else:
                user = await bot.fetch_user(user_id)  # Запасной вариант (если не на сервере)
                username = user.name  # Глобальное имя
            response += f"**{username}**: **{count}** реакции\n"
        
        response += f"\nДругие реакции: **{other_tags}** реакций\n" + f"Всего реакций: **{sum(reaction_counts.values()) + other_tags}** реакций"

    # Отправляем итоговый ответ
    await ctx.author.send(response)


# Команда для подсчёта принятий
@bot.command()
async def count_invites(ctx):
    # Проверка роли для выполнения команды
    has_role = any(role.id in (head_sai, curator_sai) for role in ctx.author.roles)

    if not has_role:
        msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
        await asyncio.sleep(4)  # Ждём 7 секунд
        await msg.delete()
        return
    
    await ctx.message.delete()
    
    last_saturday = get_last_saturday()
    now_msk = datetime.now(tz_moscow)

    # Делаем наивные даты
    last_saturday_naive = last_saturday.replace(tzinfo=None)
    now_msk_naive = now_msk.replace(tzinfo=None)

    # Словарь для подсчёта упоминаний
    mention_counts = defaultdict(int)

    other_tags = 0
    # Ищем сообщения от бота в канале с фильтром времени
    async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive):
        # Проверяем, что сообщение отправлено ботом
        if message.author.bot:
            # Проверяем, содержит ли сообщение слово 'принимает'
            if "принимает" in message.content.lower():
                # Проходим по всем упоминаниям в сообщении
                for user in message.mentions:
                    # Проверяем, есть ли у пользователя нужная роль
                    has_role_ = any(role.id == sai_role for role in user.roles)

                    if has_role_:
                        mention_counts[user.id] += 1  # Увеличиваем счётчик для пользователя

    # Если нет упоминаний
    if not mention_counts:
        await ctx.send("⚠️ За указанный период не найдено упоминаний с нужными ролями.")
        return

    # Формируем ответ
    response = f"📊  Принято людей в период с **{str(last_saturday_naive.day).zfill(2)}-{str(last_saturday_naive.month).zfill(2)} {str(last_saturday_naive.hour).zfill(2)}:{str(last_saturday_naive.minute).zfill(2)}** по **{str(now_msk.day).zfill(2)}-{str(now_msk.month).zfill(2)} {str(now_msk.hour).zfill(2)}:{str(now_msk.minute).zfill(2)}:**\n"
    for user_id, count in mention_counts.items():
            member = ctx.guild.get_member(user_id)  # Получаем объект участника сервера

            if member:
                username = member.display_name  # Никнейм на сервере
            else:
                user = await bot.fetch_user(user_id)  # Запасной вариант (если не на сервере)
                username = user.name  # Глобальное имя
            response += f"**{username}**: **{count}** принятий\n"
    response += f"\nДругие принятия: **{other_tags}** принятий\n" + f"Всего принято: **{sum(mention_counts.values()) + other_tags}** человек"
    # Отправляем итоговый ответ
    await ctx.author.send(response)


bot.run(TOKEN)
