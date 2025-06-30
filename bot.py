import logging
import json
import os
from datetime import datetime, timedelta
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    PicklePersistence
)

# --- КОНФИГУРАЦИЯ ---
CONFIG = {
    'TOKEN': '8087173732:AAEEPd4j_krBy4-vzDiH3MCvmDWvIYA6AZU',
    'ADMIN_ID': 8114620763,
    'DATABASE_FILE': 'bot_data.json',
    'LOG_FILE': 'bot.log',
    'REPORT_COOLDOWN': 300  # 5 минут между репортами
}

# --- НАСТРОЙКА ЛОГГИНГА ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(CONFIG['LOG_FILE']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- КЛАСС ДЛЯ ХРАНЕНИЯ ДАННЫХ ---
class Database:
    def __init__(self):
        self.data = {
            'users': {},
            'reports': {},
            'stats': {
                'total_reports': 0,
                'resolved_reports': 0
            },
            'settings': {
                'auto_respond': True,
                'notify_new_users': True
            },
            'banned_users': {}
        }
        self.load()
    
    def load(self):
        if os.path.exists(CONFIG['DATABASE_FILE']):
            with open(CONFIG['DATABASE_FILE'], 'r') as f:
                self.data = json.load(f)
    
    def save(self):
        with open(CONFIG['DATABASE_FILE'], 'w') as f:
            json.dump(self.data, f, indent=2)

db = Database()

# --- КЛАВИАТУРЫ ---
def get_main_keyboard(is_admin=False):
    buttons = [
        ["🆘 Помощь", "⚠️ Репорт"],
        ["📊 Моя статистика"]
    ]
    if is_admin:
        buttons.append(["👮 Админ-панель"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([
        ["📨 Репорты", "📊 Статистика"],
        ["👥 Пользователи", "⚙️ Настройки"],
        ["🔙 Главное меню"]
    ], resize_keyboard=True)

def get_settings_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Авто-ответы" if db.data['settings']['auto_respond'] else "❌ Авто-ответы",
                callback_data="toggle_auto_respond"
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Уведомления" if db.data['settings']['notify_new_users'] else "❌ Уведомления",
                callback_data="toggle_notify_new_users"
            )
        ]
    ])

def get_report_actions(report_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📩 Ответить", callback_data=f"reply_{report_id}"),
            InlineKeyboardButton("✅ Закрыть", callback_data=f"resolve_{report_id}")
        ],
        [
            InlineKeyboardButton("🚷 Забанить", callback_data=f"ban_{report_id}"),
            InlineKeyboardButton("🔍 Подробнее", callback_data=f"details_{report_id}")
        ]
    ])

# --- УТИЛИТЫ ---
async def is_admin(user_id):
    return user_id == CONFIG['ADMIN_ID']

async def update_user(user):
    db.data['users'][str(user.id)] = {
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'last_activity': datetime.now().isoformat(),
        'reports_sent': db.data['users'].get(str(user.id), {}).get('reports_sent', 0),
        'is_banned': False
    }
    db.save()

async def can_send_report(user_id):
    user_id = str(user_id)
    for report in db.data['reports'].values():
        if report['user_id'] == user_id:
            report_time = datetime.fromisoformat(report['timestamp'])
            if (datetime.now() - report_time) < timedelta(seconds=CONFIG['REPORT_COOLDOWN']):
                return False
    return True

# --- ОБРАБОТЧИКИ КОМАНД ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        await update.message.reply_text("ℹ️ Бот работает только в ЛС!")
        return
    
    user = update.effective_user
    await update_user(user)
    
    if await is_admin(user.id):
        text = "👑 Добро пожаловать, Администратор!"
    else:
        text = (
            "👋 Привет! Я бот поддержки.\n"
            "Отправьте репорт, если у вас есть проблемы."
        )
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard(await is_admin(user.id)))

