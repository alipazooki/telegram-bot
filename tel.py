import time
import logging
import jdatetime  # کتابخانه تاریخ شمسی
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes, ChatMemberHandler
from telegram.constants import ChatMemberStatus

# تنظیمات پیشرفته لاگ‌گیری: نمایش فقط پیام‌های هشدار و بالاتر
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING,  # تغییر سطح به WARNING
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# تنظیم سطح لاگ برای کتابخانه‌های خاص
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

ALLOWED_GROUPS = {-1001380789897}  # شناسه گروه خود را وارد کنید

book_pages = []  # لیست برای ذخیره صفحات کتاب
page_index = 0  # ایندکس صفحه فعلی

# بارگذاری کتاب از فایل
def load_book():
    with open('book.txt', 'r', encoding='utf-8') as file:
        content = file.read()
    pages = content.split('<page>')[1:]  # قسمت اول قبل از اولین <page> را حذف می‌کنیم
    pages = [page.split('</page>')[0].strip() for page in pages]  # حذف <page> و </page> از صفحات
    return pages

book_pages = load_book()  # بارگذاری کتاب

async def send_book_page(context: ContextTypes.DEFAULT_TYPE):
    global page_index

    # ارسال صفحه فعلی از کتاب
    chat_id = context.job.data['chat_id']
    page_text = book_pages[page_index]
    await context.bot.send_message(chat_id=chat_id, text=page_text)

    # به صفحه بعدی برو
    page_index = (page_index + 1) % len(book_pages)

async def schedule_book_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زمان‌بندی ارسال صفحات کتاب"""
    chat_id = update.effective_chat.id
    context.job_queue.run_repeating(
        send_book_page,  # تابعی که صفحه را ارسال می‌کند
        interval=60*60*3,  # هر 3 ساعت یک‌بار (به ثانیه)
        first=0,  # ارسال صفحه اول فوراً
        data={'chat_id': chat_id}
    )
    await update.message.reply_text("📖 ارسال صفحات کتاب شروع شد!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start"""
    await update.message.reply_text("🤖 ربات فعال است!")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی وضعیت"""
    await update.message.reply_text("🟢 ربات آنلاین است!")

def main():
    # توکن واقعی ربات خود را جایگزین کنید
    application = Application.builder().token("7753379516:AAFd2mj1fmyRTuWleSQSQRle2-hpTKJauwI").build()
    application.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("schedule", schedule_book_pages))  # اضافه کردن دستور برای زمان‌بندی ارسال صفحات
    application.run_polling()

if __name__ == "__main__":
    main()
