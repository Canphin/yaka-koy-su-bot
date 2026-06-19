import os
import sqlite3
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============ AYARLAR ============
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
SU_BIRIM_FIYAT = int(os.environ.get('SU_FIYAT', '30'))
HIZMET_BEDELI = int(os.environ.get('HIZMET_BEDEL', '20'))
FAIZ_ORANI = int(os.environ.get('FAIZ_ORANI', '5'))
ODEME_SURESI = int(os.environ.get('ODEME_SURESI', '30'))
DB_PATH = '/tmp/su_abone.db'

YETKILI_TELEGRAM_ID = os.environ.get('YETKILI_ID', '').split(',')
WEB_PANEL_SIFRE = os.environ.get('WEB_SIFRE', '')

def yetkili_mi(update: Update):
    return str(update.effective_user.id) in YETKILI_TELEGRAM_ID

def api_yetkili(request):
    return request.args.get('sifre') == WEB_PANEL_SIFRE

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
        toplam_tutar REAL NOT NULL, faiz_tutari REAL DEFAULT 0,
        fatura_tarihi TEXT DEFAULT (datetime('now','localtime')),
        son_odeme_tarihi TEXT, okuyan TEXT,
        durum TEXT DEFAULT 'odenmedi', silindi INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

app = Flask(__name__)

