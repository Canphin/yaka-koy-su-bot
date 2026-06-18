import os
import sqlite3
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, redirect
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

app = Flask(__name__)

# ============ WEB PANEL HTML ============
PANEL_HTML = '''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Yaka Köyü Su İşletmesi</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:system-ui;background:#f0f4f8;padding:10px}
        .header{background:linear-gradient(135deg,#1565C0,#0D47A1);color:white;padding:20px;border-radius:15px;text-align:center;margin-bottom:15px}
        .header h1{font-size:22px}
        .stats{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:15px}
        .stat{background:white;border-radius:12px;padding:15px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.05)}
        .stat h3{color:#666;font-size:11px}
        .stat .val{font-size:24px;font-weight:bold;color:#1565C0}
        .card{background:white;border-radius:12px;padding:15px;margin-bottom:15px;box-shadow:0 2px 8px rgba(0,0,0,0.05)}
        .btn{background:#2196F3;color:white;border:none;padding:8px 15px;border-radius:8px;font-weight:600;margin:3px;cursor:pointer;font-size:13px}
        .btn-success{background:#4CAF50}
        .btn-orange{background:#FF9800}
        .btn-danger{background:#f44336}
        .btn-sm{padding:5px 10px;font-size:11px}
        table{width:100%;border-collapse:collapse;font-size:12px}
        th{background:#2196F3;color:white;padding:8px;text-align:left}
        td{padding:6px 8px;border-bottom:1px solid #eee}
        tr:hover td{background:#f5f9ff}
        input,select{padding:8px;border:2px solid #ddd;border-radius:8px;width:100%;margin:3px 0;font-size:13px}
        input:focus{border-color:#2196F3;outline:none}
        .modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:999;justify-content:center;align-items:center;padding:10px}
        .modal-content{background:white;border-radius:15px;padding:20px;max-width:450px;width:100%;max-height:90vh;overflow-y:auto}
        .badge{display:inline-block;padding:4px 10px;border-radius:15px;font-size:11px}
        .badge-odendi{background:#E8F5E9;color:#2E7D32}
        .badge-odenmedi{background:#FFF3E0;color:#E65100}
        .tab-btn{background:#e0e0e0;color:#333;border:none;padding:10px 15px;cursor:pointer;font-weight:600;font-size:13px}
        .tab-btn.active{background:#2196F3;color:white}
        @media(min-width:768px){body{padding:20px}.container{max-width:1100px;margin:0 auto}.stats{grid-template-columns:repeat(4,1fr)}}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💧 Yaka Köyü Su İşletmesi</h1>
            <p>Abone Yönetim ve Fatura Takip Paneli</p>
        </div>

        <div class="stats" id="istatistikler"></div>

        <div class="card">
            <button class="tab-btn active" onclick="sekmeDegistir('aboneler')">👥 Aboneler</button>
            <button class="tab-btn" onclick="sekmeDegistir('faturalar')">📄 Faturalar</button>
        </div>

        <div id="aboneSekmesi">
            <div class="card">
                <button class="btn btn-success" onclick="modalAc('aboneModal')">➕ Yeni Abone</button>
                <button class="btn" onclick="aboneleriYukle()">🔄 Yenile</button>
            </div>
            <div class="card">
                <input type="text" id="aboneArama" placeholder="🔍 Abone no veya isim ara..." onkeyup="aboneFiltrele()">
            </div>
            <div class="card" style="overflow-x:auto;">
                <table>
                    <thead><tr><th>No</th><th>Ad Soyad</th><th>Mahalle</th><th>Sayaç</th><th>Endeks</th><th>İşlem</th></tr></thead>
                    <tbody id="aboneTablo"></tbody>
                </table>
            </div>
        </div>

        <div id="faturaSekmesi" style="display:none;">
            <div class="card">
                <button class="btn" onclick="faturalariYukle()">🔄 Yenile</button>
                <button class="btn btn-orange" onclick="modalAc('odemeModal')">💳 Toplu Ödeme</button>
            </div>
            <div class="card">
                <input type="text" id="faturaArama" placeholder="🔍 Abone no ara..." onkeyup="faturaFiltrele()">
            </div>
            <div class="card" style="overflow-x:auto;">
                <table>
                    <thead><tr><th>Fatura No</th><th>Abone</th><th>Tüketim</th><th>Tutar</th><th>Tarih</th><th>Durum</th><th>İşlem</th></tr></thead>
                    <tbody id="faturaTablo"></tbody>
                </table>
            </div>
        </div>

        <!-- Abone Modal -->
        <div id="aboneModal" class="modal">
            <div class="modal-content">
                <h2 id="aboneModalBaslik">➕ Yeni Abone</h2>
                <input type="hidden" id="aboneId">
                <input type="text" id="a_no" placeholder="Abone No *">
                <input type="text" id="a_ad" placeholder="Ad Soyad *">
                <input type="text" id="a_mahalle" placeholder="Mahalle *">
                <input type="text" id="a_sokak" placeholder="Sokak">
                <input type="text" id="a_kapi" placeholder="Kapı No">
                <input type="tel" id="a_tel" placeholder="Telefon">
                <input type="text" id="a_sayac" placeholder="Sayaç No">
                <input type="number" id="a_endeks" placeholder="İlk Endeks" value="0" step="0.01">
                <button class="btn btn-success" onclick="aboneKaydet()" style="width:100%;margin-top:10px;">💾 Kaydet</button>
                <button class="btn btn-danger" onclick="modalKapat('aboneModal')" style="width:100%;margin-top:5px;">İptal</button>
            </div>
        </div>

        <!-- Endeks Modal -->
        <div id="endeksModal" class="modal">
            <div class="modal-content">
                <h2>✏️ Endeks Güncelle</h2>
                <p id="endeksBilgi"></p>
                <input type="number" id="e_yeni" placeholder="Yeni endeks değeri" step="0.01">
                <button class="btn btn-success" onclick="endeksGuncelle()" style="width:100%;margin-top:10px;">✅ Güncelle ve Fatura Kes</button>
                <button class="btn btn-danger" onclick="modalKapat('endeksModal')" style="width:100%;margin-top:5px;">İptal</button>
            </div>
        </div>

        <!-- Ödeme Modal -->
        <div id="odemeModal" class="modal">
            <div class="modal-content">
                <h2>💳 Ödeme Yap</h2>
                <select id="odemeAbone"></select>
                <input type="number" id="odemeTutar" placeholder="Ödeme Tutarı (TL)">
                <button class="btn btn-success" onclick="odemeYap()" style="width:100%;margin-top:10px;">✅ Ödeme Yap</button>
                <button class="btn btn-danger" onclick="modalKapat('odemeModal')" style="width:100%;margin-top:5px;">İptal</button>
            </div>
        </div>
    </div>

    <script>
        let tumAboneler=[], tumFaturalar=[], seciliAbone=null;

        function modalAc(id){document.getElementById(id).style.display='flex'}
        function modalKapat(id){document.getElementById(id).style.display='none'}
        window.onclick=function(e){if(e.target.classList.contains('modal'))e.target.style.display='none'}

        function sekmeDegistir(sekme){
            document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('aboneSekmesi').style.display=sekme=='aboneler'?'block':'none';
            document.getElementById('faturaSekmesi').style.display=sekme=='faturalar'?'block':'none';
            if(sekme=='faturalar')faturalariYukle();
        }

        async function aboneleriYukle(){
            const r=await fetch('/api/aboneler');
            tumAboneler=await r.json();
            let h='';
            tumAboneler.forEach(a=>{
                h+=`<tr><td>#${a[0]}</td><td>${a[1]}</td><td>${a[4]}</td><td>${a[7]}</td><td>${a[8]} m³</td>
                <td>
                    <button class="btn btn-sm" onclick="endeksAc('${a[0]}','${a[1]}',${a[8]})">✏️</button>
                    <button class="btn btn-sm btn-orange" onclick="aboneDuzenle('${a[0]}')">📝</button>
                    <button class="btn btn-sm btn-danger" onclick="aboneSil('${a[0]}')">🗑️</button>
                </td></tr>`;
            });
            document.getElementById('aboneTablo').innerHTML=h||'<tr><td colspan="6" style="text-align:center;">Abone yok</td></tr>';
            istatistikleriYukle();
        }

        function aboneFiltrele(){
            const q=document.getElementById('aboneArama').value.toLowerCase();
            const f=tumAboneler.filter(a=>a[0].includes(q)||a[1].toLowerCase().includes(q));
            let h='';
            f.forEach(a=>{
                h+=`<tr><td>#${a[0]}</td><td>${a[1]}</td><td>${a[4]}</td><td>${a[7]}</td><td>${a[8]} m³</td>
                <td><button class="btn btn-sm" onclick="endeksAc('${a[0]}','${a[1]}',${a[8]})">✏️</button></td></tr>`;
            });
            document.getElementById('aboneTablo').innerHTML=h||'<tr><td colspan="6">Yok</td></tr>';
        }

        async function faturalariYukle(){
            const r=await fetch('/api/faturalar');
            tumFaturalar=await r.json();
            faturaTablosuOlustur(tumFaturalar);
        }

        function faturaFiltrele(){
            const q=document.getElementById('faturaArama').value.toLowerCase();
            faturaTablosuOlustur(tumFaturalar.filter(f=>f[1].includes(q)));
        }

        function faturaTablosuOlustur(liste){
            let h='';
            liste.forEach(f=>{
                h+=`<tr><td>#${f[0]}</td><td>#${f[1]}</td><td>${f[4]} m³</td><td>${f[8]} TL</td><td>${f[9]?f[9].substr(0,10):''}</td>
                <td><span class="badge ${f[12]=='odendi'?'badge-odendi':'badge-odenmedi'}">${f[12]}</span></td>
                <td>${f[12]=='odenmedi'?`<button class="btn btn-sm btn-success" onclick="tekOdeme(${f[0]})">💳 Öde</button>`:''}</td></tr>`;
            });
            document.getElementById('faturaTablo').innerHTML=h||'<tr><td colspan="7">Fatura yok</td></tr>';
        }

        async function istatistikleriYukle(){
            const r=await fetch('/api/istatistik');
            const s=await r.json();
            document.getElementById('istatistikler').innerHTML=`
                <div class="stat"><h3>Toplam Abone</h3><div class="val">${s.abone}</div></div>
                <div class="stat"><h3>Bugün Okuma</h3><div class="val">${s.bugun}</div></div>
                <div class="stat"><h3>Toplam Borç</h3><div class="val">${s.borc} ₺</div></div>
                <div class="stat"><h3>Son İşlem</h3><div class="val">${s.son||'-'}</div></div>`;
        }

        function endeksAc(no,ad,endeks){
            seciliAbone=no;
            document.getElementById('endeksBilgi').innerHTML=`<strong>#${no} - ${ad}</strong><br>Mevcut: ${endeks} m³`;
            document.getElementById('e_yeni').value='';
            modalAc('endeksModal');
        }

        async function endeksGuncelle(){
            const y=document.getElementById('e_yeni').value;
            if(!y)return;
            const r=await fetch('/api/endeks-guncelle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({abone_no:seciliAbone,son_endeks:parseFloat(y)})});
            const s=await r.json();
            if(s.basarili){alert(`✅ Fatura Kesildi!\nTüketim: ${s.tuketim} ton\nToplam: ${s.toplam} TL`);modalKapat('endeksModal');aboneleriYukle()}
            else alert('❌ '+s.hata);
        }

        function aboneDuzenle(no){
            const a=tumAboneler.find(x=>x[0]==no);
            if(!a)return;
            document.getElementById('aboneModalBaslik').textContent='📝 Abone Düzenle';
            document.getElementById('aboneId').value=no;
            document.getElementById('a_no').value=a[0];document.getElementById('a_no').disabled=true;
            document.getElementById('a_ad').value=a[1];document.getElementById('a_mahalle').value=a[4];
            document.getElementById('a_sokak').value=a[5]||'';document.getElementById('a_kapi').value=a[6]||'';
            document.getElementById('a_tel').value=a[2]||'';document.getElementById('a_sayac').value=a[7];
            document.getElementById('a_endeks').value=a[8];document.getElementById('a_endeks').disabled=true;
            modalAc('aboneModal');
        }

        async function aboneKaydet(){
            const id=document.getElementById('aboneId').value;
            const d={abone_no:document.getElementById('a_no').value,ad_soyad:document.getElementById('a_ad').value,
                mahalle:document.getElementById('a_mahalle').value,sokak:document.getElementById('a_sokak').value,
                kapi_no:document.getElementById('a_kapi').value,telefon:document.getElementById('a_tel').value,
                sayac_no:document.getElementById('a_sayac').value,ilk_endeks:parseFloat(document.getElementById('a_endeks').value)||0};
            if(!d.abone_no||!d.ad_soyad||!d.mahalle)return alert('Abone No, Ad Soyad ve Mahalle zorunlu!');
            const url=id?'/api/abone-guncelle':'/api/abone-ekle';
            const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
            const s=await r.json();
            if(s.basarili){alert('✅ '+s.mesaj);modalKapat('aboneModal');aboneleriYukle();document.getElementById('aboneId').value='';
                document.getElementById('a_no').disabled=false;document.getElementById('a_endeks').disabled=false;
                document.getElementById('aboneModalBaslik').textContent='➕ Yeni Abone';}
            else alert('❌ '+s.hata);
        }

        async function aboneSil(no){
            if(!confirm(`#${no} silinsin mi?`))return;
            const r=await fetch(`/api/abone-sil/${no}`,{method:'DELETE'});
            const s=await r.json();
            alert(s.basarili?'✅ Silindi':'❌ '+s.hata);
            aboneleriYukle();
        }

        async function tekOdeme(faturaNo){
            const r=await fetch(`/api/odeme/${faturaNo}`,{method:'POST'});
            const s=await r.json();
            alert(s.basarili?'✅ Ödendi':'❌ Hata');
            faturalariYukle();
        }

        async function odemeYap(){
            const abone=document.getElementById('odemeAbone').value;
            const tutar=document.getElementById('odemeTutar').value;
            if(!abone||!tutar)return;
            const r=await fetch('/api/toplu-odeme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({abone_no:abone,tutar:parseFloat(tutar)})});
            const s=await r.json();
            alert(s.basarili?`✅ ${s.odenen} fatura ödendi!`:'❌ Hata');
            modalKapat('odemeModal');faturalariYukle();
        }

        aboneleriYukle();
    </script>
</body>
</html>
'''

