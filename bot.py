import logging
import random
import json
import os
from datetime import datetime, time
from typing import Dict
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, JobQueue
from telegram.constants import ParseMode

# --- КОНСТАНТЫ И НАСТРОЙКИ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATA_FILE = 'football_data.json'
TIMEZONE = pytz.timezone('Asia/Tashkent')
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
TOKEN = "8373138925:AAG3kjpfdSjlXrULKCLT7W-n9taXSyeoxqM"

# --- КЛАСС ДЛЯ УПРАВЛЕНИЯ ДАННЫМИ ---

class FootballBot:
    def __init__(self):
        self.data = self.load_data()
        self.admin_user_id = None
        self.group_chat_id = self.data.get('group_chat_id')
        
    def load_data(self) -> Dict:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    data.setdefault('players', [])
                    data.setdefault('team1', [])
                    data.setdefault('team2', [])
                    data.setdefault('captain1', None)
                    data.setdefault('captain2', None)
                    data.setdefault('match_date', None)
                    data.setdefault('matches_history', [])
                    data.setdefault('remind_times', ['10:00', '18:00'])
                    data.setdefault('group_chat_id', None)
                    return data
            except Exception as e:
                logger.error(f"Ошибка загрузки данных: {e}")
        
        return {
            'players': [],
            'team1': [],
            'team2': [],
            'captain1': None,
            'captain2': None,
            'match_date': None,
            'matches_history': [],
            'remind_times': ['10:00', '18:00'],
            'group_chat_id': None
        }
    
    def save_data(self):
        try:
            self.data['group_chat_id'] = self.group_chat_id
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            logger.info("✅ Данные сохранены")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения данных: {e}")

bot_instance = FootballBot()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def is_admin(user_id: int) -> bool:
    return bot_instance.admin_user_id is not None and user_id == bot_instance.admin_user_id

async def check_admin(update: Update):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text(
            "⛔ <b>Недостаточно прав.</b>\nВыполните /login admin admin", 
            parse_mode=ParseMode.HTML
        )
        return False
    return True

def format_match_date(iso_date: str) -> str:
    try:
        match_datetime = datetime.fromisoformat(iso_date)
        match_datetime_tz = TIMEZONE.localize(match_datetime.replace(tzinfo=None))
        formatted_date = match_datetime_tz.strftime("%d %B в %H:%M")
        months = {
            'January': 'января', 'February': 'февраля', 'March': 'марта',
            'April': 'апреля', 'May': 'мая', 'June': 'июня',
            'July': 'июля', 'August': 'августа', 'September': 'сентября',
            'October': 'октября', 'November': 'ноября', 'December': 'декабря'
        }
        for eng, rus in months.items():
            formatted_date = formatted_date.replace(eng, rus)
        return formatted_date
    except Exception:
        return "Дата не назначена"

# --- ЛОГИКА НАПОМИНАНИЙ ---

async def set_jobs(application: Application):
    job_queue: JobQueue = application.job_queue
    current_jobs = job_queue.get_jobs_by_name("daily_reminders")
    for job in current_jobs:
        job.schedule_removal()
    
    remind_times = bot_instance.data.get('remind_times', [])
    if not bot_instance.group_chat_id:
        logger.info("group_chat_id не установлен")
        return

    for time_str in remind_times:
        try:
            hour, minute = map(int, time_str.split(':'))
            t = time(hour, minute, tzinfo=TIMEZONE)
            job_queue.run_daily(
                send_reminder,
                time=t,
                days=(0, 1, 2, 3, 4, 5, 6),
                name="daily_reminders"
            )
            logger.info(f"✅ Напоминание на {time_str}")
        except ValueError:
            logger.error(f"❌ Неверный формат времени: {time_str}")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    if not bot_instance.group_chat_id or not bot_instance.data.get('match_date'):
        return
    
    match_datetime = datetime.fromisoformat(bot_instance.data['match_date'])
    match_datetime_tz = TIMEZONE.localize(match_datetime.replace(tzinfo=None))
    now_tz = datetime.now(TIMEZONE)
    
    if now_tz >= match_datetime_tz:
        return
    
    time_diff = match_datetime_tz - now_tz
    days = time_diff.days
    hours = time_diff.seconds // 3600
    minutes = (time_diff.seconds % 3600) // 60
    
    if days == 0 and hours == 0 and minutes < 30:
        return

    time_str = []
    if days > 0:
        time_str.append(f"{days} дн.")
    if hours > 0:
        time_str.append(f"{hours} ч.")
    if minutes > 0:
        time_str.append(f"{minutes} мин.")
    
    formatted_date = format_match_date(bot_instance.data['match_date'])
    message = (
        f"⏳ <b>Напоминание! До матча осталось {' '.join(time_str)}!</b>\n"
        f"🕕 Матч состоится {formatted_date}"
    )
    
    await context.bot.send_message(
        chat_id=bot_instance.group_chat_id,
        text=message,
        parse_mode=ParseMode.HTML
    )