# ============ SİYAH-SARI TEMALI WEB PANEL ============
PANEL_HTML = '''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Yaka Koyu Su Isletmesi</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{background:#0a0a0a;font-family:'Inter',-apple-system,sans-serif;padding:20px;color:#e0e0e0;font-size:13px}
        .container-fluid{max-width:1400px;margin:0 auto}
        h1{color:#ffc107;font-weight:500;border-left:3px solid #ffc107;padding-left:15px;margin-bottom:20px;font-size:24px}
        .card{background:#141414;border:1px solid #2a2a2a;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.3);margin-bottom:16px}
        .card-header{background:#0f0f0f!important;color:#ffc107!important;font-weight:500;border-bottom:1px solid #2a2a2a;padding:12px 16px!important;font-size:14px!important}
        .card-body{background:#141414;padding:16px!important}
        .form-control,.form-select{background:#2a2a2a;border:1px solid #555;color:#fff;border-radius:6px;padding:8px 12px!important;font-size:13px!important}
        .form-control:focus,.form-select:focus{border-color:#ffc107;box-shadow:0 0 0 0.1rem rgba(255,193,7,0.2)}
        label{font-size:12px!important;font-weight:500;margin-bottom:4px;color:#ffc107}
        .btn{border-radius:6px;font-weight:500;padding:8px 16px!important;font-size:12px!important}
        .btn-warning{background:#ffc107;border-color:#ffc107;color:#000}
        .btn-warning:hover{background:#ffcd39;color:#000}
        .btn-info{background:#1e1e1e;border-color:#ffc107;color:#ffc107}
        .btn-success{background:#0f0f0f;border-color:#ffc107;color:#ffc107}
        .btn-danger{background:#dc3545;border-color:#dc3545;color:#fff}
        .btn-sm{padding:4px 8px!important;font-size:11px!important}
        table{color:#e0e0e0;font-size:12px!important;min-width:800px}
        thead th{background:#0f0f0f;color:#ffc107;border-bottom:1px solid #2a2a2a;padding:10px 8px!important;font-size:12px!important;white-space:nowrap}
        tbody td{padding:8px!important;vertical-align:middle;white-space:nowrap;border-bottom:1px solid #1e1e1e}
        .stats-container{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}
        .stat-card{flex:1;min-width:200px;background:#141414;border:1px solid #2a2a2a;border-radius:12px;padding:16px;display:flex;align-items:center;gap:16px;transition:all 0.2s ease;cursor:pointer}
        .stat-card:hover{border-color:#ffc107;box-shadow:0 4px 15px rgba(255,193,7,0.1)}
        .stat-icon{width:48px;height:48px;background:#1e1e1e;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:20px;color:#ffc107;border:1px solid #333;flex-shrink:0}
        .stat-label{font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px}
        .stat-value{font-size:24px;font-weight:600;color:#ffc107}
        .stat-desc{font-size:11px;color:#666}
        .badge-odendi{background:#0f3320;color:#28a745;padding:4px 10px;border-radius:10px;font-size:11px}
        .badge-odenmedi{background:#332200;color:#ffc107;padding:4px 10px;border-radius:10px;font-size:11px}
        .badge-faizli{background:#330a0a;color:#dc3545;padding:4px 10px;border-radius:10px;font-size:11px}
        .modal-content{background:#1e1e1e;border:1px solid #444;border-radius:12px}
        .modal-header{background:#181818;border-bottom:1px solid #444;color:#ffc107}
        .modal-body{background:#1e1e1e}
        .modal-footer{background:#1e1e1e;border-top:1px solid #2a2a2a}
        .btn-close{filter:invert(1)}
        ::-webkit-scrollbar{width:6px;height:6px}
        ::-webkit-scrollbar-track{background:#1a1a1a}
        ::-webkit-scrollbar-thumb{background:#3a3a3a;border-radius:3px}
        tr.gecikme{background:rgba(220,53,69,0.08)!important}
        @media(max-width:768px){body{padding:8px}h1{font-size:17px}.stats-container{flex-direction:column;gap:8px}.stat-card{min-width:auto;padding:12px}.stat-value{font-size:20px}.table{font-size:11px!important;min-width:560px}}
    </style>
</head>
<body>
    <div class="container-fluid">
        <h1><i class="fas fa-tint"></i> YAKA KOYU SU ISLETMESI</h1>

        <!-- Istatistik Kartlari -->
        <div class="stats-container">
            <div class="stat-card" onclick="sekmeDegistir('aboneler')">
                <div class="stat-icon"><i class="fas fa-users"></i></div>
                <div class="stat-content">
                    <div class="stat-label">TOPLAM ABONE</div>
                    <div class="stat-value" id="toplamAbone">0</div>
                    <div class="stat-desc">goruntulemek icin tikla</div>
                </div>
            </div>
            <div class="stat-card" onclick="sekmeDegistir('faturalar')">
                <div class="stat-icon" style="border-color:#dc3545;"><i class="fas fa-clock" style="color:#dc3545;"></i></div>
                <div class="stat-content">
                    <div class="stat-label">ODENMEMIS</div>
                    <div class="stat-value" id="odenecekToplam">0 TL</div>
                    <div class="stat-desc">goruntulemek icin tikla</div>
                </div>
            </div>
            <div class="stat-card" onclick="sekmeDegistir('faturalar')">
                <div class="stat-icon"><i class="fas fa-coins"></i></div>
                <div class="stat-content">
                    <div class="stat-label">FAIZLI BORC</div>
                    <div class="stat-value" id="faizliBorc">0 TL</div>
                    <div class="stat-desc">30 gun gecikmis</div>
                </div>
            </div>
            <div class="stat-card" onclick="faturalariYukle()">
                <div class="stat-icon" style="border-color:#28a745;"><i class="fas fa-check-circle" style="color:#28a745;"></i></div>
                <div class="stat-content">
                    <div class="stat-label">BUGUN OKUMA</div>
                    <div class="stat-value" id="bugunOkuma">0</div>
                    <div class="stat-desc">yenilemek icin tikla</div>
                </div>
            </div>
        </div>

        <!-- Sekmeler -->
        <div class="card mb-3">
            <div class="card-body">
                <button class="btn btn-warning me-2" onclick="sekmeDegistir('aboneler')">👥 ABONELER</button>
                <button class="btn btn-info me-2" onclick="sekmeDegistir('faturalar')">📄 FATURALAR</button>
                <button class="btn btn-success me-2" onclick="modalAc('aboneModal')">➕ YENI ABONE</button>
                <button class="btn btn-warning me-2" onclick="modalAc('okumaModal')">📊 OKUMA GIRIS</button>
                <button class="btn btn-danger me-2" onclick="faizIslet()">📈 FAIZ ISLET</button>
                <button class="btn btn-info" onclick="tumVerileriYenile()">🔄 YENILE</button>
            </div>
        </div>

        <!-- Abone Sekmesi -->
        <div id="aboneSekmesi">
            <div class="card">
                <div class="card-header"><i class="fas fa-users"></i> ABONELER</div>
                <div class="card-body p-0"><div class="table-responsive"><table><thead><tr><th>No</th><th>Ad Soyad</th><th>Telefon</th><th>Mahalle</th><th>Sokak</th><th>Sayac</th><th>Endeks</th><th>Islem</th></tr></thead><tbody id="aboneTablo"></tbody></table></div></div>
            </div>
        </div>

        <!-- Fatura Sekmesi -->
        <div id="faturaSekmesi" style="display:none;">
            <div class="card">
                <div class="card-header"><i class="fas fa-file-invoice"></i> FATURALAR</div>
                <div class="card-body p-0"><div class="table-responsive"><table><thead><tr><th>Fatura No</th><th>Abone</th><th>Tarih</th><th>Tuketim</th><th>Tutar</th><th>Faiz</th><th>Son Odeme</th><th>Durum</th><th>Islem</th></tr></thead><tbody id="faturaTablo"></tbody></table></div></div>
            </div>
        </div>
    </div>

    <!-- Abone Modal -->
    <div class="modal fade" id="aboneModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
        <div class="modal-header"><h5 class="modal-title">➕ YENI ABONE</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
        <div class="modal-body">
            <input type="hidden" id="aboneId">
            <label>Abone No *</label><input type="text" id="a_no" class="form-control mb-2">
            <label>Ad Soyad *</label><input type="text" id="a_ad" class="form-control mb-2">
            <label>Telefon</label><input type="tel" id="a_tel" class="form-control mb-2">
            <label>Mahalle *</label><input type="text" id="a_mahalle" class="form-control mb-2">
            <label>Sokak</label><input type="text" id="a_sokak" class="form-control mb-2">
            <label>Kapi No</label><input type="text" id="a_kapi" class="form-control mb-2">
            <label>Sayac No</label><input type="text" id="a_sayac" class="form-control mb-2">
            <label>Ilk Endeks</label><input type="number" id="a_endeks" class="form-control mb-2" value="0" step="0.01">
        </div>
        <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">IPTAL</button><button class="btn btn-warning" onclick="aboneKaydet()">KAYDET</button></div>
    </div></div></div>

    <!-- Okuma Modal -->
    <div class="modal fade" id="okumaModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
        <div class="modal-header"><h5 class="modal-title">📊 OKUMA GIRISI</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
        <div class="modal-body">
            <label>Abone</label><select id="okumaAbone" class="form-select mb-2"></select>
            <label>Son Endeks</label><input type="number" id="sonEndeks" class="form-control mb-2" step="0.01">
        </div>
        <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">IPTAL</button><button class="btn btn-warning" onclick="okumaKaydet()">FATURA KES</button></div>
    </div></div></div>

    <!-- Endeks Modal -->
    <div class="modal fade" id="endeksModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
        <div class="modal-header"><h5 class="modal-title">✏️ ENDEKS GUNCELLE</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
        <div class="modal-body">
            <p id="endeksBilgi"></p>
            <label>Yeni Endeks</label><input type="number" id="e_yeni" class="form-control mb-2" step="0.01">
        </div>
        <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">IPTAL</button><button class="btn btn-warning" onclick="endeksGuncelle()">FATURA KES</button></div>
    </div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let sifre=location.search.split('sifre=')[1]?.split('&')[0]||'';
        let seciliAbone=null;

        function modalAc(id){new bootstrap.Modal(document.getElementById(id)).show()}
        function modalKapat(id){bootstrap.Modal.getInstance(document.getElementById(id))?.hide()}
        function sekmeDegistir(s){document.getElementById('aboneSekmesi').style.display=s=='aboneler'?'block':'none';document.getElementById('faturaSekmesi').style.display=s=='faturalar'?'block':'none';if(s=='faturalar')faturalariYukle()}

        async function tumVerileriYenile(){aboneleriYukle();faturalariYukle();istatistikleriYukle()}

        async function aboneleriYukle(){
            const r=await fetch('/api/aboneler?sifre='+sifre);
            const data=await r.json();
            let h='';
            data.forEach(a=>{h+=`<tr><td>#${a[0]}</td><td>${a[1]}</td><td>${a[2]||'-'}</td><td>${a[4]}</td><td>${a[5]||'-'}</td><td>${a[7]}</td><td>${a[8]} m³</td><td><button class="btn btn-sm btn-info" onclick="endeksAc('${a[0]}','${a[1]}',${a[8]})">✏️</button><button class="btn btn-sm btn-warning" onclick="aboneDuzenle('${a[0]}')">📝</button><button class="btn btn-sm btn-danger" onclick="aboneSil('${a[0]}')">🗑️</button></td></tr>`});
            document.getElementById('aboneTablo').innerHTML=h||'<tr><td colspan="8">Abone yok</td></tr>';
            document.getElementById('toplamAbone').textContent=data.length;
            // Okuma select doldur
            let sel=document.getElementById('okumaAbone');
            sel.innerHTML='<option value="">ABONE SEC</option>';
            data.forEach(a=>{sel.innerHTML+=`<option value="${a[0]}">#${a[0]} ${a[1]}</option>`});
        }

        async function faturalariYukle(){
            const r=await fetch('/api/faturalar?sifre='+sifre);
            const data=await r.json();
            let h='';
            data.forEach(f=>{
                const durum=f[12];
                const badge=durum=='odendi'?'badge-odendi':durum=='faizli'?'badge-faizli':'badge-odenmedi';
                h+=`<tr class="${durum=='faizli'?'gecikme':''}"><td>#${f[0]}</td><td>#${f[1]}</td><td>${f[9]?f[9].substr(0,10):'-'}</td><td>${f[4]} m³</td><td>${f[8]} TL</td><td>${f[9]||0} TL</td><td>${f[10]?f[10].substr(0,10):'-'}</td><td><span class="${badge}">${durum}</span></td><td>${durum!='odendi'?`<button class="btn btn-sm btn-success" onclick="odemeYap(${f[0]})">💳</button>`:''}<button class="btn btn-sm btn-danger" onclick="faturaSil(${f[0]})">🗑️</button></td></tr>`;
            });
            document.getElementById('faturaTablo').innerHTML=h||'<tr><td colspan="9">Fatura yok</td></tr>';
            istatistikleriYukle();
        }

        async function istatistikleriYukle(){
            const r=await fetch('/api/istatistik?sifre='+sifre);
            const s=await r.json();
            document.getElementById('odenecekToplam').textContent=(s.borc||0)+' TL';
            document.getElementById('faizliBorc').textContent=(s.faizli||0)+' TL';
            document.getElementById('bugunOkuma').textContent=s.bugun||0;
        }

        function endeksAc(no,ad,endeks){
            seciliAbone=no;
            document.getElementById('endeksBilgi').innerHTML=`<strong>#${no} - ${ad}</strong><br>Mevcut Endeks: ${endeks} m³`;
            document.getElementById('e_yeni').value='';
            modalAc('endeksModal');
        }

        async function endeksGuncelle(){
            const y=document.getElementById('e_yeni').value;
            if(!y)return;
            const r=await fetch('/api/endeks-guncelle?sifre='+sifre,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({abone_no:seciliAbone,son_endeks:parseFloat(y)})});
            const s=await r.json();
            if(s.basarili){alert(`✅ Fatura Kesildi!\nTuketim: ${s.tuketim} ton\nToplam: ${s.toplam} TL`);modalKapat('endeksModal');tumVerileriYenile()}
            else alert('❌ '+s.hata);
        }

        async function okumaKaydet(){
            const abone=document.getElementById('okumaAbone').value;
            const son=document.getElementById('sonEndeks').value;
            if(!abone||!son)return alert('Abone ve endeks gerekli!');
            const r=await fetch('/api/endeks-guncelle?sifre='+sifre,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({abone_no:abone,son_endeks:parseFloat(son)})});
            const s=await r.json();
            if(s.basarili){alert(`✅ Fatura Kesildi!\nTuketim: ${s.tuketim} ton\nToplam: ${s.toplam} TL\nSon Odeme: ${s.son_odeme}`);modalKapat('okumaModal');tumVerileriYenile()}
            else alert('❌ '+s.hata);
        }

        async function aboneKaydet(){
            const d={abone_no:document.getElementById('a_no').value,ad_soyad:document.getElementById('a_ad').value,telefon:document.getElementById('a_tel').value,mahalle:document.getElementById('a_mahalle').value,sokak:document.getElementById('a_sokak').value,kapi_no:document.getElementById('a_kapi').value,sayac_no:document.getElementById('a_sayac').value,ilk_endeks:parseFloat(document.getElementById('a_endeks').value)||0};
            if(!d.abone_no||!d.ad_soyad||!d.mahalle)return alert('Zorunlu alanlari doldur!');
            const r=await fetch('/api/abone-ekle?sifre='+sifre,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
            const s=await r.json();
            alert(s.basarili?'✅ '+s.mesaj:'❌ '+s.hata);
            if(s.basarili){modalKapat('aboneModal');tumVerileriYenile()}
        }

        async function aboneSil(no){if(!confirm(`#${no} silinsin mi?`))return;const r=await fetch('/api/abone-sil/'+no+'?sifre='+sifre,{method:'DELETE'});const s=await r.json();alert(s.basarili?'✅ Silindi':'❌ Hata');tumVerileriYenile()}

        async function faturaSil(fn){if(!confirm(`Fatura #${fn} silinsin mi?`))return;const r=await fetch('/api/fatura-sil/'+fn+'?sifre='+sifre,{method:'DELETE'});const s=await r.json();alert(s.basarili?'✅ Silindi':'❌ Hata');tumVerileriYenile()}

        async function odemeYap(fn){const r=await fetch('/api/odeme/'+fn+'?sifre='+sifre,{method:'POST'});const s=await r.json();alert(s.basarili?'✅ Odendi':'❌ Hata');tumVerileriYenile()}

        async function faizIslet(){const r=await fetch('/api/faiz-islet?sifre='+sifre,{method:'POST'});const s=await r.json();alert(s.basarili?`✅ ${s.islenen} faturaya faiz islendi!`:'❌ Hata');tumVerileriYenile()}

        function aboneDuzenle(no){alert('Duzenleme yakinda! Abone No: '+no)}

        tumVerileriYenile();
    </script>
</body>
</html>
'''

