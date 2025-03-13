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
    level=logging.WARNING,
    handlers=[logging.FileHandler("bot.log", encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# تنظیم سطح لاگ برای کتابخانه‌های خاص
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# شناسه کاربری مدیر (تنها شما) و شناسه گروه‌های مجاز
ALLOWED_USER_ID = 6323600609
ALLOWED_GROUPS = {-1001380789897, -1002485718927}

book_pages = []  # لیست برای ذخیره صفحات کتاب

# بارگذاری کتاب از فایل
def load_book():
    with open('book.txt', 'r', encoding='utf-8') as file:
        content = file.read()
    pages = content.split('<page>')[1:]
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

# دیکشنری برای ردیابی تعداد استفاده از دستور /page به ازای هر کاربر در روز
user_page_usage = {}

# متغیر سراسری جهت کنترل امکان سکوت خودکار به محض ورود
AUTO_MUTE_ENABLED = True

# تابع برای ارسال یک صفحه از کتاب به صورت تصادفی (برای زمان‌بندی)
async def send_book_page(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    page_text = random.choice(book_pages)
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

# تابع برای زمان‌بندی ارسال صفحات کتاب (فقط مدیر مجاز است)
async def schedule_book_pages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    chat_id = update.effective_chat.id
    context.job_queue.run_repeating(
        send_book_page,
        interval=60*60,
        first=0,
        data={'chat_id': chat_id}
    )
    await update.message.reply_text("📖 ارسال صفحات کتاب شروع شد!")

# تابع پردازش تغییر وضعیت اعضای گروه با در نظر گرفتن تنظیم سکوت خودکار
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in ALLOWED_GROUPS:
        return

    # در صورتی که امکان سکوت خودکار غیرفعال باشد، عملیات سکوت انجام نمی‌شود.
    if not AUTO_MUTE_ENABLED:
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
                until_date=int(time.time()) + 3600  # سکوت 1 ساعته
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

# تابع حذف خودکار پیام پس از 120 ثانیه
async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    message_id = job_data.get("message_id")
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"✅ پیام {message_id} حذف شد!")
    except Exception as e:
        logger.error(f"❌ خطا در حذف پیام: {str(e)}")

# پاسخ به سوالات از فایل responses.txt
async def handle_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    if user_message in responses_dict:
        await update.message.reply_text(responses_dict[user_message])

# دستور /start برای شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 ربات فعال است!")

# دستور /ping برای بررسی وضعیت
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 ربات آنلاین است!")

# دستور جهت غیرفعال کردن سکوت خودکار (فقط توسط مدیر)
async def disable_auto_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_MUTE_ENABLED
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    AUTO_MUTE_ENABLED = False
    await update.message.reply_text("امکان سکوت خودکار به محض ورود غیرفعال شد.")

# دستور جهت فعال کردن مجدد سکوت خودکار (فقط توسط مدیر)
async def enable_auto_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_MUTE_ENABLED
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    AUTO_MUTE_ENABLED = True
    await update.message.reply_text("امکان سکوت خودکار به محض ورود فعال شد.")

def main():
    application = Application.builder().token("7753379516:AAFd2mj1fmyRTuWleSQSQRle2-hpTKJauwI").build()
    application.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("schedule", schedule_book_pages))
    application.add_handler(CommandHandler("page", send_one_page))
    # افزودن دستورات مدیریت جهت کنترل سکوت خودکار
    application.add_handler(CommandHandler("disablemute", disable_auto_mute))
    application.add_handler(CommandHandler("enablemute", enable_auto_mute))
    application.add_handler(MessageHandler(filters.TEXT, handle_responses))
    application.run_polling()

if __name__ == "__main__":
    main()
