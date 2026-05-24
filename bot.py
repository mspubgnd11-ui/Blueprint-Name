import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
import config
import database as db
import api_client as api

logging.basicConfig(level=logging.INFO)

def main_menu(is_admin=False):
    buttons = [
        [InlineKeyboardButton("📱 احصل على رقم واتساب", callback_data="get_number")],
        [InlineKeyboardButton("💰 رصيدي",               callback_data="my_balance")],
        [InlineKeyboardButton("📋 طلباتي",               callback_data="my_orders")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ شحن رصيد مستخدم", callback_data="admin_add"),
         InlineKeyboardButton("➖ خصم رصيد",         callback_data="admin_del")],
        [InlineKeyboardButton("👥 المستخدمين",        callback_data="admin_users")],
        [InlineKeyboardButton("💲 رصيد الـ API",      callback_data="admin_api_bal")],
        [InlineKeyboardButton("🔙 رجوع",              callback_data="back_main")],
    ])

# ══ /start ══════════════════════════════════════════════
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.register_user(u.id, u.username or "", u.full_name or "")
    is_admin = u.id in config.ADMIN_IDS
    await update.message.reply_text(
        f"👋 أهلاً <b>{u.first_name}</b>!\n\n"
        f"📱 بوت الأرقام الافتراضية\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 رصيدك: <b>{db.get_balance(u.id):.0f} {config.CURRENCY}</b>",
        parse_mode="HTML", reply_markup=main_menu(is_admin)
    )

