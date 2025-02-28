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

# شناسه کاربری مدیر (تنها شما)
ALLOWED_USER_ID = 6323600609  # شناسه عددی شما
ALLOWED_GROUPS = {-1001380789897, -1002485718927}  # شناسه گروه‌هایی که پیام‌ها در آن ذخیره شوند

book_pages = []  # لیست برای ذخیره صفحات کتاب
message_history = {}  # دیکشنری جدید برای ذخیره پیام‌ها: کلید (chat_id, message_id)

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
        return  # هیچ پاسخی ارسال نمی‌شود اگر مدیر نباشد

    chat_id = update.effective_chat.id
    context.job_queue.run_repeating(
        send_book_page,  # تابعی که صفحه را ارسال می‌کند
        interval=60*60,  # هر ۱ ساعت یک‌بار (به ثانیه)
        first=0,  # ارسال صفحه اول فوراً
        data={'chat_id': chat_id}
    )
    await update.message.reply_text("📖 ارسال صفحات کتاب شروع شد!")

# تابع برای پردازش تغییر وضعیت اعضای گروه
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in ALLOWED_GROUPS:
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
                until_date=int(time.time()) + 3600  # ۱ ساعت سکوت
            )

            jalali_date = jdatetime.date.today().strftime("%Y/%m/%d")
            welcome_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"سلام [{user.full_name}](tg://user?id={user.id})!\n"
                     f"شما به مدت ۱ ساعت سکوت شده‌اید ⏳\n"
                     f"📅 تاریخ: {jalali_date}\n"
                     f"(این پیام پس از ۱۲۰ ثانیه خودکار حذف می‌شود)",
                parse_mode="Markdown"
            )

            context.job_queue.run_once(
                callback=delete_message,
                when=120,
                data={"chat_id": update.effective_chat.id, "message_id": welcome_msg.message_id}
            )
        except Exception as e:
            logger.error(f"خطا در پردازش عضویت: {str(e)}")

# تابع حذف خودکار پیام پس از ۱۲۰ ثانیه
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

# --- قابلیت ذخیره‌سازی پیام‌های گروه برای ۳ روز و بازیابی پیام‌های حذف‌شده ---

# ذخیره هر پیام ارسالی در گروه‌های مجاز
async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in ALLOWED_GROUPS:
        return
    message = update.message
    if message:
        message_history[(chat_id, message.message_id)] = {
            'text': message.text or "",
            'user_id': message.from_user.id,
            'username': message.from_user.full_name,
            'timestamp': time.time()
        }

# پاکسازی پیام‌های قدیمی‌تر از ۳ روز (هر ساعت یکبار اجرا می‌شود)
async def cleanup_messages(context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    keys_to_delete = []
    for key, data in message_history.items():
        if now - data['timestamp'] > 259200:  # 3 روز به ثانیه (3*24*3600)
            keys_to_delete.append(key)
    for key in keys_to_delete:
        del message_history[key]

# تلاش برای بازیابی پیام حذف‌شده (این قسمت تنها در صورتی کار می‌کند که Telegram به ربات رویداد حذف ارسال کند)
async def deleted_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in ALLOWED_GROUPS:
        return
    # فرض می‌کنیم اطلاعات پیام حذف‌شده در update.message موجود است (ممکن است در عمل اینطور نباشد)
    deleted_msg = update.message
    if not deleted_msg:
        return
    key = (deleted_msg.chat.id, deleted_msg.message_id)
    if key in message_history:
        data = message_history[key]
        user_tag = f"[{data['username']}](tg://user?id={data['user_id']})"
        recovered_text = data['text']
        notification = f"پیام حذف شده توسط کاربر {user_tag}:\n{recovered_text}"
        await context.bot.send_message(chat_id=deleted_msg.chat.id, text=notification, parse_mode="Markdown")
        del message_history[key]

# تابع اصلی اجرای ربات
def main():
    application = Application.builder().token("7753379516:AAFd2mj1fmyRTuWleSQSQRle2-hpTKJauwI").build()
    
    application.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("schedule", schedule_book_pages))  # محدود کردن دستور /schedule به مدیر
    application.add_handler(CommandHandler("page", send_one_page))
    application.add_handler(MessageHandler(filters.TEXT, handle_responses))
    
    # اضافه کردن هندلر ذخیره پیام (به غیر از دستورات)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, store_message), group=1)
    
    # تلاش برای افزودن هندلر دریافت رویداد حذف پیام (ممکن است به درستی کار نکند)
    application.add_handler(MessageHandler(filters.Deleted, deleted_message_handler), group=2)
    
    # زمان‌بندی پاکسازی پیام‌های قدیمی هر ساعت
    application.job_queue.run_repeating(cleanup_messages, interval=3600, first=0)
    
    application.run_polling()

if __name__ == "__main__":
    main()