async def show_help(update: Update):
    help_text = (
        "🆘 *Помощь по боту*\n\n"
        "• Нажмите *⚠️ Репорт* для отправки жалобы\n"
        "• *📊 Моя статистика* - ваша активность\n"
        "• Администратор ответит в течение 24 часов\n"
        "• Используйте /start для перезагрузки бота"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def show_user_stats(update: Update):
    user = update.effective_user
    stats = db.data['users'].get(str(user.id), {})
    stats_text = (
        f"📊 *Ваша статистика*\n\n"
        f"• Отправлено репортов: {stats.get('reports_sent', 0)}\n"
        f"• Последняя активность: {stats.get('last_activity', 'никогда')}\n"
        f"• Статус: {'🔴 Заблокирован' if str(user.id) in db.data['banned_users'] else '🟢 Активен'}"
    )
    await update.message.reply_text(stats_text, parse_mode="Markdown")

# --- ОБРАБОТЧИКИ РЕПОРТОВ ---
async def start_report(update: Update):
    user = update.effective_user
    if not await can_send_report(user.id):
        cooldown = CONFIG['REPORT_COOLDOWN'] // 60
        await update.message.reply_text(f"⏳ Вы можете отправлять репорты раз в {cooldown} минут!")
        return
    
    await update.message.reply_text(
        "✍️ Опишите вашу проблему:\n\n"
        "• Будьте максимально конкретны\n"
        "• Укажите все детали\n"
        "• При необходимости прикрепите скриншоты",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Отмена")]], resize_keyboard=True)
    )
    context.user_data['awaiting_report'] = True

async def process_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    report_id = len(db.data['reports']) + 1
    
    db.data['reports'][str(report_id)] = {
        'id': report_id,
        'user_id': str(user.id),
        'text': update.message.text,
        'timestamp': datetime.now().isoformat(),
        'status': 'open'
    }
    db.data['users'][str(user.id)]['reports_sent'] += 1
    db.data['stats']['total_reports'] += 1
    db.save()
    
    if await is_admin(CONFIG['ADMIN_ID']):
        await context.bot.send_message(
            CONFIG['ADMIN_ID'],
            f"🚨 Новый репорт #{report_id} от @{user.username}",
            reply_markup=get_report_actions(report_id)
        )
    
    await update.message.reply_text(
        "✅ Ваш репорт получен! Мы ответим в ближайшее время.",
        reply_markup=get_main_keyboard(await is_admin(user.id))
    )
    context.user_data['awaiting_report'] = False

# --- АДМИН-ФУНКЦИИ ---
async def show_admin_panel(update: Update):
    await update.message.reply_text(
        "👮 *Админ-панель*",
        reply_markup=get_admin_keyboard(),
        parse_mode="Markdown"
    )

async def show_reports_list(update: Update):
    open_reports = [r for r in db.data['reports'].values() if r['status'] == 'open']
    
    if not open_reports:
        await update.message.reply_text("🎉 Нет активных репортов!")
        return
    
    text = "📨 *Последние репорты:*\n\n"
    for report in sorted(open_reports, key=lambda x: x['timestamp'], reverse=True)[:5]:
        user = db.data['users'].get(report['user_id'], {})
        text += (
            f"⚠️ *#{report['id']}* от @{user.get('username', 'unknown')}\n"
            f"📅 {datetime.fromisoformat(report['timestamp']).strftime('%d.%m %H:%M')}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def show_system_stats(update: Update):
    stats_text = (
        f"📈 *Системная статистика*\n\n"
        f"• Всего пользователей: {len(db.data['users'])}\n"
        f"• Всего репортов: {db.data['stats']['total_reports']}\n"
        f"• Решено репортов: {db.data['stats']['resolved_reports']}\n"
        f"• Заблокированных: {len(db.data['banned_users'])}"
    )
    await update.message.reply_text(stats_text, parse_mode="Markdown")

async def show_users_list(update: Update):
    recent_users = sorted(
        db.data['users'].values(),
        key=lambda x: x['last_activity'],
        reverse=True
    )[:5]
    
    text = "👥 *Последние пользователи:*\n\n"
    for user in recent_users:
        text += (
            f"👤 {user['first_name']} (@{user.get('username', 'нет')})\n"
            f"🕒 Последняя активность: {datetime.fromisoformat(user['last_activity']).strftime('%d.%m %H:%M')}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def show_settings(update: Update):
    await update.message.reply_text(
        "⚙️ *Настройки бота:*",
        reply_markup=get_settings_keyboard(),
        parse_mode="Markdown"
    )

# --- ОБРАБОТЧИКИ CALLBACK ---
async def handle_settings_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await is_admin(query.from_user.id):
        return
    
    setting = query.data.split('_')[1]
    
    if setting == "autorespond":
        db.data['settings']['auto_respond'] = not db.data['settings']['auto_respond']
    elif setting == "notifynewusers":
        db.data['settings']['notify_new_users'] = not db.data['settings']['notify_new_users']
    
    db.save()
    await query.edit_message_reply_markup(reply_markup=get_settings_keyboard())

async def handle_report_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await is_admin(query.from_user.id):
        return
    
    action, report_id = query.data.split('_')
    report = db.data['reports'].get(report_id)
    
    if not report:
        await query.edit_message_text("❌ Репорт не найден")
        return
    
    if action == "resolve":
        db.data['reports'][report_id]['status'] = 'resolved'
        db.data['stats']['resolved_reports'] += 1
        await query.edit_message_text(f"✅ Репорт #{report_id} закрыт")
    elif action == "ban":
        user_id = report['user_id']
        db.data['banned_users'][user_id] = datetime.now().isoformat()
        await context.bot.send_message(
            user_id,
            "🚫 Вы были заблокированы администратором"
        )
        await query.edit_message_text(f"✅ Пользователь {user_id} заблокирован")
    elif action == "details":
        user = db.data['users'].get(report['user_id'], {})
        details = (
            f"🔍 *Детали репорта #{report_id}*\n\n"
            f"👤 Пользователь: {user.get('first_name', 'Unknown')} (@{user.get('username', 'нет')})\n"
            f"📅 Время: {datetime.fromisoformat(report['timestamp']).strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📝 *Сообщение:*\n{report['text']}"
        )
        await query.message.reply_text(details, parse_mode="Markdown")
    elif action == "reply":
        context.user_data['replying_to'] = report_id
        await query.message.reply_text(
            f"✍️ Введите ответ на репорт #{report_id}:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Отмена")]], resize_keyboard=True)
        )