async def post_init_setup(application: Application):
    if bot_instance.group_chat_id:
        logger.info("Настройка напоминаний...")
        await set_jobs(application)
    else:
        logger.info("Напоминания будут настроены после /login")

# --- ОБРАБОТЧИКИ КОМАНД ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - приветствие бота"""
    welcome_text = """
👋 <b>Добро пожаловать в Футбольный бот!</b>

Для управления ботом нужна авторизация:
🔐 /login admin admin

После входа используйте /help для просмотра всех команд.
    """
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("⚠️ Использование: /login admin admin")
        return
    
    username, password = args
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        bot_instance.admin_user_id = update.effective_user.id
        # Сохраняем ID чата только если это групповой чат
        if update.message.chat.type in ['group', 'supergroup']:
            bot_instance.group_chat_id = update.message.chat_id
        elif not bot_instance.group_chat_id:
            # Если это личный чат и group_chat_id еще не установлен
            bot_instance.group_chat_id = update.message.chat_id
        
        bot_instance.save_data()
        
        await update.message.reply_text(
            "✅ <b>Вход выполнен. Привет, админ!</b>\n"
            "Используй /help для списка команд.\n"
            f"<i>ID чата: {bot_instance.group_chat_id}</i>",
            parse_mode=ParseMode.HTML
        )
        await set_jobs(context.application)
    else:
        await update.message.reply_text("❌ Неверный логин или пароль!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        help_text = """
📋 <b>КОМАНДЫ БОТА (Админ)</b>

<b>👤 Управление игроками:</b>
/addplayer Имя - добавить игрока
/addplayers Имя1, Имя2 - добавить несколько
/removeplayer Имя - удалить игрока
/players - список всех игроков
/clearplayers - очистить весь список

<b>⚽ Формирование команд:</b>
/split - случайное распределение
/setcaptain 1 Имя - назначить капитана команды 1
/setcaptain 2 Имя - назначить капитана команды 2

<b>📅 Управление матчем:</b>
/setdate ГГГГ-ММ-ДД ЧЧ:ММ - назначить дату матча
/announce - объявить матч в группе
/score X-Y - записать результат матча

<b>📊 История:</b>
/history - последние 10 матчей
/match номер - детали конкретного матча
/clearmatches - очистить всю историю

<b>⚙️ Настройки:</b>
/setremindtimes ЧЧ:ММ,ЧЧ:ММ - время напоминаний
/logout - выйти из системы
/help - эта справка

<i>💡 Совет: Используйте команды в группе для уведомлений всех участников!</i>
        """
    else:
        help_text = """
👋 <b>Добро пожаловать в Футбольный бот!</b>

Этот бот помогает организовывать футбольные матчи:
• 👥 Управление списком игроков
• ⚽ Автоматическое распределение команд
• 📅 Назначение времени матчей
• ⏰ Автоматические напоминания
• 📊 История всех матчей

<b>Для использования нужна авторизация:</b>
🔐 /login admin admin

После входа используйте /help для просмотра всех команд.
        """
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def addplayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.effective_message.reply_text(
            "⚠️ <b>Использование:</b> /addplayer Имя\n\n"
            "<i>Пример: /addplayer Саша</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    player_name = ' '.join(context.args).strip()
    
    if not player_name:
        await update.effective_message.reply_text(
            "⚠️ Имя игрока не может быть пустым",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверка на дубликат
    if player_name in bot_instance.data['players']:
        await update.effective_message.reply_text(
            f"⚠️ Игрок <b>«{player_name}»</b> уже есть в списке!\n\n"
            f"📋 Всего игроков: {len(bot_instance.data['players'])}\n"
            f"Используйте /players для просмотра списка",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Добавляем игрока
    bot_instance.data['players'].append(player_name)
    bot_instance.save_data()
    
    logger.info(f"✅ Добавлен игрок: {player_name} | Всего: {len(bot_instance.data['players'])}")
    
    await update.effective_message.reply_text(
        f"✅ <b>Игрок добавлен!</b>\n\n"
        f"👤 <b>{player_name}</b>\n"
        f"📊 Всего игроков: <b>{len(bot_instance.data['players'])}</b>",
        parse_mode=ParseMode.HTML
    )

async def addplayers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.effective_message.reply_text("⚠️ Использование: /addplayers Имя1, Имя2, Имя3")
        return
    
    # Получаем весь текст после команды
    full_text = update.effective_message.text.split(maxsplit=1)
    if len(full_text) < 2:
        await update.effective_message.reply_text("⚠️ Использование: /addplayers Имя1, Имя2, Имя3")
        return
    
    players_input = full_text[1]
    players_list = [p.strip() for p in players_input.split(',') if p.strip()]
    
    if not players_list:
        await update.effective_message.reply_text("⚠️ Не указаны имена игроков")
        return
    
    added = []
    duplicates = []
    
    for player in players_list:
        if player in bot_instance.data['players']:
            duplicates.append(player)
        else:
            bot_instance.data['players'].append(player)
            added.append(player)
    
    bot_instance.save_data()
    
    message = ""
    if added:
        message += f"✅ <b>Добавлено игроков: {len(added)}</b>\n"
        message += "\n".join([f"• {p}" for p in added])
    if duplicates:
        message += f"\n\n⚠️ <b>Уже в списке:</b>\n"
        message += "\n".join([f"• {p}" for p in duplicates])
    message += f"\n\n<b>Всего игроков: {len(bot_instance.data['players'])}</b>"
    
    await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)

async def players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    
    players_list = bot_instance.data.get('players', [])
    
    if not players_list:
        await update.effective_message.reply_text(
            "📋 <b>Список игроков пуст</b>\n\n"
            "Добавьте игроков:\n"
            "• /addplayer Имя - добавить одного\n"
            "• /addplayers Имя1, Имя2, Имя3 - добавить несколько",
            parse_mode=ParseMode.HTML
        )
        return
    
    message = f"📋 <b>Список игроков ({len(players_list)}):</b>\n\n"
    
    # Разделяем на группы по 20 для удобства чтения
    for i, p in enumerate(players_list, 1):
        message += f"{i}. {p}\n"
        # Если список очень большой, добавляем разделитель каждые 20 игроков
        if i % 20 == 0 and i < len(players_list):
            message += "\n"
    
    # Добавляем статистику
    message += f"\n<i>Для распределения команд используйте /split</i>"
    
    await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)

async def removeplayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    
    if not context.args:
        await update.effective_message.reply_text(
            "⚠️ <b>Использование:</b> /removeplayer Имя\n\n"
            "<i>Пример: /removeplayer Саша</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    player_name = ' '.join(context.args).strip()
    
    if not player_name:
        await update.effective_message.reply_text(
            "⚠️ Имя игрока не может быть пустым",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверяем наличие игрока
    if player_name not in bot_instance.data['players']:
        await update.effective_message.reply_text(
            f"⚠️ Игрок <b>«{player_name}»</b> не найден в списке!\n\n"
            f"Используйте /players для просмотра списка",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Удаляем игрока из основного списка
    bot_instance.data['players'].remove(player_name)
    
    # Удаляем из команд, если он там есть
    if player_name in bot_instance.data.get('team1', []):
        bot_instance.data['team1'].remove(player_name)
    if player_name in bot_instance.data.get('team2', []):
        bot_instance.data['team2'].remove(player_name)
    
    # Если он был капитаном, убираем капитанство
    if bot_instance.data.get('captain1') == player_name:
        bot_instance.data['captain1'] = None
    if bot_instance.data.get('captain2') == player_name:
        bot_instance.data['captain2'] = None
    
    bot_instance.save_data()
    
    logger.info(f"🗑️ Удалён игрок: {player_name} | Осталось: {len(bot_instance.data['players'])}")
    
    await update.effective_message.reply_text(
        f"✅ <b>Игрок удалён!</b>\n\n"
        f"👤 <b>{player_name}</b>\n"
        f"📊 Осталось игроков: <b>{len(bot_instance.data['players'])}</b>",
        parse_mode=ParseMode.HTML
    )

async def split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверка прав для callback query
    if hasattr(update, 'callback_query') and update.callback_query:
        if not is_admin(update.callback_query.from_user.id):
            await update.callback_query.answer("⛔ Недостаточно прав", show_alert=True)
            return
    else:
        if not await check_admin(update):
            return
    
    players_list = bot_instance.data['players'].copy()
    
    if len(players_list) < 2:
        await update.effective_message.reply_text("❌ Нужно минимум 2 игрока. Добавьте через /addplayer.")
        return
    
    random.shuffle(players_list)
    mid = len(players_list) // 2
    team1 = players_list[:mid]
    team2 = players_list[mid:2*mid]
    
    bot_instance.data['team1'] = team1
    bot_instance.data['team2'] = team2
    bot_instance.data['captain1'] = random.choice(team1) if team1 else None
    bot_instance.data['captain2'] = random.choice(team2) if team2 else None
    bot_instance.save_data()
    
    message = "⚽ <b>Рандомное распределение:</b>\n\n"
    message += "🟢 <b>Команда 1:</b>\n"
    for player in team1:
        mark = " 👑" if player == bot_instance.data['captain1'] else ""
        message += f"• {player}{mark}\n"
    
    message += "\n🔵 <b>Команда 2:</b>\n"
    for player in team2:
        mark = " 👑" if player == bot_instance.data['captain2'] else ""
        message += f"• {player}{mark}\n"
    
    if len(players_list) % 2 == 1:
        message += f"\n⚠️ Запасной: <b>{players_list[-1]}</b>"
    
    message += f"\n\n<b>Капитаны:</b>\n🟢 {bot_instance.data['captain1']}  |  🔵 {bot_instance.data['captain2']}"
    
    await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)

async def setcaptain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text("⚠️ Использование: /setcaptain <1/2> <Имя>")
        return
    
    team_num = context.args[0]
    captain_name = ' '.join(context.args[1:]).strip()
    
    if team_num == '1':
        if captain_name not in bot_instance.data['team1']:
            await update.effective_message.reply_text("⚠️ Этого игрока нет в команде 1")
            return
        bot_instance.data['captain1'] = captain_name
    elif team_num == '2':
        if captain_name not in bot_instance.data['team2']:
            await update.effective_message.reply_text("⚠️ Этого игрока нет в команде 2")
            return
        bot_instance.data['captain2'] = captain_name
    else:
        await update.effective_message.reply_text("⚠️ Номер команды должен быть 1 или 2")
        return
    
    bot_instance.save_data()
    await update.effective_message.reply_text(
        f"✅ <b>Капитаны обновлены:</b>\n"
        f"🟢 {bot_instance.data['captain1']}  |  🔵 {bot_instance.data['captain2']}",
        parse_mode=ParseMode.HTML
    )

async def setdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    if len(context.args) != 2:
        await update.effective_message.reply_text(
            "⚠️ Использование: /setdate ГГГГ-ММ-ДД ЧЧ:ММ\n"
            "Например: /setdate 2025-10-20 18:30"
        )
        return
    
    date_str = f"{context.args[0]} {context.args[1]}"
    try:
        match_datetime = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        bot_instance.data['match_date'] = match_datetime.isoformat()
        bot_instance.save_data()
        
        formatted_date = format_match_date(bot_instance.data['match_date'])
        message = f"📆 <b>Матч назначен на {formatted_date}</b>"
        
        keyboard = []
        has_teams = bool(bot_instance.data['team1'])
        has_enough_players = len(bot_instance.data['players']) >= 2
        
        if has_enough_players:
            action_text = "🔄 Перераспределить" if has_teams else "⚽ Распределить"
            message += "\n\n🤔 Желаете распределить команды сейчас?"
            keyboard.append(InlineKeyboardButton(
                f"{action_text} команды",
                callback_data='split_now'
            ))
        elif not has_enough_players:
            message += "\n\n⚠️ Добавьте игроков через /addplayer"
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup([keyboard])
            await update.effective_message.reply_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)
        
        await set_jobs(context.application)
    except ValueError:
        await update.effective_message.reply_text("❌ Неверный формат! Используйте: ГГГГ-ММ-ДД ЧЧ:ММ")

async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    if not bot_instance.data.get('match_date'):
        await update.effective_message.reply_text("⚠️ Сначала назначьте дату через /setdate")
        return
    if not bot_instance.data['team1'] or not bot_instance.data['team2']:
        await update.effective_message.reply_text("⚠️ Сначала распределите игроков через /split")
        return
    
    formatted_date = format_match_date(bot_instance.data['match_date'])
    message = f"⚽ <b>Следующий матч состоится {formatted_date}!</b>\n\n"
    message += "🟢 <b>Команда 1:</b>\n"
    for player in bot_instance.data['team1']:
        mark = " (капитан)" if player == bot_instance.data['captain1'] else ""
        message += f"• {player}{mark}\n"
    message += "\n🔵 <b>Команда 2:</b>\n"
    for player in bot_instance.data['team2']:
        mark = " (капитан)" if player == bot_instance.data['captain2'] else ""
        message += f"• {player}{mark}\n"
    message += "\n⚽ Всем удачи!"
    await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)

async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("⚠️ Использование: /score X-Y (например: /score 3-2)")
        return
    
    score_input = context.args[0]
    if '-' not in score_input:
        await update.effective_message.reply_text("❌ Неверный формат! Используйте: /score X-Y")
        return
    
    try:
        score1, score2 = map(int, score_input.split('-'))
        match_data = {
            'date': bot_instance.data.get('match_date'),
            'team1': bot_instance.data['team1'].copy(),
            'team2': bot_instance.data['team2'].copy(),
            'captain1': bot_instance.data['captain1'],
            'captain2': bot_instance.data['captain2'],
            'score1': score1,
            'score2': score2
        }
        bot_instance.data['matches_history'].append(match_data)
        bot_instance.save_data()
        
        winner = ""
        if score1 > score2:
            winner = "\n🏆 Победила команда 1!"
        elif score2 > score1:
            winner = "\n🏆 Победила команда 2!"
        else:
            winner = "\n🤝 Ничья!"
        
        await update.effective_message.reply_text(
            f"✅ <b>Счёт зафиксирован:</b> 🟢 {score1} — {score2} 🔵{winner}",
            parse_mode=ParseMode.HTML
        )
    except ValueError:
        await update.effective_message.reply_text("❌ Неверный формат счёта!")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    matches = bot_instance.data.get('matches_history', [])
    if not matches:
        await update.effective_message.reply_text("📜 История матчей пуста.")
        return
    
    message = "📜 <b>История матчей (последние 10):</b>\n\n"
    for i, match in enumerate(reversed(matches[-10:]), 1):
        match_date = "Дата не указана"
        if match.get('date'):
            match_date = format_match_date(match['date']).split(" в ")[0]
        idx = len(matches) - i + 1
        message += (
            f"#{idx} ({match_date}) — 🟢{match['score1']}:{match['score2']}🔵 "
            f"(К1: {match.get('captain1', 'Нет')} | К2: {match.get('captain2', 'Нет')})\n"
        )
    await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)

async def match_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text("⚠️ Использование: /match <номер>")
        return
    
    try:
        match_num = int(context.args[0])
        matches = bot_instance.data.get('matches_history', [])
        if match_num < 1 or match_num > len(matches):
            await update.effective_message.reply_text("⚠️ Матч с таким номером не найден.")
            return
        
        match = matches[match_num - 1]
        match_date = "Дата не указана"
        if match.get('date'):
            match_date = format_match_date(match['date'])
        
        message = f"📅 <b>Матч №{match_num} — {match_date}</b>\n\n"
        message += f"🟢 <b>Команда 1</b> (капитан: {match.get('captain1', 'Нет')})\n"
        for player in match['team1']:
            message += f"• {player}\n"
        message += f"\n🔵 <b>Команда 2</b> (капитан: {match.get('captain2', 'Нет')})\n"
        for player in match['team2']:
            message += f"• {player}\n"
        message += f"\n🏁 <b>Счёт:</b> {match['score1']} — {match['score2']}"
        await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)
    except ValueError:
        await update.effective_message.reply_text("❌ Номер матча должен быть числом!")

async def clearplayers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    bot_instance.data['players'] = []
    bot_instance.data['team1'] = []
    bot_instance.data['team2'] = []
    bot_instance.data['captain1'] = None
    bot_instance.data['captain2'] = None
    bot_instance.save_data()
    await update.effective_message.reply_text("✅ Список игроков очищен.")

async def clearmatches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    bot_instance.data['matches_history'] = []
    bot_instance.save_data()
    await update.effective_message.reply_text("✅ История матчей очищена.")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    bot_instance.admin_user_id = None
    bot_instance.group_chat_id = None
    bot_instance.save_data()
    
    job_queue: JobQueue = context.application.job_queue
    current_jobs = job_queue.get_jobs_by_name("daily_reminders")
    for job in current_jobs:
        job.schedule_removal()
    await update.effective_message.reply_text("👋 Вы вышли из системы. Напоминания отключены.")

async def setremindtimes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            f"⚠️ Использование: /setremindtimes ЧЧ:ММ,ЧЧ:ММ\n"
            f"Например: /setremindtimes 09:30,21:00\n\n"
            f"Текущее время: <b>{', '.join(bot_instance.data.get('remind_times', []))}</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    times_input = context.args[0]
    times = [t.strip() for t in times_input.split(',') if t.strip()]
    valid_times = []
    for t_str in times:
        try:
            datetime.strptime(t_str, "%H:%M")
            valid_times.append(t_str)
        except ValueError:
            await update.effective_message.reply_text(f"❌ Неверный формат: {t_str}. Используйте ЧЧ:ММ")
            return
    
    bot_instance.data['remind_times'] = valid_times
    bot_instance.save_data()
    await set_jobs(context.application)
    await update.effective_message.reply_text(
        f"✅ Время напоминаний обновлено: <b>{', '.join(valid_times)}</b>\n"
        f"<i>Напоминания в чат ID: {bot_instance.group_chat_id}</i>",
        parse_mode=ParseMode.HTML
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'split_now':
        if not is_admin(query.from_user.id):
            await query.edit_message_text(
                "⛔ Недостаточно прав для выполнения этого действия.",
                reply_markup=None
            )
            return
        await split(update, context)
        await query.edit_message_markup(reply_markup=None)

# --- ГЛАВНАЯ ФУНКЦИЯ ---

def main():
    application = Application.builder().token(TOKEN).build()
    application.post_init = post_init_setup
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addplayer", addplayer))
    application.add_handler(CommandHandler("addplayers", addplayers))
    application.add_handler(CommandHandler("removeplayer", removeplayer))
    application.add_handler(CommandHandler("players", players))
    application.add_handler(CommandHandler("split", split))
    application.add_handler(CommandHandler("setcaptain", setcaptain))
    application.add_handler(CommandHandler("setdate", setdate))
    application.add_handler(CommandHandler("announce", announce))
    application.add_handler(CommandHandler("score", score))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("match", match_details))
    application.add_handler(CommandHandler("clearplayers", clearplayers))
    application.add_handler(CommandHandler("clearmatches", clearmatches))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("setremindtimes", setremindtimes))
    application.add_handler(CallbackQueryHandler(button))
    
    logger.info("⚽ Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()