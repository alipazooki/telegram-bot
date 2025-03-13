import logging
import datetime
import jdatetime  # کتابخانه تاریخ شمسی
from astral import LocationInfo
from astral.sun import sun
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تابع محاسبه وضعیت ماه (بر اساس یک الگوریتم ساده)
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

# تابعی که اطلاعات نجومی را محاسبه و ارسال می‌کند
async def astro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # تاریخ شمسی و ساعت کنونی
    persian_date = jdatetime.date.today().strftime("%Y/%m/%d")
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    
    # تنظیمات موقعیت: تهران (قابل تغییر)
    tehran = LocationInfo("Tehran", "Iran", "Asia/Tehran", 35.6892, 51.3890)
    s = sun(tehran.observer, date=datetime.date.today(), tzinfo=tehran.timezone)
    sunrise = s["sunrise"].strftime("%H:%M")
    sunset = s["sunset"].strftime("%H:%M")
    
    # وضعیت ماه
    moon_phase = get_moon_phase(datetime.date.today())
    
    message = (
        f"📅 تاریخ: {persian_date}\n"
        f"⏰ ساعت: {current_time}\n"
        f"🌅 طلوع آفتاب: {sunrise}\n"
        f"🌇 غروب آفتاب: {sunset}\n"
        f"🌕 وضعیت ماه: {moon_phase}"
    )
    await update.message.reply_text(message)

def main():
    # جایگزین کردن YOUR_BOT_TOKEN_HERE با توکن واقعی ربات شما
    application = Application.builder().token("YOUR_BOT_TOKEN_HERE").build()
    application.add_handler(CommandHandler("astro", astro))
    application.run_polling()

if __name__ == "__main__":
    main()