async def send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'replying_to' not in context.user_data:
        return
    
    report_id = context.user_data['replying_to']
    report = db.data['reports'].get(str(report_id))
    
    if not report:
        await update.message.reply_text("❌ Репорт не найден")
        return
    
    try:
        await context.bot.send_message(
            report['user_id'],
            f"📨 *Ответ на ваш репорт #{report_id}:*\n\n{update.message.text}",
            parse_mode="Markdown"
        )
        await update.message.reply_text("✅ Ответ отправлен")
        db.data['reports'][str(report_id)]['status'] = 'resolved'
        db.data['stats']['resolved_reports'] += 1
        db.save()
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    
    del context.user_data['replying_to']

# --- ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    
    user = update.effective_user
    await update_user(user)
    
    if str(user.id) in db.data['banned_users']:
        await update.message.reply_text("🚫 Вы заблокированы и не можете использовать бота.")
        return
    
    text = update.message.text
    
    if text == "🆘 Помощь":
        await show_help(update)
    elif text == "⚠️ Репорт":
        await start_report(update)
    elif text == "📊 Моя статистика":
        await show_user_stats(update)
    elif text == "👮 Админ-панель" and await is_admin(user.id):
        await show_admin_panel(update)
    elif text == "📨 Репорты" and await is_admin(user.id):
        await show_reports_list(update)
    elif text == "📊 Статистика" and await is_admin(user.id):
        await show_system_stats(update)
    elif text == "👥 Пользователи" and await is_admin(user.id):
        await show_users_list(update)
    elif text == "⚙️ Настройки" and await is_admin(user.id):
        await show_settings(update)
    elif text == "🔙 Главное меню":
        await start(update, context)
    elif context.user_data.get('awaiting_report'):
        await process_report(update, context)
    elif 'replying_to' in context.user_data:
        await send_reply(update, context)

# --- ЗАПУСК ---
def main():
    persistence = PicklePersistence(filepath='bot_persistence.pickle')
    application = Application.builder() \
        .token(CONFIG['TOKEN']) \
        .persistence(persistence) \
        .build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчики callback
    application.add_handler(CallbackQueryHandler(handle_settings_toggle, pattern="^toggle_"))
    application.add_handler(CallbackQueryHandler(handle_report_action, pattern="^(reply|resolve|ban|details)_"))
    
    # Запуск
    application.run_polling()

if __name__ == '__main__':
    print("Starting bot...")
    main()