# ============ FLASK ROUTES ============
@app.route('/')
def panel():
    sifre = request.args.get('sifre', '')
    if sifre != WEB_PANEL_SIFRE:
        return '''<html><head><title>Giris</title><meta name="viewport" content="width=device-width, initial-scale=1">
        <style>body{font-family:system-ui;background:#0a0a0a;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
        .box{background:#141414;padding:30px;border-radius:15px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,0.5);border:1px solid #2a2a2a}
        input{padding:12px;border:2px solid #333;border-radius:8px;font-size:16px;width:100%;margin:10px 0;background:#2a2a2a;color:#fff}
        button{background:#ffc107;color:#000;border:none;padding:12px 30px;border-radius:8px;font-size:16px;cursor:pointer;font-weight:700}
        h2{color:#ffc107}</style></head>
        <body><div class="box"><h2>💧 Yaka Koyu</h2><p style="color:#888;">Sifre girin</p>
        <form><input type="password" name="sifre" placeholder="Sifre" required><br>
        <button>🔐 Giris</button></form></div></body></html>'''
    return PANEL_HTML

@app.route('/api/aboneler')
def api_aboneler():
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT * FROM aboneler ORDER BY abone_no"); data = c.fetchall()
    conn.close(); return jsonify(data)

@app.route('/api/faturalar')
def api_faturalar():
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT * FROM faturalar WHERE silindi=0 ORDER BY fatura_tarihi DESC LIMIT 100"); data = c.fetchall()
    conn.close(); return jsonify(data)

