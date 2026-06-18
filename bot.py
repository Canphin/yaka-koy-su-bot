import sqlite3
import os
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============ AYARLAR ============
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8708118556:AAEs0m4BbhX7Tv22w_hcvIBCXXsBldqC5U0')
SU_BIRIM_FIYAT = 30
HIZMET_BEDELI = 20
DB_PATH = '/tmp/su_abone.db'

# ============ VERITABANI ============
def veritabani_kur():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS aboneler (
        abone_no TEXT PRIMARY KEY,
        ad_soyad TEXT NOT NULL,
        telefon TEXT,
        telegram_id TEXT,
        mahalle TEXT NOT NULL,
        sokak TEXT,
        kapi_no TEXT,
        sayac_no TEXT UNIQUE,
        onceki_endeks REAL DEFAULT 0,
        kayit_tarihi TEXT DEFAULT (datetime('now','localtime'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS faturalar (
        fatura_no INTEGER PRIMARY KEY AUTOINCREMENT,
        abone_no TEXT NOT NULL,
        onceki_endeks REAL NOT NULL,
        son_endeks REAL NOT NULL,
        tuketim_ton REAL NOT NULL,
        birim_fiyat REAL NOT NULL,
        su_bedeli REAL NOT NULL,
        hizmet_bedeli REAL NOT NULL,
        toplam_tutar REAL NOT NULL,
        fatura_tarihi TEXT DEFAULT (datetime('now','localtime')),
        son_odeme_tarihi TEXT,
        okuyan TEXT,
        durum TEXT DEFAULT 'odenmedi'
    )''')
    conn.commit()
    conn.close()
    print("✅ Veritabani hazir!")

# ============ FLASK UYGULAMASI ============
web_app = Flask(__name__)

@web_app.route('/')
def ana_sayfa():
    return """
    <html><head><title>Yaka Koyu Su Isletmesi</title>
    <meta charset='UTF-8'>
    <style>body{font-family:Arial;text-align:center;padding:50px;background:#f0f4f8}
    h1{color:#1565C0}span{font-size:50px}</style></head>
    <body><span>💧</span><h1>Yaka Koyu Su Isletmesi</h1>
    <p>✅ Sistem Aktif</p><p>Telegram botunu kullanin</p></body></html>"""

@web_app.route('/webhook', methods=['POST'])
def webhook():
    if bot_app:
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        bot_app.update_queue.put_nowait(update)
        return 'OK'
    return 'Bot baslatilmadi', 500

# ============ TELEGRAM BOT ============
bot_app = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""💧 YAKA KOYU SU ISLETMESI BOTU

📋 Komutlar:
/oku [no] [endeks] - Sayac okuma gir
/abone_ekle - Yeni abone kaydi
/abone_sorgu [no] - Abone sorgula
/abone_liste - Tum aboneler
/rapor - Gunluk rapor""")

async def oku(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Kullanim: /oku [abone_no] [son_endeks]\nOrnek: /oku 42 75")
        return
    
    abone_no = args[0]
    son_endeks = float(args[1])
    okuyan = update.effective_user.full_name
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM aboneler WHERE abone_no=?", (abone_no,))
    abone = c.fetchone()
    
    if not abone:
        await update.message.reply_text(f"❌ {abone_no} nolu abone bulunamadi!")
        conn.close()
        return
    
    onceki = abone[8]
    tuketim = son_endeks - onceki
    
    if tuketim < 0:
        await update.message.reply_text(f"❌ Son endeks ({son_endeks}) oncekinden ({onceki}) kucuk!")
        conn.close()
        return
    
    su_bedeli = tuketim * SU_BIRIM_FIYAT
    toplam = su_bedeli + HIZMET_BEDELI
    
    c.execute("""INSERT INTO faturalar 
        (abone_no, onceki_endeks, son_endeks, tuketim_ton, 
         birim_fiyat, su_bedeli, hizmet_bedeli, toplam_tutar, 
         fatura_tarihi, okuyan)
        VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'),?)""",
        (abone_no, onceki, son_endeks, tuketim, SU_BIRIM_FIYAT, su_bedeli, HIZMET_BEDELI, toplam, okuyan))
    
    c.execute("UPDATE aboneler SET onceki_endeks=? WHERE abone_no=?", (son_endeks, abone_no))
    conn.commit()
    conn.close()
    
    mesaj = f"""✅ OKUMA KAYDEDILDI - FATURA KESILDI

👤 Abone: #{abone_no} - {abone[1]}
📍 {abone[4]}, {abone[5]} Sk. No:{abone[6]}

📊 TUKETIM
Onceki: {onceki} ton
Son: {son_endeks} ton
Tuketim: {tuketim} ton

💰 FATURA
Su Bedeli: {su_bedeli} TL
Hizmet: {HIZMET_BEDELI} TL
TOPLAM: {toplam} TL

👷 Okuyan: {okuyan}"""
    await update.message.reply_text(mesaj)
    
    if abone[3]:
        try:
            await context.bot.send_message(
                chat_id=abone[3],
                text=f"💧 Yaka Koyu Su Isletmesi\nFaturaniz kesildi!\nToplam: {toplam} TL\nTuketim: {tuketim} ton"
            )
        except:
            pass

async def abone_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Kullanim: /abone_ekle [no] [ad_soyad] [mahalle] [sokak] [kapi_no] [tel] [sayac_no] [ilk_endeks]\n\n"
            "Ornek: /abone_ekle 42 Ahmet_Yilmaz Yukari_Mahalle Cinari_Sk 5 05320001122 SU-0042 20\n\n"
            "Bosluk yerine _ kullanin!"
        )
        return
    
    try:
        abone_no = args[0]
        ad_soyad = args[1].replace('_', ' ')
        mahalle = args[2].replace('_', ' ')
        sokak = args[3].replace('_', ' ') if len(args) > 3 else ""
        kapi_no = args[4] if len(args) > 4 else ""
        telefon = args[5] if len(args) > 5 else ""
        sayac_no = args[6] if len(args) > 6 else f"SU-{abone_no}"
        ilk_endeks = float(args[7]) if len(args) > 7 else 0
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO aboneler (abone_no, ad_soyad, telefon, mahalle, sokak, kapi_no, sayac_no, onceki_endeks) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (abone_no, ad_soyad, telefon, mahalle, sokak, kapi_no, sayac_no, ilk_endeks)
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"""✅ ABONE EKLENDI!

🔢 No: {abone_no}
👤 {ad_soyad}
📍 {mahalle}, {sokak} Sk. No:{kapi_no}
🔧 Sayac: {sayac_no}
🔢 Ilk Endeks: {ilk_endeks} ton""")
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {str(e)}")

async def abone_sorgu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Kullanim: /abone_sorgu [abone_no]")
        return
    
    abone_no = context.args[0]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM aboneler WHERE abone_no=?", (abone_no,))
    abone = c.fetchone()
    
    if not abone:
        await update.message.reply_text("❌ Abone bulunamadi!")
        conn.close()
        return
    
    c.execute("SELECT * FROM faturalar WHERE abone_no=? ORDER BY fatura_tarihi DESC LIMIT 3", (abone_no,))
    faturalar = c.fetchall()
    conn.close()
    
    mesaj = f"""📋 ABONE BILGILERI

🔢 No: {abone[0]}
👤 Ad: {abone[1]}
📞 Tel: {abone[2] or 'Yok'}
📍 {abone[4]}, {abone[5]} Sk. No:{abone[6]}
🔧 Sayac: {abone[7]}
🔢 Endeks: {abone[8]} ton

📊 SON 3 FATURA:"""
    
    if faturalar:
        for f in faturalar:
            mesaj += f"\n📅 {f[9][:10]} | {f[4]} ton | {f[8]} TL | {f[12]}"
    else:
        mesaj += "\nHenuz fatura yok."
    
    await update.message.reply_text(mesaj)

async def abone_liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aboneler")
    toplam = c.fetchone()[0]
    c.execute("SELECT abone_no, ad_soyad, mahalle, onceki_endeks FROM aboneler ORDER BY abone_no LIMIT 50")
    aboneler = c.fetchall()
    conn.close()
    
    mesaj = f"📋 YAKA KOYU ABONE LISTESI (Toplam: {toplam})\n\n"
    for a in aboneler:
        mesaj += f"#{a[0]} | {a[1]} | {a[2]} | {a[3]} ton\n"
    if toplam > 50:
        mesaj += f"\n... ve {toplam - 50} abone daha."
    
    await update.message.reply_text(mesaj)

async def rapor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bugun = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*), COALESCE(SUM(tuketim_ton),0), COALESCE(SUM(toplam_tutar),0) "
        "FROM faturalar WHERE date(fatura_tarihi)=?",
        (bugun,)
    )
    bugun_oku = c.fetchone()
    c.execute("SELECT COUNT(*) FROM aboneler")
    toplam_abone = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(toplam_tutar),0) FROM faturalar WHERE durum='odenmedi'")
    toplam_borc = c.fetchone()[0]
    conn.close()
    
    await update.message.reply_text(f"""📊 YAKA KOYU GUNLUK RAPOR - {bugun}

📝 Bugunku Okuma: {bugun_oku[0]} adet
💧 Toplam Tuketim: {bugun_oku[1]} ton
💰 Toplam Fatura: {bugun_oku[2]} TL
👥 Toplam Abone: {toplam_abone}
💵 Tahsil Edilmemis: {toplam_borc} TL""")

# ============ BASLAT ============
if __name__ == '__main__':
    veritabani_kur()
    
    # Bot token'ini al
    TOKEN = os.environ.get('BOT_TOKEN', BOT_TOKEN)
    
    # Bot uygulamasini olustur
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("oku", oku))
    bot_app.add_handler(CommandHandler("abone_ekle", abone_ekle))
    bot_app.add_handler(CommandHandler("abone_sorgu", abone_sorgu))
    bot_app.add_handler(CommandHandler("abone_liste", abone_liste))
    bot_app.add_handler(CommandHandler("rapor", rapor))
    
    # Render'da webhook, lokal'de polling
    RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
    PORT = int(os.environ.get('PORT', 5000))
    
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/webhook"
        print(f"✅ Webhook ayarlaniyor: {webhook_url}")
        bot_app.run_webhook(
            listen='0.0.0.0',
            port=PORT,
            webhook_url=webhook_url
        )
    else:
        print("✅ Polling modunda calisiyor...")
        bot_app.run_polling()
    
    print(f"✅ Yaka Koyu Su Isletmesi calisiyor! Port: {PORT}")
    web_app.run(host='0.0.0.0', port=PORT)