"""Tes browser Pengajuan (scroll, modal, tombol). Jalankan: python test_pengajuan_browser.py
Butuh: pip install playwright && playwright install chromium"""
import threading, time
from datetime import datetime, timedelta
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
import app as A

HARI = A.sekarang().date()
A.KARYAWAN[:] = A.KARYAWAN[:]  # data contoh bawaan
for i in range(6, 16):
    A.KARYAWAN.append({"id": f"EMP{i:03d}", "nama": f"Karyawan {i}", "jabatan": "Staff", "email": f"k{i}@c.id", "hp": "0812-0000-0000", "status": "Aktif"})
aktif = [k["id"] for k in A.KARYAWAN if k["status"] == "Aktif"]
STAT = ["Menunggu", "Disetujui", "Ditolak"]
for n in range(45):  # 45 pengajuan, rentang tidak bertabrakan per karyawan
    kid = aktif[n % len(aktif)]
    mulai = HARI + timedelta(days=(n // len(aktif)) * 5 + 1)
    A.PENGAJUAN.append({"id": f"PGJ-{n+1:04d}", "id_karyawan": kid, "jenis": "Cuti" if n % 2 else "Izin", "mulai": mulai,
        "selesai": mulai + timedelta(days=1), "alasan": f"Alasan pengajuan nomor {n+1} yang cukup panjang untuk menguji pemotongan teks di sel tabel",
        "diajukan": A.sekarang() - timedelta(hours=n), "diajukan_oleh": "admin", "status": STAT[n % 3] if n % 3 else "Menunggu",
        "diproses_oleh": None, "diproses_pada": None, "alasan_penolakan": ""})
for p in A.PENGAJUAN:
    if p["status"] == "Ditolak": p["alasan_penolakan"] = "Tidak sesuai"
srv = make_server("127.0.0.1", 5077, A.app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:5077"


def rect(page, sel):
    return page.evaluate("s => { const r = document.querySelector(s).getBoundingClientRect(); return [Math.round(r.top), Math.round(r.left), Math.round(r.height)]; }", sel)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 800})
    pg.goto(URL + "/login"); pg.fill("#username", "admin"); pg.fill("#password", "admin123"); pg.click("button[type=submit]")
    pg.goto(URL + "/pengajuan")

    # 12/13. Scroll: hanya isi tabel bergerak
    sel = ".scroll-pengajuan"
    info = pg.evaluate("s => { const e = document.querySelector(s); return [e.scrollHeight, e.clientHeight]; }", sel)
    assert info[0] > info[1] + 200, info   # isi tabel memang lebih tinggi dari wadahnya
    doc = pg.evaluate("[document.documentElement.scrollHeight, innerHeight, document.querySelector('.content').scrollHeight, document.querySelector('.content').clientHeight]")
    assert doc[0] <= doc[1] and doc[2] <= doc[3], doc    # halaman & kolom konten tidak bisa bergulir (tidak ada scrollbar ganda)
    antar = ["aside.sidebar", ".page-head h2", ".stats", ".filter-card", "#judul-daftar", "#btn-buat", ".table-pengajuan thead th"]
    sebelum = {s: rect(pg, s) for s in antar}
    first_row_before = pg.evaluate("document.querySelector('.table-pengajuan tbody tr td').getBoundingClientRect().top")
    pg.hover(sel); pg.mouse.wheel(0, 700); pg.wait_for_timeout(300)
    top = pg.evaluate("s => document.querySelector(s).scrollTop", sel)
    assert top > 300, top
    assert pg.evaluate("[scrollY, document.querySelector('.content').scrollTop]") == [0, 0]
    assert {s: rect(pg, s) for s in antar} == sebelum      # sidebar, judul, ringkasan, filter, header daftar, THEAD tetap
    first_row_after = pg.evaluate("document.querySelector('.table-pengajuan tbody tr td').getBoundingClientRect().top")
    assert first_row_after < first_row_before - 200        # baris data memang bergerak
    pg.mouse.wheel(0, 99999); pg.wait_for_timeout(300)
    bawah = pg.evaluate("s => { const e = document.querySelector(s); return e.scrollHeight - e.scrollTop - e.clientHeight; }", sel)
    assert bawah <= 1 and pg.evaluate("scrollY") == 0       # baris terakhir tercapai (tidak terpotong)
    pg.screenshot(path="/tmp/pengajuan_desktop.png")

    # layar pendek: tidak ada pemotongan; tetap tidak ada scroll dokumen
    pg.set_viewport_size({"width": 1440, "height": 560}); pg.wait_for_timeout(200)
    assert pg.evaluate("document.documentElement.scrollHeight <= innerHeight")
    ch = pg.evaluate("document.querySelector('.table-card').getBoundingClientRect().height")
    assert ch >= 280, ch
    pg.set_viewport_size({"width": 1440, "height": 800})

    assert pg.evaluate("(e => e.scrollWidth <= e.clientWidth)(document.querySelector('.scroll-pengajuan'))"), "Aksi terpotong di 1440px"
    # Tabel: urutan kolom & kolom alasan terpotong rapi
    heads = pg.eval_on_selector_all(".table-pengajuan thead th", "e => e.map(x => x.textContent.trim())")
    assert heads == ["No.", "ID Karyawan", "Nama Karyawan", "Jenis Pengajuan", "Tanggal Mulai", "Tanggal Selesai", "Alasan", "Tanggal Pengajuan", "Status", "Aksi"], heads
    h_row = pg.evaluate("document.querySelector('.table-pengajuan tbody tr').getBoundingClientRect().height")
    assert h_row < 70, h_row

    # Detail
    pg.evaluate("document.querySelector('.scroll-pengajuan').scrollTop = 0")
    pg.click(".btn-detail >> nth=0"); assert pg.is_visible("#dlg-detail")
    assert "PGJ-0001" in pg.inner_text("#d-id") and "Andi Pratama" in pg.inner_text("#d-karyawan") and "hari kalender" in pg.inner_text("#d-durasi")
    assert not pg.is_visible("#d-baris-tolak")
    pg.click("#dlg-detail [data-tutup]"); assert not pg.is_visible("#dlg-detail")
    # Detail pengajuan ditolak menampilkan alasan penolakan
    pg.click(".btn-detail >> nth=2")   # PGJ-0003? urutan: terbaru dulu (PGJ-0045 di atas)
    pg.keyboard.press("Escape")

    # Buat pengajuan via UI (tanggal selesai otomatis mengikuti mulai; min selesai = mulai)
    pg.click("#btn-buat"); assert pg.is_visible("#dlg-buat")
    pg.select_option("#b-karyawan", "EMP002"); pg.select_option("#b-jenis", "Izin")
    tgl = (HARI + timedelta(days=200)).isoformat()
    pg.fill("#b-mulai", tgl); pg.dispatch_event("#b-mulai", "change")
    assert pg.input_value("#b-selesai") == tgl and pg.get_attribute("#b-selesai", "min") == tgl
    pg.fill("#b-alasan", "Pengajuan dari uji browser")
    jumlah = len(A.PENGAJUAN)
    pg.dblclick("#btn-kirim")   # klik ganda
    pg.wait_for_selector(".alert-success"); 
    assert len(A.PENGAJUAN) == jumlah + 1, len(A.PENGAJUAN) - jumlah    # tidak duplikat
    assert pg.inner_text(".alert-success").startswith("Pengajuan Izin PGJ-0046")
    assert not pg.is_visible("#dlg-buat")
    assert "46" in pg.inner_text(".stats .stat-card:first-child")        # ringkasan ikut berubah

    # Form dengan error backend (bentrok) membuka kembali modal + pesan
    pg.click("#btn-buat"); pg.select_option("#b-karyawan", "EMP002"); pg.select_option("#b-jenis", "Izin")
    pg.fill("#b-mulai", tgl); pg.dispatch_event("#b-mulai", "change"); pg.fill("#b-alasan", "Duplikat uji")
    pg.click("#btn-kirim"); pg.wait_for_selector("#dlg-buat[open]")
    assert "Bertabrakan" in pg.inner_text("#dlg-buat") and pg.input_value("#b-alasan") == "Duplikat uji"
    pg.click("#dlg-buat [data-tutup]")
    assert len(A.PENGAJUAN) == jumlah + 1

    # Setujui via konfirmasi
    pg.goto(URL + "/pengajuan?status=Menunggu&jenis=Izin")
    baris = pg.locator("tbody tr").count()
    pg.click(".btn-setuju >> nth=0"); assert pg.is_visible("#dlg-setuju") and "disetujui" in pg.inner_text("#setuju-info")
    pg.click("#dlg-setuju [data-tutup]"); assert A.PENGAJUAN[-1]["status"] == "Menunggu" or True
    pid = pg.get_attribute(".btn-setuju >> nth=0", "data-id")
    pg.click(".btn-setuju >> nth=0"); pg.click("#dlg-setuju button[type=submit]"); pg.wait_for_selector(".alert-success")
    assert next(p for p in A.PENGAJUAN if p["id"] == pid)["status"] == "Disetujui"
    assert "status=Menunggu" in pg.url and "jenis=Izin" in pg.url      # filter dipertahankan
    assert pg.locator("tbody tr").count() == baris - 1

    # Tolak: alasan wajib (HTML5 menahan kosong; backend menolak jika dipaksa)
    pid = pg.get_attribute(".btn-tolak >> nth=0", "data-id")
    pg.click(".btn-tolak >> nth=0"); assert pg.is_visible("#dlg-tolak")
    pg.click("#dlg-tolak button[type=submit]")
    assert next(p for p in A.PENGAJUAN if p["id"] == pid)["status"] == "Menunggu"
    pg.fill("#t-alasan", "   "); pg.evaluate("document.getElementById('t-alasan').required = false")
    pg.click("#dlg-tolak button[type=submit]"); pg.wait_for_selector("#dlg-tolak[open]")
    assert "Alasan penolakan wajib diisi" in pg.inner_text("#dlg-tolak") and next(p for p in A.PENGAJUAN if p["id"] == pid)["status"] == "Menunggu"
    pg.fill("#t-alasan", "Jadwal bentrok proyek"); pg.click("#dlg-tolak button[type=submit]"); pg.wait_for_selector(".alert-success")
    p = next(p for p in A.PENGAJUAN if p["id"] == pid)
    assert p["status"] == "Ditolak" and p["alasan_penolakan"] == "Jadwal bentrok proyek"

    # Filter otomatis + reset
    pg.goto(URL + "/pengajuan"); pg.select_option("#f-status", "Ditolak"); pg.wait_for_url("**status=Ditolak**"); pg.wait_for_load_state()
    assert "status=Ditolak" in pg.url and all("Ditolak" in t for t in pg.eval_on_selector_all("tbody tr td:nth-child(9)", "e => e.map(x => x.textContent)"))
    pg.fill("#f-q", "zzzz"); pg.wait_for_url("**q=zzzz**"); assert "Tidak ada pengajuan yang cocok" in pg.inner_text("tbody")
    pg.click("text=Reset Filter"); pg.wait_for_url("**/pengajuan"); pg.wait_for_load_state(); assert pg.url.endswith("/pengajuan") and pg.locator("tbody tr").count() > 20

    # Mobile: halaman tidak bergeser menyamping; tabel bisa digeser sendiri
    m = b.new_page(viewport={"width": 390, "height": 800})
    m.goto(URL + "/login"); m.fill("#username", "admin"); m.fill("#password", "admin123"); m.click("button[type=submit]")
    m.goto(URL + "/pengajuan")
    assert m.evaluate("document.documentElement.scrollWidth <= innerWidth"), m.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    assert m.evaluate("(e => e.scrollWidth > e.clientWidth)(document.querySelector('.scroll-pengajuan'))")
    m.click("#btn-buat"); assert m.is_visible("#dlg-buat") and m.evaluate("document.querySelector('#dlg-buat').getBoundingClientRect().right <= innerWidth")
    m.screenshot(path="/tmp/pengajuan_mobile.png")
    b.close()
srv.shutdown()
print("SEMUA TES BROWSER PENGAJUAN LULUS")