@app.route('/api/istatistik')
def api_istatistik():
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    bugun = datetime.now().strftime('%Y-%m-%d'); conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aboneler"); abone = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM faturalar WHERE silindi=0 AND date(fatura_tarihi)=?", (bugun,)); bugun_oku = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(toplam_tutar+faiz_tutari),0) FROM faturalar WHERE silindi=0 AND durum!='odendi'"); borc = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(toplam_tutar+faiz_tutari),0) FROM faturalar WHERE silindi=0 AND durum='faizli'"); faizli = c.fetchone()[0]
    c.execute("SELECT fatura_tarihi FROM faturalar WHERE silindi=0 ORDER BY fatura_tarihi DESC LIMIT 1"); son = c.fetchone()
    conn.close(); return jsonify({'abone':abone,'bugun':bugun_oku,'borc':borc,'faizli':faizli,'son':son[0][:16] if son else '-'})

@app.route('/api/endeks-guncelle', methods=['POST'])
def api_endeks_guncelle():
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    data = request.get_json(); abone_no, son_endeks = data['abone_no'], float(data['son_endeks'])
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT onceki_endeks FROM aboneler WHERE abone_no=?", (abone_no,)); abone = c.fetchone()
    if not abone: conn.close(); return jsonify({'basarili':False,'hata':'Abone bulunamadi!'})
    onceki = abone[0]; tuketim = son_endeks - onceki
    if tuketim < 0: conn.close(); return jsonify({'basarili':False,'hata':'Endeks kucuk!'})
    toplam = tuketim * SU_BIRIM_FIYAT + HIZMET_BEDELI
    son_odeme = (datetime.now() + timedelta(days=ODEME_SURESI)).strftime('%Y-%m-%d')
    c.execute("INSERT INTO faturalar (abone_no,onceki_endeks,son_endeks,tuketim_ton,birim_fiyat,su_bedeli,hizmet_bedeli,toplam_tutar,fatura_tarihi,son_odeme_tarihi) VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'),?)",
              (abone_no,onceki,son_endeks,tuketim,SU_BIRIM_FIYAT,tuketim*SU_BIRIM_FIYAT,HIZMET_BEDELI,toplam,son_odeme))
    c.execute("UPDATE aboneler SET onceki_endeks=? WHERE abone_no=?", (son_endeks,abone_no)); conn.commit(); conn.close()
    return jsonify({'basarili':True,'tuketim':tuketim,'toplam':toplam,'son_odeme':son_odeme})

