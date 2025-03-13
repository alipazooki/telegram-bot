import time
import logging
import jdatetime  # کتابخانه تاریخ شمسی
import random  # برای ارسال صفحات به صورت تصادفی
import datetime  # برای تاریخ و زمان میلادی
from zoneinfo import ZoneInfo  # برای تنظیم منطقه زمانی
from astral import LocationInfo
from astral.sun import sun
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters, ChatMemberHandler
)
from telegram.constants import ChatMemberStatus

# تنظیمات پیشرفته لاگ‌گیری: سطح لاگ DEBUG جهت عیب‌یابی.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    handlers=[logging.FileHandler("bot.log", encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# تنظیم سطح لاگ برای کتابخانه‌های خاص
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# شناسه کاربری مدیر (تنها شما)
ALLOWED_USER_ID = 6323600609  # شناسه عددی شما
ALLOWED_GROUPS = {-1001380789897, -1002485718927}  # شناسه گروه‌های مجاز

# تنظیمات ویژگی‌ها (قابلیت‌ها)
ENABLE_MUTE_ON_JOIN = True  # قابلیت سکوت ورود اعضا

book_pages = []  # لیست برای ذخیره صفحات کتاب

# بارگذاری کتاب از فایل
def load_book():
    with open('book.txt', 'r', encoding='utf-8') as file:
        content = file.read()
    pages = content.split('<page>')[1:]  # حذف قسمت اول قبل از اولین <page>
    pages = [page.split('</page>')[0].strip() for page in pages]
    return pages

# بارگذاری سوالات و پاسخ‌ها از فایل
def load_responses():
    responses = {}
    with open('responses.txt', 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            question = lines[i].strip()
            answer = lines[i+1].strip()
            responses[question] = answer
    return responses

responses_dict = load_responses()  # بارگذاری سوالات و پاسخ‌ها
book_pages = load_book()  # بارگذاری کتاب

# تابع برای پردازش پیام‌های متنی جهت پاسخ به سوالات
async def handle_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    if user_message in responses_dict:
        await update.message.reply_text(responses_dict[user_message])

# دیکشنری برای ردیابی تعداد استفاده از دستور /page به ازای هر کاربر در روز
user_page_usage = {}

# تابع برای ارسال یک صفحه از کتاب به صورت تصادفی (برای زمان‌بندی)
async def send_book_page(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    page_text = random.choice(book_pages)  # انتخاب تصادفی صفحه
    await context.bot.send_message(chat_id=chat_id, text=page_text)

# تابع برای ارسال یک صفحه از کتاب در دستور /page با محدودیت روزانه برای کاربران غیر مدیر
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
                await update.message.reply_text("شما امروز از این دستور استفاده کرده‌اید. لطفاً فردا دوباره امتحان کنید