# ============ WEB ROUTES ============
@app.route('/')
def panel():
    return PANEL_HTML

@app.route('/api/aboneler')
def api_aboneler():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM aboneler ORDER BY abone_no")
    data = c.fetchall()
    conn.close()
    return jsonify(data)

@app.route('/api/faturalar')
def api_faturalar():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM faturalar ORDER BY fatura_tarihi DESC LIMIT 100")
    data = c.fetchall()
    conn.close()
    return jsonify(data)

@app.route('/api/istatistik')
def api_istatistik():
    bugun = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aboneler")
    abone = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM faturalar WHERE date(fatura_tarihi)=?", (bugun,))
    bugun_oku = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(toplam_tutar),0) FROM faturalar WHERE durum='odenmedi'")
    borc = c.fetchone()[0]
    c.execute("SELECT fatura_tarihi FROM faturalar ORDER BY fatura_tarihi DESC LIMIT 1")
    son = c.fetchone()
    conn.close()
    return jsonify({'abone':abone,'bugun':bugun_oku,'borc':borc,'son':son[0][:16] if son else '-'})

@app.route('/api/endeks-guncelle', methods=['POST'])
def api_endeks_guncelle():
    data = request.get_json()
    abone_no, son_endeks = data['abone_no'], float(data['son_endeks'])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT onceki_endeks FROM aboneler WHERE abone_no=?", (abone_no,))
    abone = c.fetchone()
    if not abone:
        conn.close()
        return jsonify({'basarili':False,'hata':'Abone bulunamadi!'})
    onceki = abone[0]
    tuketim = son_endeks - onceki
    if tuketim < 0:
        conn.close()
        return jsonify({'basarili':False,'hata':'Endeks küçük!'})
    toplam = tuketim * SU_BIRIM_FIYAT + HIZMET_BEDELI
    c.execute("INSERT INTO faturalar (abone_no,onceki_endeks,son_endeks,tuketim_ton,birim_fiyat,su_bedeli,hizmet_bedeli,toplam_tutar,fatura_tarihi) VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'))",
              (abone_no,onceki,son_endeks,tuketim,SU_BIRIM_FIYAT,tuketim*SU_BIRIM_FIYAT,HIZMET_BEDELI,toplam))
    c.execute("UPDATE aboneler SET onceki_endeks=? WHERE abone_no=?", (son_endeks,abone_no))
    conn.commit()
    conn.close()
    return jsonify({'basarili':True,'tuketim':tuketim,'toplam':toplam})