@app.route('/api/abone-ekle', methods=['POST'])
def api_abone_ekle():
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    data = request.get_json()
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("INSERT INTO aboneler (abone_no,ad_soyad,telefon,mahalle,sokak,kapi_no,sayac_no,onceki_endeks) VALUES (?,?,?,?,?,?,?,?)",
                  (data['abone_no'],data['ad_soyad'],data.get('telefon',''),data['mahalle'],data.get('sokak',''),data.get('kapi_no',''),data.get('sayac_no',f"SU-{data['abone_no']}"),data.get('ilk_endeks',0)))
        conn.commit(); conn.close(); return jsonify({'basarili':True,'mesaj':'Abone eklendi!'})
    except Exception as e: return jsonify({'basarili':False,'hata':str(e)})

@app.route('/api/abone-sil/<abone_no>', methods=['DELETE'])
def api_abone_sil(abone_no):
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("UPDATE faturalar SET silindi=1 WHERE abone_no=?", (abone_no,))
        c.execute("DELETE FROM aboneler WHERE abone_no=?", (abone_no,))
        conn.commit(); conn.close(); return jsonify({'basarili':True})
    except Exception as e: return jsonify({'basarili':False,'hata':str(e)})

@app.route('/api/fatura-sil/<int:fatura_no>', methods=['DELETE'])
def api_fatura_sil(fatura_no):
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("UPDATE faturalar SET silindi=1 WHERE fatura_no=?", (fatura_no,))
        conn.commit(); conn.close(); return jsonify({'basarili':True})
    except Exception as e: return jsonify({'basarili':False,'hata':str(e)})