# ══ الأزرار ══════════════════════════════════════════════
async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    uid  = q.from_user.id
    data = q.data
    await q.answer()
    is_admin = uid in config.ADMIN_IDS

    # ─ رجوع ─
    if data == "back_main":
        await q.edit_message_text(
            f"💰 رصيدك: <b>{db.get_balance(uid):.0f} {config.CURRENCY}</b>",
            parse_mode="HTML", reply_markup=main_menu(is_admin))

    # ─ رصيدي ─
    elif data == "my_balance":
        await q.edit_message_text(
            f"💰 <b>رصيدك:</b> {db.get_balance(uid):.0f} {config.CURRENCY}\n\n"
            f"للشحن تواصل مع الإدارة.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))

    # ─ طلباتي ─
    elif data == "my_orders":
        conn = db.get_conn()
        rows = conn.execute(
            "SELECT number, status, otp_code, created_at FROM orders "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (uid,)
        ).fetchall(); conn.close()
        if not rows:
            text = "📋 ما عندك طلبات بعد."
        else:
            lines = ["📋 <b>آخر طلباتك:</b>\n"]
            for r in rows:
                icon = "✅" if r[1]=="done" else ("❌" if r[1]=="cancelled" else "⏳")
                lines.append(f"{icon} <code>{r[0]}</code> | كود: {r[2] or '⏳'}")
            text = "\n".join(lines)
        await q.edit_message_text(text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))

    # ─ احصل على رقم ─
    elif data == "get_number":
        bal = db.get_balance(uid)
        if bal < config.NUMBER_COST:
            await q.edit_message_text(
                f"❌ رصيدك غير كافٍ!\n"
                f"💰 رصيدك: <b>{bal:.0f}</b> | المطلوب: <b>{config.NUMBER_COST}</b> {config.CURRENCY}\n\n"
                f"تواصل مع الإدارة لشحن رصيدك.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])); return

        await q.edit_message_text("⏳ جاري تجهيز رقم عشوائي...")
        try:
            result = await asyncio.wait_for(api.get_whatsapp_number(), timeout=20)
        except asyncio.TimeoutError:
            result = None

        if not result:
            await q.edit_message_text("❌ ما في أرقام متاحة الآن، جرب بعد دقيقة.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔁 حاول مجدداً", callback_data="get_number"),
                    InlineKeyboardButton("🔙 رجوع",        callback_data="back_main")]])); return

        number = result["number"]
        mid    = result["id"]

        db.update_balance(uid, -config.NUMBER_COST, note=f"شراء رقم {number}", tx_type="purchase")
        db.create_order(uid, number, mid, config.NUMBER_COST)

        await q.edit_message_text(
            f"✅ <b>تم تجهيز رقمك!</b>\n\n"
            f"📱 الرقم: <code>{format_number(number)}</code>\n"
            f"💸 التكلفة: <b>{config.NUMBER_COST} {config.CURRENCY}</b>\n"
            f"💰 رصيدك: <b>{db.get_balance(uid):.0f} {config.CURRENCY}</b>\n\n"
            f"⏳ <i>جاري انتظار كود التفعيل... (حتى 5 دقائق)</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ إلغاء واسترجاع الرصيد",
                                     callback_data=f"cancel_{number}")]]))

        ctx.application.create_task(
            wait_for_otp(q, uid, number, mid))

    # ─ إلغاء ─
    elif data.startswith("cancel_"):
        number = data.split("_", 1)[1]
        order  = db.get_order_by_activation(number)
        if order and order[4] not in ("done", "cancelled"):
            await api.release_number(number)
            db.update_order(number, "cancelled")
            db.update_balance(uid, config.NUMBER_COST,
                              note="استرجاع إلغاء", tx_type="refund")
            await q.edit_message_text(
                f"✅ تم الإلغاء!\n"
                f"💰 تم استرجاع <b>{config.NUMBER_COST} {config.CURRENCY}</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))
        else:
            await q.edit_message_text("⚠️ الطلب منتهي أو ملغي مسبقاً.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))

    # ══ أدمن ══
    elif data == "admin_panel" and is_admin:
        await q.edit_message_text("👑 <b>لوحة الأدمن</b>",
                                  parse_mode="HTML", reply_markup=admin_kb())

    elif data == "admin_add" and is_admin:
        ctx.user_data["admin_action"] = "add"
        await q.edit_message_text(
            "✏️ أرسل:\n<code>USER_ID المبلغ</code>\n"
            "مثال: <code>123456789 10</code>", parse_mode="HTML")

    elif data == "admin_del" and is_admin:
        ctx.user_data["admin_action"] = "del"
        await q.edit_message_text(
            "✏️ أرسل:\n<code>USER_ID المبلغ</code>\n"
            "مثال: <code>123456789 5</code>", parse_mode="HTML")

    elif data == "admin_users" and is_admin:
        users = db.get_all_users()
        if not users:
            text = "👥 ما في مستخدمين بعد."
        else:
            lines = [f"👥 <b>المستخدمين ({len(users)}):</b>\n"]
            for u in users[:20]:
                name = u[2] or u[1] or "—"
                lines.append(f"• <code>{u[0]}</code> | {name} | 💰 {u[3]:.0f}")
            text = "\n".join(lines)
        await q.edit_message_text(text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]))

    elif data == "admin_api_bal" and is_admin:
        bal = await api.get_balance_api()
        await q.edit_message_text(
            f"💲 رصيد حساب durianrcs: <b>{bal:.2f}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]))

# ══ انتظار الكود ══════════════════════════════════════════
async def wait_for_otp(query, uid, number, mid):
    waited = 0
    while waited < config.SMS_WAIT_SECONDS:
        await asyncio.sleep(config.SMS_POLL_INTERVAL)
        waited += config.SMS_POLL_INTERVAL

        order = db.get_order_by_activation(number)
        if order and order[4] == "cancelled":
            return

        code = await api.check_otp(number)
        if code:
            db.update_order(number, "done", otp_code=code)
            await query.message.reply_text(
                f"🎉 <b>وصل كود التفعيل!</b>\n\n"
                f"📱 الرقم: <code>{format_number(number)}</code>\n"
                f"🔑 الكود: <code>{code}</code>\n\n"
                f"✅ انسخ الكود واستخدمه الآن!",
                parse_mode="HTML",
                reply_markup=main_menu(uid in config.ADMIN_IDS)); return

    # انتهى الوقت
    db.update_order(number, "expired")
    await api.release_number(number)
    db.update_balance(uid, config.NUMBER_COST,
                      note="استرجاع انتهاء وقت", tx_type="refund")
    await query.message.reply_text(
        f"⏰ <b>انتهى وقت انتظار الكود.</b>\n"
        f"💰 تم استرجاع <b>{config.NUMBER_COST} {config.CURRENCY}</b> تلقائياً.",
        parse_mode="HTML",
        reply_markup=main_menu(uid in config.ADMIN_IDS))

# ══ رسائل الأدمن ══════════════════════════════════════════
async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    action = ctx.user_data.get("admin_action")
    if uid not in config.ADMIN_IDS or not action:
        return
    try:
        parts     = update.message.text.strip().split()
        target_id = int(parts[0])
        amount    = float(parts[1])
    except Exception:
        await update.message.reply_text(
            "❌ صيغة خاطئة.\nمثال: <code>123456789 10</code>",
            parse_mode="HTML"); return

    if not db.get_user(target_id):
        db.register_user(target_id, "", "مستخدم")

    if action == "add":
        db.update_balance(target_id, +amount,
                          note=f"شحن من الأدمن", tx_type="deposit")
        new_bal = db.get_balance(target_id)
        await update.message.reply_text(
            f"✅ تم شحن <b>{amount:.0f} {config.CURRENCY}</b> "
            f"لـ <code>{target_id}</code>\n"
            f"💰 رصيده الآن: <b>{new_bal:.0f}</b>",
            parse_mode="HTML", reply_markup=admin_kb())
        try:
            await ctx.bot.send_message(target_id,
                f"🎉 تم شحن رصيدك!\n"
                f"💰 أُضيف: <b>{amount:.0f} {config.CURRENCY}</b>\n"
                f"💰 رصيدك الآن: <b>{new_bal:.0f} {config.CURRENCY}</b>",
                parse_mode="HTML")
        except Exception: pass
    else:
        db.update_balance(target_id, -amount,
                          note=f"خصم من الأدمن", tx_type="deduct")
        await update.message.reply_text(
            f"✅ تم خصم <b>{amount:.0f} {config.CURRENCY}</b> "
            f"من <code>{target_id}</code>\n"
            f"💰 رصيده الآن: <b>{db.get_balance(target_id):.0f}</b>",
            parse_mode="HTML", reply_markup=admin_kb())

    ctx.user_data.pop("admin_action", None)

# ══ تشغيل ══════════════════════════════════════════════
def main():
    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("✅ البوت شغال!")
    app.run_polling()

if __name__ == "__main__":
    main()


def format_number(number: str) -> str:
    """يحول 9779868649467 إلى (+977) 9868649467"""
    number = number.lstrip("+")
    # قائمة رموز الدول الشائعة حسب الطول
    country_codes = {
        "1": 1, "7": 1, "20": 2, "27": 2, "30": 2, "31": 2, "32": 2,
        "33": 2, "34": 2, "36": 2, "39": 2, "40": 2, "41": 2, "43": 2,
        "44": 2, "45": 2, "46": 2, "47": 2, "48": 2, "49": 2, "51": 2,
        "52": 2, "53": 2, "54": 2, "55": 2, "56": 2, "57": 2, "58": 2,
        "60": 2, "61": 2, "62": 2, "63": 2, "64": 2, "65": 2, "66": 2,
        "81": 2, "82": 2, "84": 2, "86": 2, "90": 2, "91": 2, "92": 2,
        "93": 3, "94": 2, "95": 2, "98": 2,
        "212": 3, "213": 3, "216": 3, "218": 3, "220": 3, "221": 3,
        "234": 3, "249": 3, "251": 3, "254": 3, "255": 3, "256": 3,
        "966": 3, "971": 3, "972": 3, "973": 3, "974": 3, "975": 3,
        "976": 3, "977": 3, "992": 3, "994": 3, "995": 3, "996": 3,
        "998": 3,
    }
    for code, length in sorted(country_codes.items(), key=lambda x: -x[1]):
        if number.startswith(code):
            local = number[len(code):]
            return f"(+{code}) {local}"
    return f"+{number}"
