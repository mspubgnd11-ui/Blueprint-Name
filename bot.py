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

# orders table columns:
# 0=id, 1=user_id, 2=number, 3=activation_id, 4=service, 5=status, 6=otp_code, 7=cost

def format_number(number: str) -> str:
    n = str(number).lstrip("+").strip()
    codes = ["998","996","995","994","992","977","976","975","974","973","972",
             "971","966","256","255","254","251","249","234","221","220","218",
             "216","213","212","98","95","94","93","92","91","90","86","84",
             "82","81","66","65","64","63","62","61","60","58","57","56","55",
             "54","53","52","51","49","48","47","46","45","44","43","41","40",
             "39","36","34","33","32","31","30","27","20","7","1"]
    for code in codes:
        if n.startswith(code):
            return f"(+{code}) {n[len(code):]}"
    return f"+{n}"

def number_kb(number: str) -> InlineKeyboardMarkup:
    """الكيبورد بعد الحصول على رقم"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 طلب الكود",    callback_data=f"getotp_{number}"),
         InlineKeyboardButton("🔄 تبديل الرقم",  callback_data=f"swap_{number}")],
        [InlineKeyboardButton("❌ إلغاء واسترجاع الرصيد", callback_data=f"cancel_{number}")],
    ])

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
        [InlineKeyboardButton("➕ شحن رصيد", callback_data="admin_add"),
         InlineKeyboardButton("➖ خصم رصيد", callback_data="admin_del")],
        [InlineKeyboardButton("👥 المستخدمين",   callback_data="admin_users")],
        [InlineKeyboardButton("💲 رصيد الـ API", callback_data="admin_api_bal")],
        [InlineKeyboardButton("🔙 رجوع",         callback_data="back_main")],
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

# ══ مساعد: جلب رقم جديد ══════════════════════════════════
async def fetch_and_send_number(q, uid, is_admin, deduct=True):
    """يجلب رقم ويرسله — deduct=False لما يكون تبديل"""
    await q.edit_message_text("⏳ جاري تجهيز رقم من الموقع...")
    try:
        result = await asyncio.wait_for(api.get_whatsapp_number(), timeout=20)
    except asyncio.TimeoutError:
        result = None

    if not result:
        await q.edit_message_text(
            "❌ ما في أرقام متاحة الآن، جرب بعد دقيقة.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔁 حاول مجدداً", callback_data="get_number"),
                InlineKeyboardButton("🔙 رجوع",        callback_data="back_main")]]))
        return None

    number = result["number"]
    mid    = result["id"]

    if deduct:
        db.update_balance(uid, -config.NUMBER_COST,
                          note=f"شراء رقم {number}", tx_type="purchase")
    db.create_order(uid, number, mid, config.NUMBER_COST)

    await q.edit_message_text(
        f"✅ <b>تم تجهيز رقمك!</b>\n\n"
        f"📱 الرقم: <code>{format_number(number)}</code>\n"
        f"💸 التكلفة: <b>{config.NUMBER_COST} {config.CURRENCY}</b>\n"
        f"💰 رصيدك: <b>{db.get_balance(uid):.0f} {config.CURRENCY}</b>\n\n"
        f"⏳ <i>انتظر الكود أو اضغط «طلب الكود» يدوياً</i>",
        parse_mode="HTML",
        reply_markup=number_kb(number)
    )

    q._application.create_task(wait_for_otp(q, uid, number, mid))
    return number

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
                icon = "✅" if r[1]=="done" else ("❌" if r[1] in ("cancelled","expired") else "⏳")
                lines.append(f"{icon} <code>{format_number(r[0])}</code> | {r[2] or '⏳ انتظار'}")
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
        await fetch_and_send_number(q, uid, is_admin, deduct=True)

    # ─ طلب الكود يدوياً ─
    elif data.startswith("getotp_"):
        number = data.split("_", 1)[1]
        order  = db.get_order_by_activation(number)
        if not order or order[5] in ("done", "cancelled", "expired"):
            await q.answer("⚠️ هذا الطلب منتهي.", show_alert=True); return
        await q.answer("⏳ جاري التحقق من الكود...")
        code = await api.check_otp(number)
        if code:
            db.update_order(number, "done", otp_code=code)
            await q.edit_message_text(
                f"🎉 <b>وصل كود التفعيل!</b>\n\n"
                f"📱 الرقم: <code>{format_number(number)}</code>\n"
                f"🔑 الكود: <code>{code}</code>\n\n"
                f"✅ انسخ الكود واستخدمه الآن!",
                parse_mode="HTML",
                reply_markup=main_menu(is_admin))
        else:
            await q.answer("📭 الكود ما وصل بعد، حاول مجدداً.", show_alert=True)

    # ─ تبديل الرقم ─
    elif data.startswith("swap_"):
        number = data.split("_", 1)[1]
        order  = db.get_order_by_activation(number)
        if not order or order[5] in ("done", "cancelled", "expired"):
            await q.answer("⚠️ هذا الطلب منتهي.", show_alert=True); return
        # حرر الرقم القديم
        await api.release_number(number)
        db.update_order(number, "cancelled")
        # جلب رقم جديد بدون خصم إضافي
        await fetch_and_send_number(q, uid, is_admin, deduct=False)

    # ─ إلغاء ─
    elif data.startswith("cancel_"):
        number = data.split("_", 1)[1]
        order  = db.get_order_by_activation(number)
        if order and order[5] not in ("done", "cancelled", "expired"):
            cost = float(order[7]) if order[7] else config.NUMBER_COST
            await api.release_number(number)
            db.update_order(number, "cancelled")
            db.update_balance(uid, cost, note="استرجاع إلغاء", tx_type="refund")
            await q.edit_message_text(
                f"✅ <b>تم الإلغاء!</b>\n"
                f"💰 تم استرجاع <b>{cost:.0f} {config.CURRENCY}</b>\n"
                f"💰 رصيدك الآن: <b>{db.get_balance(uid):.0f} {config.CURRENCY}</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))
        else:
            await q.edit_message_text(
                "⚠️ هذا الطلب منتهي أو ملغي مسبقاً.",
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
            f"💲 رصيد حساب durianrcs: <b>{bal:.0f}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]))

# ══ انتظار الكود تلقائياً ════════════════════════════════
async def wait_for_otp(query, uid, number, mid):
    waited = 0
    while waited < config.SMS_WAIT_SECONDS:
        await asyncio.sleep(config.SMS_POLL_INTERVAL)
        waited += config.SMS_POLL_INTERVAL

        order = db.get_order_by_activation(number)
        if not order or order[5] in ("cancelled", "done", "expired"):
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
                reply_markup=main_menu(uid in config.ADMIN_IDS))
            return

    # انتهى الوقت
    order = db.get_order_by_activation(number)
    if order and order[5] not in ("cancelled", "done"):
        cost = float(order[7]) if order[7] else config.NUMBER_COST
        db.update_order(number, "expired")
        await api.release_number(number)
        db.update_balance(uid, cost, note="استرجاع انتهاء وقت", tx_type="refund")
        await query.message.reply_text(
            f"⏰ <b>انتهى وقت انتظار الكود.</b>\n"
            f"💰 تم استرجاع <b>{cost:.0f} {config.CURRENCY}</b> تلقائياً.\n"
            f"💰 رصيدك الآن: <b>{db.get_balance(uid):.0f} {config.CURRENCY}</b>",
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

    # سجّل المستخدم تلقائياً لو ما موجود
    if not db.get_user(target_id):
        db.register_user(target_id, "", "")

    if action == "add":
        db.update_balance(target_id, +amount, note="شحن من الأدمن", tx_type="deposit")
        new_bal = db.get_balance(target_id)
        await update.message.reply_text(
            f"✅ تم شحن <b>{amount:.0f} {config.CURRENCY}</b> لـ <code>{target_id}</code>\n"
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
        db.update_balance(target_id, -amount, note="خصم من الأدمن", tx_type="deduct")
        await update.message.reply_text(
            f"✅ تم خصم <b>{amount:.0f} {config.CURRENCY}</b> من <code>{target_id}</code>\n"
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
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
