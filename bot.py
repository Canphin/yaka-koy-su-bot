import os
import sqlite3
import asyncio
from datetime import datetime
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============ AYARLAR ============
BOT_TOKEN = os.environ.get('BOT_TOKEN')
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
        okuyan TEXT,
        durum TEXT DEFAULT 'odenmedi'
    )''')
    conn.commit()
    conn.close()
    print("✅ Veritabani hazir!")

# ============ FLASK ============
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Yaka Koyu Su Isletmesi Calisiyor!"

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot_app.bot)
    asyncio.run(bot_app.update_queue.put(update))
    return 'OK'

# ============ TELEGRAM BOT ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💧 YAKA KOYU SU ISLETMESI BOTU\n\n"
        "/oku [no] [endeks] - Sayac okuma gir\n"
        "/abone_ekle - Yeni abone kaydi\n"
        "/abone_sorgu [no] - Abone sorgula\n"
        "/abone_liste - Tum aboneler\n"
        "/rapor - Gunluk rapor"
    )

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
        await update.message.reply_text("❌ Son endeks oncekinden kucuk!")
        conn.close()
        return
    su_bedeli = tuketim * SU_BIRIM_FIYAT
    toplam = su_bedeli + HIZMET_BEDELI
    c.execute(
        "INSERT INTO faturalar (abone_no, onceki_endeks, son_endeks, tuketim_ton, "
        "birim_fiyat, su_bedeli, hizmet_bedeli, toplam_tutar, fatura_tarihi, okuyan) "
        "VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'),?)",
        (abone_no, onceki, son_endeks, tuketim, SU_BIRIM_FIYAT, su_bedeli, HIZMET_BEDELI, toplam, okuyan)
    )
    c.execute("UPDATE aboneler SET onceki_endeks=? WHERE abone_no=?", (son_endeks, abone_no))
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ OKUMA KAYDEDILDI - FATURA KESILDI\n\n"
        f"👤 Abone: #{abone_no} - {abone[1]}\n"
        f"📍 {abone[4]}, {abone[5]} Sk. No:{abone[6]}\n\n"
        f"📊 TUKETIM\nOnceki: {onceki} ton\nSon: {son_endeks} ton\nTuketim: {tuketim} ton\n\n"
        f"💰 FATURA\nSu Bedeli: {su_bedeli} TL\nHizmet: {HIZMET_BEDELI} TL\nTOPLAM: {toplam} TL\n\n"
        f"👷 Okuyan: {okuyan}"
    )

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
        await update.message.reply_text(
            f"✅ ABONE EKLENDI!\n\n"
            f"🔢 No: {abone_no}\n👤 {ad_soyad}\n"
            f"📍 {mahalle}, {sokak} Sk. No:{kapi_no}\n"
            f"🔧 Sayac: {sayac_no}\n🔢 Ilk Endeks: {ilk_endeks} ton"
        )
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
    mesaj = (
        f"📋 ABONE BILGILERI\n\n"
        f"🔢 No: {abone[0]}\n👤 Ad: {abone[1]}\n📞 Tel: {abone[2] or 'Yok'}\n"
        f"📍 {abone[4]}, {abone[5]} Sk. No:{abone[6]}\n"
        f"🔧 Sayac: {abone[7]}\n🔢 Endeks: {abone[8]} ton\n\n📊 SON 3 FATURA:"
    )
    if faturalar:
        for f in faturalar:
            mesaj += f"\n📅 {f[9][:10]} | {f[4]} ton | {f[8]} TL | {f[11]}"
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
        "FROM faturalar WHERE date(fatura_tarihi)=?", (bugun,)
    )
    bugun_oku = c.fetchone()
    c.execute("SELECT COUNT(*) FROM aboneler")
    toplam_abone = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(toplam_tutar),0) FROM faturalar WHERE durum='odenmedi'")
    toplam_borc = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 YAKA KOYU GUNLUK RAPOR - {bugun}\n\n"
        f"📝 Bugunku Okuma: {bugun_oku[0]} adet\n"
        f"💧 Toplam Tuketim: {bugun_oku[1]} ton\n"
        f"💰 Toplam Fatura: {bugun_oku[2]} TL\n"
        f"👥 Toplam Abone: {toplam_abone}\n"
        f"💵 Tahsil Edilmemis: {toplam_borc} TL"
    )

# ============ BASLAT ============
if __name__ == '__main__':
    veritabani_kur()
    
    TOKEN = os.environ.get('BOT_TOKEN', BOT_TOKEN)
    PORT = int(os.environ.get('PORT', 5000))
    
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("oku", oku))
    bot_app.add_handler(CommandHandler("abone_ekle", abone_ekle))
    bot_app.add_handler(CommandHandler("abone_sorgu", abone_sorgu))
    bot_app.add_handler(CommandHandler("abone_liste", abone_liste))
    bot_app.add_handler(CommandHandler("rapor", rapor))
    
    async def baslat():
        await bot_app.initialize()
        await bot_app.start()
    
    asyncio.run(baslat())
    
    print("✅ Bot baslatiliyor...")
    app.run(host='0.0.0.0', port=PORT)
