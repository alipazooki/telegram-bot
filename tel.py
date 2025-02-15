import time
import logging
import jdatetime  # کتابخانه تاریخ شمسی
import random  # برای ارسال صفحات به صورت تصادفی
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatMemberStatus

# تنظیمات پیشرفته لاگ‌گیری: نمایش فقط پیام‌های هشدار و بالاتر
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING,  # تغییر سطح به WARNING
    handlers=[logging.FileHandler("bot.log", encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# شناسه کاربری شما که فقط شما می‌توانید از ربات استفاده کنید
ALLOWED_USER_ID = 6323600609  # شناسه عددی شما
ALLOWED_GROUPS = {-1001380789897}  # شناسه گروه خود را وارد کنید

# دیکشنری برای تنظیمات پاسخ‌ها
response_dict = {
    'بی معنی': 'به تو چه',
}

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

# تابع برای ارسال یک صفحه از کتاب به صورت تصادفی
async def send_book_page(context: ContextTypes.DEFAULT_TYPE):
    # انتخاب یک صفحه تصادفی از کتاب
    chat_id = context.job.data['chat_id']
    page_text = random.choice(book_pages)  # انتخاب تصادفی صفحه
    await context.bot.send_message(chat_id=chat_id, text=page_text)

# تابع برای ارسال یک صفحه از کتاب در دستور جدید
async def send_one_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال یک صفحه از کتاب با دستور جدید"""
    if update.effective_user.id != ALLOWED_USER_ID:
        # اگر فرستنده پیام شما نیستید، دستوری ارسال نمی‌شود
        await update.message.reply_text("شما مجاز به استفاده از این دستور نیستید.")
        return

    # ارسال صفحه فعلی از کتاب
    chat_id = update.effective_chat.id
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

# دستور /start برای شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start"""
    await update.message.reply_text("🤖 ربات فعال است!")

# دستور /ping برای بررسی وضعیت
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی وضعیت"""
    await update.message.reply_text("🟢 ربات آنلاین است!")

# پاسخ به "بی معنی"
async def handle_bi_manayi(update, context):
    await update.message.reply_text(response_dict.get('بی معنی', 'به تو چه'))

# تنظیم پاسخ‌های جدید
async def set_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("شما مجاز به تغییر تنظیمات نیستید.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("لطفاً فرمت صحیح دستور را وارد کنید: /set_response <command> <response>")
        return

    command = context.args[0]
    response = " ".join(context.args[1:])

    response_dict[command] = response
    await update.message.reply_text(f"پاسخ برای دستور '{command}' به '{response}' تغییر یافت.")

def main():
    # توکن واقعی ربات خود را جایگزین کنید
    application = Application.builder().token("7753379516:AAFd2mj1fmyRTuWleSQSQRle2-hpTKJauwI").build()
    application.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("schedule", schedule_book_pages))  # اضافه کردن دستور برای زمان‌بندی ارسال صفحات
    application.add_handler(CommandHandler("page", send_one_page))  # اضافه کردن دستور برای ارسال یک صفحه
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('بی معنی'), handle_bi_manayi))  # پاسخ به "بی معنی"
    application.add_handler(CommandHandler("set_response", set_response))  # اضافه کردن دستور برای تغییر پاسخ‌ها
    application.run_polling()

if __name__ == "__main__":
    main()
