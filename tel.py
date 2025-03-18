import time
import logging
import jdatetime  # کتابخانه تاریخ شمسی
import random  # برای ارسال صفحات به صورت تصادفی
import datetime  # برای تاریخ و زمان میلادی
from zoneinfo import ZoneInfo  # برای تنظیم منطقه زمانی
from astral import LocationInfo
from astral.sun import sun
import ephem  # برای محاسبه موقعیت زودیاک ماه و سایر محاسبات نجومی
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters, ChatMemberHandler
)
from telegram.constants import ChatMemberStatus

# تنظیمات پیشرفته لاگ‌گیری
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    handlers=[logging.FileHandler("bot.log", encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

ALLOWED_USER_ID = 6323600609  # شناسه کاربری مدیر
ALLOWED_GROUPS = {-1001380789897, -1002485718927}  # شناسه گروه‌های مجاز
ENABLE_MUTE_ON_JOIN = True  # قابلیت سکوت ورود اعضا

book_pages = []

def load_book():
    with open('book.txt', 'r', encoding='utf-8') as file:
        content = file.read()
    pages = content.split('<page>')[1:]
    pages = [page.split('</page>')[0].strip() for page in pages]
    return pages

def load_responses():
    responses = {}
    with open('responses.txt', 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            question = lines[i].strip()
            answer = lines[i+1].strip()
            responses[question] = answer
    return responses

responses_dict = load_responses()
book_pages = load_book()

async def handle_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    if user_message in responses_dict:
        await update.message.reply_text(responses_dict[user_message])

user_page_usage = {}

async def send_book_page(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    page_text = random.choice(book_pages)
    await context.bot.send_message(chat_id=chat_id, text=page_text)

async def send_one_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if user_id == ALLOWED_USER_ID:
        page_text = random.choice(book_pages)
        await context.bot.send_message(chat_id=chat_id, text=page_text)
        return
    current_date = jdatetime.date.today().strftime("%Y/%m/%d")
    usage = user_page_usage.get(user_id)
    if usage:
        last_date, count = usage
        if last_date == current_date:
            if count >= 2:
                await update.message.reply_text("شما امروز از این دستور استفاده کرده‌اید. لطفاً فردا دوباره امتحان کنید.")
                return
            else:
                user_page_usage[user_id] = (current_date, count + 1)
        else:
            user_page_usage[user_id] = (current_date, 1)
    else:
        user_page_usage[user_id] = (current_date, 1)
    page_text = random.choice(book_pages)
    await context.bot.send_message(chat_id=chat_id, text=page_text)

async def schedule_book_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    chat_id = update.effective_chat.id
    job = context.job_queue.run_repeating(
        send_book_page,
        interval=60 * 60,
        first=0,
        data={'chat_id': chat_id}
    )
    context.chat_data["book_schedule"] = job
    await update.message.reply_text("📖 ارسال صفحات کتاب شروع شد!")

async def cancel_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("شما اجازه تغییر تنظیمات را ندارید.")
        return
    job = context.chat_data.get("book_schedule")
    if job:
        job.schedule_removal()
        del context.chat_data["book_schedule"]
        await update.message.reply_text("📖 قالب پخش صفحات کتاب غیرفعال شد!")
    else:
        await update.message.reply_text("قالب پخش صفحات کتاب فعال نیست.")

async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in ALLOWED_GROUPS:
        return
    if not ENABLE_MUTE_ON_JOIN:
        return
    old_status = update.chat_member.old_chat_member.status
    new_status = update.chat_member.new_chat_member.status
    user = update.chat_member.new_chat_member.user
    if old_status == ChatMemberStatus.LEFT and new_status == ChatMemberStatus.MEMBER:
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=int(time.time()) + 3600
            )
            jalali_date = jdatetime.date.today().strftime("%Y/%m/%d")
            welcome_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"سلام [{user.full_name}](tg://user?id={user.id})!\n"
                     f"شما به مدت 1 ساعت سکوت شده‌اید ⏳\n"
                     f"📅 تاریخ: {jalali_date}\n"
                     f"(این پیام پس از 120 ثانیه خودکار حذف می‌شود)",
                parse_mode="Markdown"
            )
            context.job_queue.run_once(
                callback=delete_message,
                when=120,
                data={"chat_id": update.effective_chat.id, "message_id": welcome_msg.message_id}
            )
        except Exception as e:
            logger.error(f"خطا در پردازش عضویت: {str(e)}")

async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    message_id = job_data.get("message_id")
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"✅ پیام {message_id} حذف شد!")
    except Exception as e:
        logger.error(f"❌ خطا در حذف پیام: {str(e)}")

def get_moon_phase(date: datetime.date) -> str:
    dt = datetime.datetime(date.year, date.month, date.day)
    diff = dt - datetime.datetime(2001, 1, 1)
    days = diff.days + diff.seconds / 86400.0
    lunations = days / 29.53058867
    phase = lunations - int(lunations)
    if phase < 0:
        phase += 1
    if phase < 0.03 or phase > 0.97:
        return "ماه نو"
    elif phase < 0.22:
        return "هلال نوظهور"
    elif phase < 0.28:
        return "اولین ربع"
    elif phase < 0.47:
        return "ماه چوبکی (ابراب)"
    elif phase < 0.53:
        return "ماه کامل"
    elif phase < 0.72:
        return "ماه هلالی"
    elif phase < 0.78:
        return "آخرین ربع"
    else:
        return "ماه کم‌رونده"

def get_persian_weekday(date: datetime.date) -> str:
    weekdays = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"]
    return weekdays[date.weekday()]

def get_moon_zodiac() -> (str, float):
    moon = ephem.Moon()
    moon.compute()
    ecl = ephem.Ecliptic(moon)
    lon_deg = float(ecl.lon) * 180.0 / 3.141592653589793
    lon_deg = lon_deg % 360
    zodiac_signs = [
        ("حمل", 0, 30),
        ("ثور", 30, 60),
        ("جوزا", 60, 90),
        ("سرطان", 90, 120),
        ("اسد", 120, 150),
        ("سنبله", 150, 180),
        ("میزان", 180, 210),
        ("عقرب", 210, 240),
        ("قوس", 240, 270),
        ("جدی", 270, 300),
        ("دلو", 300, 330),
        ("حوت", 330, 360)
    ]
    for sign, start, end in zodiac_signs:
        if start <= lon_deg < end:
            return sign, lon_deg
    return "نامشخص", lon_deg

def get_ruling_planet(zodiac: str) -> str:
    mapping = {
        "حمل": "مریخ",
        "ثور": "زهره",
        "جوزا": "عطارد",
        "سرطان": "ماه",
        "اسد": "خورشید",
        "سنبله": "عطارد",
        "میزان": "زهره",
        "عقرب": "مریخ",
        "قوس": "مشتری",
        "جدی": "زحل",
        "دلو": "زحل",
        "حوت": "مشتری"
    }
    return mapping.get(zodiac, "نامشخص")

# در /astro، اطلاعات نجومی شامل خلاصه اوقات اذان (فجر، ظهر و مغرب) به علاوه اطلاعات اضافی نجومی نمایش داده می‌شود.
async def send_astronomical_info(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    current_tehran_date = datetime.datetime.now(ZoneInfo("Asia/Tehran")).date()
    persian_date = jdatetime.date.fromgregorian(date=current_tehran_date).strftime("%Y/%m/%d")
    current_time = datetime.datetime.now(ZoneInfo("Asia/Tehran")).strftime("%H:%M:%S")
    weekday = get_persian_weekday(current_tehran_date)
    
    tehran = LocationInfo("Tehran", "Iran", "Asia/Tehran", 35.6892, 51.3890)
    s = sun(tehran.observer, date=current_tehran_date, tzinfo=tehran.timezone)
    
    fajr = s['dawn'].strftime('%H:%M')
    zuhr = s['noon'].strftime('%H:%M')
    maghrib = s['sunset'].strftime('%H:%M')
    
    day_length_td = s['sunset'] - s['sunrise']
    hours, remainder = divmod(day_length_td.seconds, 3600)
    minutes = remainder // 60
    day_length = f"{hours}ساعت {minutes}دقیقه"
    
    moon_phase = get_moon_phase(current_tehran_date)
    moon_zodiac, moon_lon = get_moon_zodiac()
    ruling_planet = get_ruling_planet(moon_zodiac)
    
    moon_for_illum = ephem.Moon()
    moon_for_illum.compute(current_tehran_date)
    illumination = moon_for_illum.phase
    
    next_new = ephem.next_new_moon(current_tehran_date)
    next_full = ephem.next_full_moon(current_tehran_date)
    local_next_new = next_new.datetime().astimezone(ZoneInfo("Asia/Tehran")).strftime("%Y/%m/%d %H:%M")
    local_next_full = next_full.datetime().astimezone(ZoneInfo("Asia/Tehran")).strftime("%Y/%m/%d %H:%M")
    
    message = (
        f"📅 تاریخ: {persian_date} ({weekday})\n"
        f"⏰ ساعت: {current_time}\n\n"
        "🕌 اوقات اذان:\n"
        f"• فجر: {fajr}\n"
        f"• ظهر: {zuhr}\n"
        f"• مغرب: {maghrib}\n"
        f"• طول روز: {day_length}\n\n"
        f"🌕 وضعیت ماه: {moon_phase}\n"
        f"🌙 موقعیت زودیاک ماه: {moon_zodiac} ({moon_lon:.0f}°)\n"
        f"🏠 منزل ماه: {get_ruling_planet(moon_zodiac)}\n"
        f"💡 درصد روشنایی ماه: {illumination:.1f}%\n"
        f"🌑 ماه نو بعدی: {local_next_new}\n"
        f"🌕 ماه کامل بعدی: {local_next_full}"
    )
    
    await context.bot.send_message(chat_id=chat_id, text=message)

# نسخه دریافت اطلاعات نجومی به صورت آنی (/astro)
async def astro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_tehran_date = datetime.datetime.now(ZoneInfo("Asia/Tehran")).date()
    persian_date = jdatetime.date.fromgregorian(date=current_tehran_date).strftime("%Y/%m/%d")
    current_time = datetime.datetime.now(ZoneInfo("Asia/Tehran")).strftime("%H:%M:%S")
    weekday = get_persian_weekday(current_tehran_date)
    
    tehran = LocationInfo("Tehran", "Iran", "Asia/Tehran", 35.6892, 51.3890)
    s = sun(tehran.observer, date=current_tehran_date, tzinfo=tehran.timezone)
    
    fajr = s['dawn'].strftime('%H:%M')
    zuhr = s['noon'].strftime('%H:%M')
    maghrib = s['sunset'].strftime('%H:%M')
    
    day_length_td = s['sunset'] - s['sunrise']
    hours, remainder = divmod(day_length_td.seconds, 3600)
    minutes = remainder // 60
    day_length = f"{hours}ساعت {minutes}دقیقه"
    
    moon_phase = get_moon_phase(current_tehran_date)
    moon_zodiac, moon_lon = get_moon_zodiac()
    ruling_planet = get_ruling_planet(moon_zodiac)
    
    moon_for_illum = ephem.Moon()
    moon_for_illum.compute(current_tehran_date)
    illumination = moon_for_illum.phase
    
    next_new = ephem.next_new_moon(current_tehran_date)
    next_full = ephem.next_full_moon(current_tehran_date)
    local_next_new = next_new.datetime().astimezone(ZoneInfo("Asia/Tehran")).strftime("%Y/%m/%d %H:%M")
    local_next_full = next_full.datetime().astimezone(ZoneInfo("Asia/Tehran")).strftime("%Y/%m/%d %H:%M")
    
    message = (
        f"📅 تاریخ: {persian_date} ({weekday})\n"
        f"⏰ ساعت: {current_time}\n\n"
        "🕌 اوقات اذان:\n"
        f"• فجر: {fajr}\n"
        f"• ظهر: {zuhr}\n"
        f"• مغرب: {maghrib}\n"
        f"• طول روز: {day_length}\n\n"
        f"🌕 وضعیت ماه: {moon_phase}\n"
        f"🌙 موقعیت زودیاک ماه: {moon_zodiac} ({moon_lon:.0f}°)\n"
        f"🏠 منزل ماه: {ruling_planet}\n"
        f"💡 درصد روشنایی ماه: {illumination:.1f}%\n"
        f"🌑 ماه نو بعدی: {local_next_new}\n"
        f"🌕 ماه کامل بعدی: {local_next_full}"
    )
    await context.bot.send_message(chat_id=chat_id, text=message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 ربات فعال است!")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 ربات آنلاین است!")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("شما اجازه دسترسی به این بخش را ندارید.")
        return
    logger.info("admin_panel called by allowed user")
    msg = ("پنل مدیریت ربات:\n"
           "برای تغییر وضعیت سکوت ورود اعضا از دستور /toggle_mute استفاده کنید.\n"
           "برای زمان‌بندی ارسال اطلاعات نجومی از دستور /schedule_astro استفاده کنید.\n"
           "برای دریافت اطلاعات نجومی به صورت آنی از دستور /astro استفاده کنید.\n"
           "برای لغو پخش صفحات کتاب از دستور /cancel_schedule استفاده کنید.")
    await update.message.reply_text(msg)

async def toggle_mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ENABLE_MUTE_ON_JOIN
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("شما اجازه تغییر تنظیمات را ندارید.")
        return
    ENABLE_MUTE_ON_JOIN = not ENABLE_MUTE_ON_JOIN
    state_text = "فعال" if ENABLE_MUTE_ON_JOIN else "غیرفعال"
    logger.info(f"ENABLE_MUTE_ON_JOIN toggled to {ENABLE_MUTE_ON_JOIN} by user {update.effective_user.id}")
    await update.message.reply_text(f"سکوت ورود اعضا اکنون {state_text} است.")

async def schedule_astro_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("شما اجازه استفاده از این دستور را ندارید.")
        return
    chat_id = update.effective_chat.id
    context.job_queue.run_repeating(
        send_astronomical_info,
        interval=10800,  # 3 ساعت = 10800 ثانیه
        first=0,
        data={'chat_id': chat_id}
    )
    await update.message.reply_text("✅ ارسال اطلاعات نجومی هر ۳ ساعت آغاز شد.")

def main():
    application = Application.builder().token("7753379516:AAFd2mj1fmyRTuWleSQSQRle2-hpTKJauwI").build()
    application.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("schedule", schedule_book_pages))
    application.add_handler(CommandHandler("cancel_schedule", cancel_schedule))
    # دستور /page حذف شده است (غیر فعال)
    application.add_handler(CommandHandler("admin_panel", admin_panel))
    application.add_handler(CommandHandler("toggle_mute", toggle_mute_command))
    application.add_handler(CommandHandler("schedule_astro", schedule_astro_info))
    application.add_handler(CommandHandler("astro", astro_command))
    application.add_handler(MessageHandler(filters.TEXT, handle_responses))
    application.run_polling()

if __name__ == "__main__":
    main()