@app.route('/api/odeme/<int:fatura_no>', methods=['POST'])
def api_odeme(fatura_no):
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("UPDATE faturalar SET durum='odendi' WHERE fatura_no=? AND silindi=0", (fatura_no,))
        conn.commit(); conn.close(); return jsonify({'basarili':True})
    except: return jsonify({'basarili':False})

@app.route('/api/faiz-islet', methods=['POST'])
def api_faiz_islet():
    if not api_yetkili(request): return jsonify({'hata':'Yetkisiz'}), 403
    bugun = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT fatura_no,toplam_tutar FROM faturalar WHERE silindi=0 AND durum='odenmedi' AND son_odeme_tarihi IS NOT NULL AND date(son_odeme_tarihi) < ?", (bugun,))
    gecikmis = c.fetchall(); islenen = 0
    for f in gecikmis:
        faiz = round(f[1] * FAIZ_ORANI / 100, 2)
        c.execute("UPDATE faturalar SET faiz_tutari=?, durum='faizli' WHERE fatura_no=?", (faiz, f[0]))
        islenen += 1
    conn.commit(); conn.close()
    return jsonify({'basarili':True,'islenen':islenen})

# ============ TELEGRAM BOT ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update): await update.message.reply_text("⛔ Yetkisiz!"); return
    await update.message.reply_text("💧 YAKA KOYU SU ISLETMESI\n\n/oku [no] [endeks]\n/abone_ekle\n/abone_sorgu [no]\n/abone_liste\n/rapor\n/panel\n/faiz_islet")

