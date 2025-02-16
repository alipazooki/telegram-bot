import time
import logging
import jdatetime  # کتابخانه تاریخ شمسی
import random  # برای ارسال صفحات به صورت تصادفی
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ChatMemberHandler
from telegram.constants import ChatMemberStatus

# تنظیمات پیشرفته لاگ‌گیری: نمایش فقط پیام‌های هشدار و بالاتر
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING,  # تغییر سطح به WARNING
    handlers=[logging.FileHandler("bot.log", encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# تنظیم سطح لاگ برای کتابخانه‌های خاص
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# شناسه کاربری شما که فقط شما می‌توانید از ربات استفاده کنید
ALLOWED_USER_ID = 6323600609  # شناسه عددی شما
ALLOWED_GROUPS = {-1001380789897}  # شناسه گروه خود را وارد کنید

book_pages = []  # لیست برای ذخیره صفحات کتاب

# بارگذاری کتاب از فایل
def load_book():
    with open('book.txt', 'r', encoding='utf-8') as file:
        content = file.read()
    pages = content.split('<page>')[1:]  # قسمت اول قبل از اولین <page> را حذف می‌کنیم
    pages = [page.split('</page>')[0].strip() for page in pages]  # حذف <page> و </page> از صفحات
    return pages

# بارگذاری سوالات و پاسخ‌ها از فایل
def load_responses():
    responses = {}
    with open('responses.txt', 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            question = lines[i].strip()
            answer = lines[i + 1].strip()
            responses[question] = answer
    return responses

responses_dict = load_responses()  # بارگذاری سوالات و پاسخ‌ها
book_pages = load_book()  # بارگذاری کتاب

# دیکشنری برای ردیابی تعداد استفاده از دستور /page به ازای هر کاربر در روز
user_page_usage = {}

# تابع برای ارسال یک صفحه از کتاب به صورت تصادفی (برای زمان‌بندی)
async def send_book_page(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    page_text = random.choice(book_pages)  # انتخاب تصادفی صفحه
    await context.bot.send_message(chat_id=chat_id, text=page_text)

# تابع برای ارسال یک صفحه از کتاب در دستور /page با محدودیت روزانه برای کاربران غیر مدیر
async def send_one_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال یک صفحه از کتاب با دستور جدید با محدودیت روزانه برای کاربران غیر مدیر"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # برای مدیر بدون محدودیت اجرا شود
    if user_id == ALLOWED_USER_ID:
        page_text = random.choice(book_pages)  # انتخاب تصادفی صفحه
        await context.bot.send_message(chat_id=chat_id, text=page_text)
        return

    # دریافت تاریخ شمسی فعلی به عنوان شاخص
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

    page_text = random.choice(book_pages)  # انتخاب تصادفی صفحه
    await context.bot.send_message(chat_id=chat_id, text=page_text)

# تابع برای زمان‌بندی ارسال صفحات کتاب
async def schedule_book_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زمان‌بندی ارسال صفحات کتاب"""
    chat_id = update.effective_chat.id
    context.job_queue.run_repeating(
        send_book_page,  # تابعی که صفحه را ارسال می‌کند
        interval=60*60,  # هر 1 ساعت یک‌بار (به ثانیه)
        first=0,  # ارسال صفحه اول فوراً
        data={'chat_id': chat_id}
    )
    await update.message.reply_text("📖 ارسال صفحات کتاب شروع شد!")

# تابع برای پردازش تغییر وضعیت اعضای گروه
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش عضویت کاربران جدید"""
    if update.effective_chat.id not in ALLOWED_GROUPS:
        return

    old_status = update.chat_member.old_chat_member.status
    new_status = update.chat_member.new_chat_member.status
    user = update.chat_member.new_chat_member.user

    if old_status == ChatMemberStatus.LEFT and new_status == ChatMemberStatus.MEMBER:
        try:
            # محدودیت ۳ ساعته
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=int(time.time()) + 10800  # 3 ساعت
            )

            # دریافت تاریخ شمسی فعلی
            jalali_date = jdatetime.date.today().strftime("%Y/%m/%d")  # فرمت: ۱۴۰۲/۰۷/۲۵

            # ارسال پیام خوش‌آمدگویی با تاریخ شمسی
            welcome_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"سلام [{user.full_name}](tg://user?id={user.id})!\n"
                     f"شما به مدت ۳ ساعت سکوت شده‌اید ⏳\n"
                     f"📅 تاریخ: {jalali_date}\n"
                     f"(این پیام پس از ۱۲۰ ثانیه خودکار حذف می‌شود)",
                parse_mode="Markdown"
            )

            # زمان‌بندی حذف پیام
            context.job_queue.run_once(
                callback=delete_message,
                when=120,  # تغییر زمان حذف پیام به 120 ثانیه
                data={"chat_id": update.effective_chat.id, "message_id": welcome_msg.message_id}
            )
        except Exception as e:
            logger.error(f"خطا در پردازش عضویت: {str(e)}")

# تابع حذف خودکار پیام
async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    """حذف خودکار پیام پس از ۱۲۰ ثانیه"""
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    message_id = job_data.get("message_id")
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"✅ پیام {message_id} حذف شد!")
    except Exception as e:
        logger.error(f"❌ خطا در حذف پیام: {str(e)}")

# پاسخ به سوالات در فایل responses.txt
async def handle_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    if user_message in responses_dict:
        await update.message.reply_text(responses_dict[user_message])

# دستور /start برای شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start"""
    await update.message.reply_text("🤖 ربات فعال است!")

# دستور /ping برای بررسی وضعیت
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
    application.add_handler(CommandHandler("page", send_one_page))  # اضافه کردن دستور برای ارسال یک صفحه با محدودیت روزانه برای کاربران غیر مدیر
    application.add_handler(MessageHandler(filters.TEXT, handle_responses))  # پاسخ به سوالات موجود در responses.txt
    application.run_polling()

if __name__ == "__main__":
    main()
