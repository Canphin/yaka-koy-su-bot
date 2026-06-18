import os
import sqlite3
import threading
from datetime import datetime
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.environ.get('BOT_TOKEN')
SU_BIRIM_FIYAT = 30
HIZMET_BEDELI = 20
DB_PATH = '/tmp/su_abone.db'

def veritabani_kur():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS aboneler (
        abone_no TEXT PRIMARY KEY, ad_soyad TEXT NOT NULL, telefon TEXT,
        telegram_id TEXT, mahalle TEXT NOT NULL, sokak TEXT,
        kapi_no TEXT, sayac_no TEXT UNIQUE, onceki_endeks REAL DEFAULT 0,
        kayit_tarihi TEXT DEFAULT (datetime('now','localtime')))''')
    c.execute('''CREATE TABLE IF NOT EXISTS faturalar (
        fatura_no INTEGER PRIMARY KEY AUTOINCREMENT, abone_no TEXT NOT NULL,
        onceki_endeks REAL NOT NULL, son_endeks REAL NOT NULL,
        tuketim_ton REAL NOT NULL, birim_fiyat REAL NOT NULL,
        su_bedeli REAL NOT NULL, hizmet_bedeli REAL NOT NULL,
        toplam_tutar REAL NOT NULL,
        fatura_tarihi TEXT DEFAULT (datetime('now','localtime')),
        okuyan TEXT, durum TEXT DEFAULT 'odenmedi')''')
    conn.commit()
    conn.close()
    print("✅ VT hazir")

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Calisiyor!"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💧 YAKA KOYU SU ISLETMESI BOTU\n\n/oku [no] [endeks]\n/abone_ekle\n/abone_sorgu [no]\n/abone_liste\n/rapor")

async def oku(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("/oku [abone_no] [son_endeks]")
        return
    abone_no, son_endeks = args[0], float(args[1])
    okuyan = update.effective_user.full_name
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM aboneler WHERE abone_no=?", (abone_no,))
    abone = c.fetchone()
    if not abone:
        await update.message.reply_text(f"❌ Abone bulunamadi!")
        conn.close()
        return
    onceki, tuketim = abone[8], son_endeks - abone[8]
    if tuketim < 0:
        await update.message.reply_text("❌ Hata!")
        conn.close()
        return
    toplam = tuketim * SU_BIRIM_FIYAT + HIZMET_BEDELI
    c.execute("INSERT INTO faturalar (abone_no,onceki_endeks,son_endeks,tuketim_ton,birim_fiyat,su_bedeli,hizmet_bedeli,toplam_tutar,fatura_tarihi,okuyan) VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'),?)",
              (abone_no,onceki,son_endeks,tuketim,SU_BIRIM_FIYAT,tuketim*SU_BIRIM_FIYAT,HIZMET_BEDELI,toplam,okuyan))
    c.execute("UPDATE aboneler SET onceki_endeks=? WHERE abone_no=?", (son_endeks,abone_no))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ FATURA KESILDI\n👤 #{abone_no} {abone[1]}\n💧 {tuketim} ton\n💰 {toplam} TL")

async def abone_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("/abone_ekle [no] [ad_soyad] [mahalle] [sokak] [kapi_no] [tel] [sayac_no] [ilk_endeks]")
        return
    try:
        abone_no, ad_soyad, mahalle = args[0], args[1].replace('_',' '), args[2].replace('_',' ')
        sokak = args[3].replace('_',' ') if len(args)>3 else ""
        kapi_no, telefon = args[4] if len(args)>4 else "", args[5] if len(args)>5 else ""
        sayac_no = args[6] if len(args)>6 else f"SU-{abone_no}"
        ilk_endeks = float(args[7]) if len(args)>7 else 0
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO aboneler VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                  (abone_no,ad_soyad,telefon,None,mahalle,sokak,kapi_no,sayac_no,ilk_endeks))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ ABONE EKLENDI! #{abone_no} {ad_soyad}")
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")

async def abone_sorgu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("/abone_sorgu [abone_no]")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM aboneler WHERE abone_no=?", (context.args[0],))
    abone = c.fetchone()
    if not abone:
        await update.message.reply_text("❌ Yok!")
        conn.close()
        return
    c.execute("SELECT * FROM faturalar WHERE abone_no=? ORDER BY fatura_tarihi DESC LIMIT 3", (context.args[0],))
    faturalar = c.fetchall()
    conn.close()
    m = f"📋 #{abone[0]} {abone[1]}\n📍 {abone[4]}\n🔢 {abone[8]} ton\n"
    for f in faturalar:
        m += f"\n📅 {f[9][:10]} | {f[4]} ton | {f[8]} TL"
    await update.message.reply_text(m)

async def abone_liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aboneler")
    t = c.fetchone()[0]
    c.execute("SELECT abone_no, ad_soyad, mahalle, onceki_endeks FROM aboneler LIMIT 50")
    aboneler = c.fetchall()
    conn.close()
    m = f"📋 TOPLAM: {t}\n\n"
    for a in aboneler:
        m += f"#{a[0]} {a[1]} | {a[2]} | {a[3]} ton\n"
    await update.message.reply_text(m)

async def rapor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bugun = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(tuketim_ton),0), COALESCE(SUM(toplam_tutar),0) FROM faturalar WHERE date(fatura_tarihi)=?", (bugun,))
    o = c.fetchone()
    c.execute("SELECT COUNT(*), COALESCE(SUM(toplam_tutar),0) FROM (SELECT COUNT(*) FROM aboneler UNION ALL SELECT COALESCE(SUM(toplam_tutar),0) FROM faturalar WHERE durum='odenmedi')")
    conn.close()
    await update.message.reply_text(f"📊 {bugun}\n📝 {o[0]} okuma\n💧 {o[1]} ton\n💰 {o[2]} TL")

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
    threading.Thread(target=bot_app.run_polling, daemon=True).start()
    print("✅ Bot basladi!")
    app.run(host='0.0.0.0', port=PORT)