async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update): await update.message.reply_text("⛔ Yetkisiz!"); return
    await update.message.reply_text(f"🌐 Panel: https://yaka-koy-final.onrender.com?sifre={os.environ.get('WEB_SIFRE', '')}")

async def faiz_islet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update): await update.message.reply_text("⛔ Yetkisiz!"); return
    bugun = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT fatura_no,toplam_tutar FROM faturalar WHERE silindi=0 AND durum='odenmedi' AND son_odeme_tarihi IS NOT NULL AND date(son_odeme_tarihi) < ?", (bugun,))
    gecikmis = c.fetchall(); islenen = 0
    for f in gecikmis:
        faiz = round(f[1] * FAIZ_ORANI / 100, 2)
        c.execute("UPDATE faturalar SET faiz_tutari=?, durum='faizli' WHERE fatura_no=?", (faiz, f[0]))
        islenen += 1
    conn.commit(); conn.close()
    await update.message.reply_text(f"📈 Faiz Isletildi!\n\n✅ {islenen} faturaya %{FAIZ_ORANI} faiz eklendi.")

async def oku(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update): await update.message.reply_text("⛔ Yetkisiz!"); return
    args = context.args
    if len(args) < 2: await update.message.reply_text("/oku [abone_no] [son_endeks]"); return
    abone_no, son_endeks = args[0], float(args[1]); okuyan = update.effective_user.full_name
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT * FROM aboneler WHERE abone_no=?", (abone_no,)); abone = c.fetchone()
    if not abone: await update.message.reply_text("❌ Abone bulunamadi!"); conn.close(); return
    onceki, tuketim = abone[8], son_endeks - abone[8]
    if tuketim < 0: await update.message.reply_text("❌ Hata!"); conn.close(); return
    toplam = tuketim * SU_BIRIM_FIYAT + HIZMET_BEDELI
    son_odeme = (datetime.now() + timedelta(days=ODEME_SURESI)).strftime('%Y-%m-%d')
    c.execute("INSERT INTO faturalar (abone_no,onceki_endeks,son_endeks,tuketim_ton,birim_fiyat,su_bedeli,hizmet_bedeli,toplam_tutar,fatura_tarihi,son_odeme_tarihi,okuyan) VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'),?,?)",
              (abone_no,onceki,son_endeks,tuketim,SU_BIRIM_FIYAT,tuketim*SU_BIRIM_FIYAT,HIZMET_BEDELI,toplam,son_odeme,okuyan))
    c.execute("UPDATE aboneler SET onceki_endeks=? WHERE abone_no=?", (son_endeks,abone_no)); conn.commit(); conn.close()
    await update.message.reply_text(f"✅ FATURA KESILDI\n👤 #{abone_no} {abone[1]}\n💧 {tuketim} ton\n💰 {toplam} TL\n📅 Son Odeme: {son_odeme}")

