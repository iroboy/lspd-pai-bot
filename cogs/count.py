import discord
from discord.ext import commands
import pytz
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
import json
import aiofiles
import re



exams = 'устный экзамен, практический экзамен + test arest'
tz_moscow = pytz.timezone('Europe/Moscow')


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



class Count(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.head = None
        self.sai_role = None


    async def load_config(self):
        """Загружает конфигурацию из config.json"""
        async with aiofiles.open('config.json', 'r', encoding='utf-8') as f:
            config_data = await f.read()
        
        global config
        config = json.loads(config_data)
        self.head = config["head_sai"]
        self.sai_role = config["role_id"]


    @commands.command()
    async def count_authors(self, ctx):
        await self.load_config()  # Загружаем конфиг

        # Проверяем, есть ли у пользователя нужная роль
        allowed_roles = set(self.head) if isinstance(self.head, list) else {int(self.head)}
        user_roles = {role.id for role in ctx.author.roles}

        if not allowed_roles & user_roles:
            msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
            await asyncio.sleep(4)
            await msg.delete()
            await ctx.message.delete()
            return

        await ctx.message.delete()

        last_saturday = get_last_saturday()
        now_msk = datetime.now(tz_moscow)

        # Делаем наивные даты
        last_saturday_naive = last_saturday.replace(tzinfo=None)
        now_msk_naive = now_msk.replace(tzinfo=None)

        # Словари для подсчёта
        message_counts = defaultdict(int)
        other_tags = 0

        # Проверяем историю сообщений
        async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive, limit=2000):
            member = message.author  
            if member.bot:  
                continue  # Пропускаем ботов

            has_role = any(role.id == self.sai_role for role in member.roles)

            if has_role:
                message_counts[member.id] += 1
            else:
                other_tags += 1

        # Если нет сообщений
        if not message_counts:
            await ctx.send("⚠️ За указанный период не найдено сообщений.")
            return

        # Формируем ответ
        response = (
            f"## 📊  Сообщения с **{last_saturday.strftime('%d-%m %H:%M')}** по **{now_msk.strftime('%d-%m %H:%M')}**\n"
        )

        sorted_counts = sorted(message_counts.items(), key=lambda x: x[1], reverse=True)

        for user_id, count in sorted_counts:
            member = ctx.guild.get_member(user_id)
            username = member.display_name if member else f"Unknown ({user_id})"
            response += f"**{username}**: **{count}** сообщений\n"

        response += f"\nДругие сообщения: **{other_tags}**\nВсего сообщений: **{sum(message_counts.values()) + other_tags}**"

        # Отправляем в ЛС или в чат
        try:
            await ctx.author.send(response)
        except discord.Forbidden:
            await ctx.send(f"⚠️ {ctx.author.mention}, у вас закрыты ЛС! Отправляю сюда:\n{response}")
    
    @commands.command()
    async def count_mentions(self, ctx):
        await self.load_config()  # ✅ Загружаем конфиг перед проверкой
        print("🔄 Конфиг загружен!")

        # ✅ Проверяем роль пользователя
        allowed_roles = set(self.head) if isinstance(self.head, list) else {int(self.head)}
        user_roles = {role.id for role in ctx.author.roles}

        if not allowed_roles & user_roles:
            msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
            await asyncio.sleep(4)
            await msg.delete()
            await ctx.message.delete()
            return

        await ctx.message.delete()

        last_saturday = get_last_saturday()
        now_msk = datetime.now(tz_moscow)

        # Делаем наивные даты
        last_saturday_naive = last_saturday.replace(tzinfo=None)
        now_msk_naive = now_msk.replace(tzinfo=None)

        mention_counts = defaultdict(int)
        other_tags = 0

        async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive, limit=2000):
            match = re.search(r"1\.\s+<@!?(\d+)>", message.content)
            if match:
                first_mention_id = int(match.group(1))
                member = ctx.guild.get_member(first_mention_id)

                if member:
                    has_sai_role = any(role.id == self.sai_role for role in member.roles)

                    if has_sai_role:
                        if exams in message.content.lower():
                            mention_counts[first_mention_id] += 2
                        else:
                            mention_counts[first_mention_id] += 1
                    else:
                        other_tags += 1
                else:
                    other_tags += 1

        if not mention_counts:
            await ctx.send("⚠️ За указанный период не найдено упоминаний пользователей.")
            print("⚠️ Нет упоминаний!")
            return

        # ✅ Формируем ответ
        response = (
            f"## 📊  Результат упоминаний с **{last_saturday.strftime('%d-%m %H:%M')}** "
            f"по **{now_msk.strftime('%d-%m %H:%M')}**:\n"
        )

        sorted_mentions = sorted(mention_counts.items(), key=lambda x: x[1], reverse=True)

        for user_id, count in sorted_mentions:
            member = ctx.guild.get_member(user_id)
            username = member.display_name if member else (await self.bot.fetch_user(user_id)).name
            response += f"**{username}**: **{count}** упоминаний\n"

        response += f"\nДругие упоминания: **{other_tags}**\n"
        response += f"Всего упоминаний: **{sum(mention_counts.values()) + other_tags}**"

        # ✅ Проверяем, открыт ли ЛС
        if not ctx.author.dm_channel:
            await ctx.author.create_dm()

        try:
            await ctx.author.send(response)
            print("✅ Отправлен отчёт в ЛС!")
        except discord.Forbidden:
            await ctx.send(f"⚠️ {ctx.author.mention}, у вас закрыты ЛС! Отправляю сюда:\n{response}")   
    
    @commands.command()
    async def count_reactions(self, ctx):
        try:
            await self.load_config()  # ✅ Загружаем конфиг перед проверкой
            print("🔄 Конфиг загружен!")

            # ✅ Проверяем роль пользователя
            allowed_roles = set(self.head) if isinstance(self.head, list) else {int(self.head)}
            user_roles = {role.id for role in ctx.author.roles}

            if not allowed_roles & user_roles:
                msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
                await asyncio.sleep(4)
                await msg.delete()
                await ctx.message.delete()
                return

            await ctx.message.delete()

            last_saturday = get_last_saturday()
            now_msk = datetime.now(tz_moscow)

            # Делаем наивные даты
            last_saturday_naive = last_saturday.replace(tzinfo=None)
            now_msk_naive = now_msk.replace(tzinfo=None)

            reaction_counts = defaultdict(int)
            other_tags = 0

            # ✅ Считаем реакции
            async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive, limit=2000):
                for reaction in message.reactions:
                    async for user in reaction.users():
                        if user.bot:
                            continue  # Пропускаем ботов

                        member = ctx.guild.get_member(user.id)
                        has_sai_role = member and any(role.id == self.sai_role for role in member.roles) if member else False

                        if has_sai_role:
                            reaction_counts[user.id] += 1
                        else:
                            other_tags += 1  # ✅ Добавляется только если реакция учтена

            if not reaction_counts:
                await ctx.send("⚠️ За указанный период не найдено реакций от пользователей с нужными ролями.")
                return

            # ✅ Формируем отчет
            response = (
                f"## 📊  Поставленные реакции с **{last_saturday.strftime('%d-%m %H:%M')}** "
                f"по **{now_msk.strftime('%d-%m %H:%M')}**:\n"
            )

            sorted_reactions = sorted(reaction_counts.items(), key=lambda x: x[1], reverse=True)

            for user_id, count in sorted_reactions:
                member = ctx.guild.get_member(user_id)
                username = member.display_name if member else (await self.bot.fetch_user(user_id)).name
                response += f"**{username}**: **{count}** реакции\n"

            response += f"\nДругие реакции: **{other_tags}**\n"
            response += f"Всего реакций: **{sum(reaction_counts.values()) + other_tags}**"

            # ✅ Отправка в ЛС (или в канал, если ЛС закрыты)
            if not ctx.author.dm_channel:
                await ctx.author.create_dm()

            try:
                await ctx.author.send(response)
                print("✅ Отчет отправлен в ЛС!")
            except discord.Forbidden:
                await ctx.send(f"⚠️ {ctx.author.mention}, у вас закрыты ЛС! Отправляю сюда:\n{response}")

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            await ctx.send(f"❌ Произошла ошибка: {e}")
    
    @commands.command()
    async def count_invites(self, ctx):
        try:
            await self.load_config()  # ✅ Загружаем конфиг перед проверкой
            print("🔄 Конфиг загружен!")

            # Проверяем роль пользователя
            allowed_roles = set(self.head) if isinstance(self.head, list) else {int(self.head)}
            user_roles = {role.id for role in ctx.author.roles}

            if not allowed_roles & user_roles:
                msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
                await asyncio.sleep(4)
                await msg.delete()
                await ctx.message.delete()
                return

            await ctx.message.delete()

            last_saturday = get_last_saturday()
            now_msk = datetime.now(tz_moscow)

            # Делаем наивные даты
            last_saturday_naive = last_saturday.replace(tzinfo=None)
            now_msk_naive = now_msk.replace(tzinfo=None)

            # Словари для подсчёта
            mention_counts = defaultdict(int)
            other_tags = 0

            async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive, limit=2000):
                if not (message.author.bot or message.webhook_id):
                    continue  # Пропускаем сообщения не от бота

                if "принимает" in message.content.lower():
                    mention_match = re.search(r"<@!?(\d+)>", message.content)  # Ищем первый тег вручную
                    if mention_match:
                        first_user_id = int(mention_match.group(1))  # Берём ID из первого тега
                        member = ctx.guild.get_member(first_user_id)
                        has_sai_role = member and any(role.id == self.sai_role for role in member.roles) if member else False

                        if has_sai_role:
                            mention_counts[first_user_id] += 1  # ✅ Если есть роль, считаем
                        else:
                            other_tags += 1  # ❌ Если роли нет или человек не на сервере, считаем в other_tags

            if not mention_counts:
                await ctx.send("⚠️ За указанный период не найдено принятий с нужными ролями.")
                return



            response = (
                f"## 📊 Принято людей в период с **{last_saturday.strftime('%d-%m %H:%M')}** "
                f"по **{now_msk.strftime('%d-%m %H:%M')}:**\n"
            )

            sorted_mentions = sorted(mention_counts.items(), key=lambda x: x[1], reverse=True)

            for user_id, count in sorted_mentions:
                member = ctx.guild.get_member(user_id)
                username = member.display_name if member else (await self.bot.fetch_user(user_id)).name
                response += f"**{username}**: **{count}** принятий\n"

            response += f"\nДругие принятия: **{other_tags}**\n" + f"Всего принято: **{sum(mention_counts.values()) + other_tags}** человек"

            # Проверяем, открыт ли ЛС
            try:
                await ctx.author.send(response)
                print("✅ Отправлен отчёт в ЛС!")
            except discord.Forbidden:
                await ctx.send(f"⚠️ {ctx.author.mention}, у вас закрыты ЛС! Отправляю сюда:\n{response}")

        except Exception as e:
            print(f"❌ Ошибка: {e}")  # Лог ошибки
            await ctx.send(f"❌ Произошла ошибка: {e}") 

    @commands.command()
    async def count_apps(self, ctx):
        await self.load_config()  # ✅ Загружаем конфиг перед проверкой

        # ✅ Проверяем, является ли `self.head` списком
        allowed_roles = set(self.head) if isinstance(self.head, list) else {int(self.head)}

        # ✅ Проверяем, есть ли у пользователя нужная роль
        user_roles = {role.id for role in ctx.author.roles}

        if not allowed_roles & user_roles:
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

        # Словарь для подсчёта упоминаний
        mention_counts = defaultdict(int)

        other_tags = 0
        # Ищем сообщения от бота в канале с фильтром времени
        async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive, limit=2000):
            # Проверяем, что сообщение отправлено ботом
            if message.author.bot:
                # Проверяем, содержит ли сообщение слово 'принимает'
                if "повышает" in message.content.lower():
                    # Проходим по всем упоминаниям в сообщении
                    for user in message.mentions:
                        # Проверяем, есть ли у пользователя нужная роль
                        has_role_ = any(role.id == self.sai_role for role in user.roles)

                        if has_role_:
                            mention_counts[user.id] += 1  # Увеличиваем счётчик для пользователя

        # Если нет упоминаний
        if not mention_counts:
            await ctx.send("⚠️ За указанный период не найдено упоминаний с нужными ролями.")
            return

        # Формируем ответ
        response = f"## 📊 Отчётов проверено в период с **{str(last_saturday_naive.day).zfill(2)}-{str(last_saturday_naive.month).zfill(2)} {str(last_saturday_naive.hour).zfill(2)}:{str(last_saturday_naive.minute).zfill(2)}** по **{str(now_msk.day).zfill(2)}-{str(now_msk.month).zfill(2)} {str(now_msk.hour).zfill(2)}:{str(now_msk.minute).zfill(2)}:**\n"
                
        for user_id, count in mention_counts.items():
            member = ctx.guild.get_member(user_id)  # Получаем объект участника сервера

            if member:
                username = member.display_name  # Никнейм на сервере
            else:
                user = await self.bot.fetch_user(user_id)  # Запасной вариант (если не на сервере)
                username = user.name  # Глобальное имя
                response += f"**{username}**: **{count}** отчётов\n"
            response += f"\nДругие проверенные отчёты: **{other_tags}** отчётов\n" + f"Всего: **{sum(mention_counts.values()) + other_tags}** отчётов"
        
        # Отправляем итоговый ответ
        await ctx.author.send(response)

    @commands.command()
    async def count_lic(self, ctx):
        try:
            await self.load_config()  # ✅ Загружаем конфиг перед проверкой
            print("🔄 Конфиг загружен!")

            # ✅ Проверяем роль пользователя
            allowed_roles = set(self.head) if isinstance(self.head, list) else {int(self.head)}
            user_roles = {role.id for role in ctx.author.roles}

            if not allowed_roles & user_roles:
                msg = await ctx.reply("У вас нет роли, чтобы выполнить эту команду.")
                await asyncio.sleep(4)
                await msg.delete()
                await ctx.message.delete()
                return

            await ctx.message.delete()

            last_saturday = get_last_saturday()
            now_msk = datetime.now(tz_moscow)

            # Делаем наивные даты
            last_saturday_naive = last_saturday.replace(tzinfo=None)
            now_msk_naive = now_msk.replace(tzinfo=None)

            message_counts = defaultdict(int)
            other_tags = 0

            # Проверяем сообщения за период
            async for message in ctx.channel.history(after=last_saturday_naive, before=now_msk_naive, limit=2000):
                member = message.author
                if member.bot:
                    continue  # Пропускаем ботов

                # Получаем объект Member, чтобы проверить роли
                member = ctx.guild.get_member(member.id)  # Получаем объект Member

                if member is None:
                    continue  # Если пользователя нет на сервере, пропускаем

                has_role = any(role.id == self.sai_role for role in member.roles)
                content = message.content.lower()

                # Подсчёт лицензий
                points = 0
                if "12000" in content or "12.000" in content:
                    points = 1
                elif "24000" in content or "24.000" in content:
                    points = 2
                elif "36000" in content or "36.000" in content:
                    points = 3
                elif "48000" in content or "48.000" in content:
                    points = 4

                if has_role:
                    message_counts[member.id] += points
                else:
                    other_tags += points

            if not message_counts:
                await ctx.send("⚠️ За указанный период не найдено сообщений с лицензиями.")
                print("⚠️ Нет лицензий!")
                return

            # ✅ Формируем ответ с корректным форматированием
            response = (
                f"## 📊  Статистика лицензий с **{last_saturday.strftime('%d-%m %H:%M')}** "
                f"по **{now_msk.strftime('%d-%m %H:%M')}:**\n"
            )

            sorted_licenses = sorted(message_counts.items(), key=lambda x: x[1], reverse=True)

            for user_id, count in sorted_licenses:
                member = ctx.guild.get_member(user_id)
                username = member.display_name if member else (await self.bot.fetch_user(user_id)).name
                response += f"**{username}**: **{count}** лицензий\n"

            response += f"\nДругие лицензии: **{other_tags}**\nВсего лицензий: **{sum(message_counts.values()) + other_tags}**"

            # ✅ Отправляем сообщение в ЛС
            try:
                await ctx.author.send(response)
                print("✅ Отправлен отчёт в ЛС!")
            except discord.Forbidden:
                await ctx.send(f"⚠️ {ctx.author.mention}, у вас закрыты ЛС! Отправляю сюда:\n{response}")

        except Exception as e:
            print(f"❌ Ошибка: {e}")  # Лог ошибки
            await ctx.send(f"❌ Произошла ошибка: {e}")


async def setup(bot):
    await bot.add_cog(Count(bot))
        