@app.route('/api/abone-ekle', methods=['POST'])
def api_abone_ekle():
    data = request.get_json()
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO aboneler (abone_no,ad_soyad,telefon,mahalle,sokak,kapi_no,sayac_no,onceki_endeks) VALUES (?,?,?,?,?,?,?,?)",
                  (data['abone_no'],data['ad_soyad'],data.get('telefon',''),data['mahalle'],data.get('sokak',''),data.get('kapi_no',''),data.get('sayac_no',f"SU-{data['abone_no']}"),data.get('ilk_endeks',0)))
        conn.commit()
        conn.close()
        return jsonify({'basarili':True,'mesaj':'Abone eklendi!'})
    except Exception as e:
        return jsonify({'basarili':False,'hata':str(e)})

@app.route('/api/abone-guncelle', methods=['POST'])
def api_abone_guncelle():
    data = request.get_json()
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE aboneler SET ad_soyad=?,telefon=?,mahalle=?,sokak=?,kapi_no=?,sayac_no=? WHERE abone_no=?",
                  (data['ad_soyad'],data.get('telefon',''),data['mahalle'],data.get('sokak',''),data.get('kapi_no',''),data.get('sayac_no',''),data['abone_no']))
        conn.commit()
        conn.close()
        return jsonify({'basarili':True,'mesaj':'Güncellendi!'})
    except Exception as e:
        return jsonify({'basarili':False,'hata':str(e)})