async def abone_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update): await update.message.reply_text("⛔ Yetkisiz!"); return
    args = context.args
    if len(args) < 3: await update.message.reply_text("/abone_ekle [no] [ad_soyad] [mahalle] [sokak] [kapi_no] [tel] [sayac_no] [ilk_endeks]"); return
    try:
        abone_no, ad_soyad, mahalle = args[0], args[1].replace('_',' '), args[2].replace('_',' ')
        sokak = args[3].replace('_',' ') if len(args)>3 else ""; kapi_no, telefon = args[4] if len(args)>4 else "", args[5] if len(args)>5 else ""
        sayac_no = args[6] if len(args)>6 else f"SU-{abone_no}"; ilk_endeks = float(args[7]) if len(args)>7 else 0
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("INSERT INTO aboneler VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                  (abone_no,ad_soyad,telefon,None,mahalle,sokak,kapi_no,sayac_no,ilk_endeks))
        conn.commit(); conn.close(); await update.message.reply_text(f"✅ ABONE EKLENDI! #{abone_no} {ad_soyad}")
    except Exception as e: await update.message.reply_text(f"❌ {str(e)}")

async def abone_sorgu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update): await update.message.reply_text("⛔ Yetkisiz!"); return
    if len(context.args) < 1: await update.message.reply_text("/abone_sorgu [abone_no]"); return
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT * FROM aboneler WHERE abone_no=?", (context.args[0],)); abone = c.fetchone()
    if not abone: await update.message.reply_text("❌ Yok!"); conn.close(); return
    c.execute("SELECT * FROM faturalar WHERE abone_no=? AND silindi=0 ORDER BY fatura_tarihi DESC LIMIT 3", (context.args[0],)); faturalar = c.fetchall(); conn.close()
    m = f"📋 #{abone[0]} {abone[1]}\n📍 {abone[4]}\n🔢 {abone[8]} ton\n"
    for f in faturalar:
        faiz = f[9] or 0
        m += f"\n📅 {f[10][:10]} | {f[4]} ton | {f[8]} TL"
        if faiz > 0: m += f" + {faiz} TL faiz"
        m += f" | {f[13]}"
    await update.message.reply_text(m)

async def abone_liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update): await update.message.reply_text("⛔ Yetkisiz!"); return
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aboneler"); t = c.fetchone()[0]
    c.execute("SELECT abone_no, ad_soyad, mahalle, onceki_endeks FROM aboneler LIMIT 50"); aboneler = c.fetchall(); conn.close()
    m = f"📋 TOPLAM: {t}\n\n"
    for a in aboneler: m += f"#{a[0]} {a[1]} | {a[2]} | {a[3]} ton\n"
    await update.message.reply_text(m)

async def rapor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update): await update.message.reply_text("⛔ Yetkisiz!"); return
    bugun = datetime.now().strftime('%Y-%m-%d'); conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(tuketim_ton),0), COALESCE(SUM(toplam_tutar),0) FROM faturalar WHERE silindi=0 AND date(fatura_tarihi)=?", (bugun,)); o = c.fetchone()
    c.execute("SELECT COUNT(*), COALESCE(SUM(toplam_tutar+faiz_tutari),0) FROM faturalar WHERE silindi=0 AND durum!='odendi'"); b = c.fetchone()
    conn.close()
    await update.message.reply_text(f"📊 {bugun}\n📝 {o[0]} okuma\n💧 {o[1]} ton\n💰 {o[2]} TL\n\n⚠️ {b[0]} odenmemis fatura\n💵 {b[1]} TL toplam borc")

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
    bot_app.add_handler(CommandHandler("panel", panel_cmd))
    bot_app.add_handler(CommandHandler("faiz_islet", faiz_islet_cmd))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT), daemon=True).start()
    print("✅ Panel hazir!")
    print("✅ Bot baslatiliyor...")
    bot_app.run_polling()