@app.route('/api/abone-sil/<abone_no>', methods=['DELETE'])
def api_abone_sil(abone_no):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM faturalar WHERE abone_no=?", (abone_no,))
        c.execute("DELETE FROM aboneler WHERE abone_no=?", (abone_no,))
        conn.commit()
        conn.close()
        return jsonify({'basarili':True})
    except Exception as e:
        return jsonify({'basarili':False,'hata':str(e)})

@app.route('/api/odeme/<int:fatura_no>', methods=['POST'])
def api_odeme(fatura_no):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE faturalar SET durum='odendi' WHERE fatura_no=?", (fatura_no,))
        conn.commit()
        conn.close()
        return jsonify({'basarili':True})
    except Exception as e:
        return jsonify({'basarili':False})

@app.route('/api/toplu-odeme', methods=['POST'])
def api_toplu_odeme():
    data = request.get_json()
    abone_no, tutar = data['abone_no'], data['tutar']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT fatura_no,toplam_tutar FROM faturalar WHERE abone_no=? AND durum='odenmedi' ORDER BY fatura_tarihi", (abone_no,))
    faturalar = c.fetchall()
    odenen = 0
    kalan = tutar
    for f in faturalar:
        if kalan >= f[1]:
            c.execute("UPDATE faturalar SET durum='odendi' WHERE fatura_no=?", (f[0],))
            kalan -= f[1]
            odenen += 1
    conn.commit()
    conn.close()
    return jsonify({'basarili':True,'odenen':odenen})

# ============ TELEGRAM BOT ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💧 YAKA KOYU SU ISLETMESI BOTU\n\n/oku [no] [endeks]\n/abone_ekle\n/abone_sorgu [no]\n/abone_liste\n/rapor\n/panel")

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🌐 Web Panel: https://yaka-koy-su-bot.onrender.com")

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
        await update.message.reply_text("❌ Abone bulunamadi!")
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
        m += f"\n📅 {f[9][:10]} | {f[4]} ton | {f[8]} TL | {f[12]}"
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
    c.execute("SELECT COUNT(*), COALESCE(SUM(toplam_tutar),0) FROM aboneler LEFT JOIN faturalar ON aboneler.abone_no=faturalar.abone_no AND faturalar.durum='odenmedi'")
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
    bot_app.add_handler(CommandHandler("panel", panel))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT), daemon=True).start()
    print("✅ Panel: https://yaka-koy-su-bot.onrender.com")
    print("✅ Bot polling modunda baslatiliyor...")
    bot_app.run_polling()
