"""Tes browser Laporan (scroll khusus data, grafik, filter, mobile). Jalankan: python test_laporan_browser.py
Butuh: pip install playwright && playwright install chromium"""
import os
import threading
from datetime import timedelta
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
import app as A

SHOT = os.environ.get("SHOT_DIR", "/tmp")
HARI = A.sekarang().date()
A.LOG_ABSENSI[:] = []
for i in range(6, 14):
    A.KARYAWAN.append({"id": f"EMP{i:03d}", "nama": f"Karyawan {i}", "jabatan": "Staff", "email": f"k{i}@c.id", "hp": "0812-0000-0000", "status": "Aktif"})
aktif = [k["id"] for k in A.KARYAWAN if k["status"] == "Aktif"]
for n in range(40):   # catatan nyata (via struktur app) selama 40 hari terakhir
    d = HARI - timedelta(days=n)
    if d.weekday() >= 5:
        continue
    for j, kid in enumerate(aktif):
        if (n + j) % 4 == 0:
            continue   # sebagian tidak hadir
        telat = (n + j) % 5 == 0
        A.LOG_ABSENSI.append({"id_karyawan": kid, "waktu": A.datetime(d.year, d.month, d.day, 8 if telat else 7, 10, tzinfo=A.TZ_JAKARTA),
                              "jenis": "Check In", "status": "Terlambat" if telat else "Tepat Waktu"})
        A.LOG_ABSENSI.append({"id_karyawan": kid, "waktu": A.datetime(d.year, d.month, d.day, 16, 30, tzinfo=A.TZ_JAKARTA), "jenis": "Check Out", "status": "Tepat Waktu"})

srv = make_server("127.0.0.1", 5078, A.app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:5078"
Q60 = "/laporan?periode=rentang&dari=" + (HARI - timedelta(days=59)).isoformat() + "&sampai=" + HARI.isoformat()


def rect(page, sel):
    return page.evaluate("s => { const r = document.querySelector(s).getBoundingClientRect(); return [Math.round(r.top), Math.round(r.left), Math.round(r.height), Math.round(r.width)]; }", sel)


def login(pg):
    pg.goto(URL + "/login"); pg.fill("#username", "admin"); pg.fill("#password", "admin123"); pg.click("button[type=submit]")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    login(pg)
    pg.goto(URL + Q60)

    # ---- Scroll: hanya baris tabel yang bergerak ----
    sel = ".scroll-laporan"
    info = pg.evaluate("s => { const e = document.querySelector(s); return [e.scrollHeight, e.clientHeight]; }", sel)
    assert info[0] > info[1] + 200, info
    doc = pg.evaluate("[document.documentElement.scrollHeight, innerHeight, document.querySelector('.content').scrollHeight, document.querySelector('.content').clientHeight]")
    assert doc[0] <= doc[1] and doc[2] <= doc[3], doc        # tanpa scrollbar ganda: halaman & kolom konten tidak bergulir
    antar = ["aside.sidebar", ".page-head h2", ".filter-card", ".stats", ".lap-charts", "#chart-tren", "#judul-daftar", "#btn-xlsx", "#btn-csv", "#btn-cetak", ".table-laporan thead th"]
    sebelum = {s: rect(pg, s) for s in antar}
    baris_awal = pg.evaluate("document.querySelector('.table-laporan tbody tr td').getBoundingClientRect().top")
    pg.hover(sel); pg.mouse.wheel(0, 700); pg.wait_for_timeout(300)
    assert pg.evaluate("s => document.querySelector(s).scrollTop", sel) > 300
    assert pg.evaluate("[scrollY, document.querySelector('.content').scrollTop]") == [0, 0]
    assert {s: rect(pg, s) for s in antar} == sebelum        # sidebar, judul, filter, statistik, grafik, judul tabel, tombol ekspor, THEAD tetap
    assert pg.evaluate("document.querySelector('.table-laporan tbody tr td').getBoundingClientRect().top") < baris_awal - 200
    pg.mouse.wheel(0, 99999); pg.wait_for_timeout(300)
    assert pg.evaluate("s => { const e = document.querySelector(s); return e.scrollHeight - e.scrollTop - e.clientHeight; }", sel) <= 1
    assert pg.evaluate("scrollY") == 0
    pg.evaluate("document.querySelector('.scroll-laporan').scrollTop = 0")
    pg.screenshot(path=f"{SHOT}/laporan_desktop.png")
    # tidak ada scroll horizontal di tabel pada 1440px
    assert pg.evaluate("(e => e.scrollWidth <= e.clientWidth)(document.querySelector('.scroll-laporan'))")

    heads = pg.eval_on_selector_all(".table-laporan thead th", "e => e.map(x => x.textContent.trim())")
    assert heads == ["No.", "Tanggal", "ID Karyawan", "Nama Karyawan", "Jabatan", "Jam Datang", "Jam Pulang", "Status Absensi", "Keterangan"], heads
    assert pg.evaluate("(() => { const th = document.querySelector('.table-laporan thead th'); return getComputedStyle(th).position; })()") == "sticky"

    # ---- Layar pendek: tidak ada konten terpotong; filter & tombol ekspor tetap terjangkau ----
    for tinggi in (768, 560):
        pg.set_viewport_size({"width": 1440, "height": tinggi}); pg.wait_for_timeout(250)
        ch = pg.evaluate("document.querySelector('.table-card').getBoundingClientRect().height")
        assert ch >= 279, (tinggi, ch)
        # halaman boleh bergulir sebagai cadangan, tetapi tidak ada scroll horizontal dan tombol bisa di-scroll ke tampilan
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        pg.evaluate("document.querySelector('.content').scrollTo(0, 0)")
        assert pg.is_visible("#btn-xlsx") and pg.is_visible("button[type=submit]")
        pg.screenshot(path=f"{SHOT}/laporan_{tinggi}.png")
    pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(250)
    # layar cukup tinggi (1080): tidak ada scroll halaman sama sekali dan tabel mendapat ruang cukup
    pg.set_viewport_size({"width": 1440, "height": 1080}); pg.wait_for_timeout(250)
    assert pg.evaluate("document.querySelector('.content').scrollHeight <= document.querySelector('.content').clientHeight")
    assert pg.evaluate("document.querySelector('.table-card').getBoundingClientRect().height") > 350
    pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(250)

    # ---- Grafik tren: SVG dari data nyata ----
    n_tren = pg.evaluate("JSON.parse(document.getElementById('data-tren').textContent).label.length")
    assert n_tren > 20 and pg.locator("#chart-tren svg").count() == 1
    assert pg.locator("#chart-tren circle").count() == 2 * n_tren
    assert pg.locator("#chart-tren polyline").count() == 2
    assert "karyawan" in pg.locator("#chart-tren circle title").first.text_content()
    assert pg.evaluate("(() => { const s = document.querySelector('#chart-tren svg').getBoundingClientRect(), b = document.getElementById('chart-tren').getBoundingClientRect(); return s.width <= b.width + 1 && s.height <= b.height + 1; })()")
    pg.set_viewport_size({"width": 1100, "height": 900}); pg.wait_for_timeout(400)      # grafik menyesuaikan lebar
    assert pg.evaluate("(() => { const s = document.querySelector('#chart-tren svg').getBoundingClientRect(), b = document.getElementById('chart-tren').getBoundingClientRect(); return Math.abs(s.width - b.width) < 3; })()")
    pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(300)
    # distribusi jumlah = jumlah baris
    total_baris = int(pg.inner_text("#judul-daftar + span").split("·")[1].strip().split()[0])
    dist = sum(int(x) for x in pg.eval_on_selector_all(".dist-val strong", "e => e.map(x => x.textContent)"))
    assert dist == total_baris, (dist, total_baris)

    # ---- Filter UI ----
    pg.goto(URL + "/laporan")
    assert pg.input_value("#f-periode") == "bulan_ini" and pg.is_disabled("#f-dari") and pg.is_disabled("#f-sampai")
    pg.select_option("#f-periode", "hari_ini")
    assert pg.input_value("#f-dari") == HARI.isoformat() and pg.input_value("#f-sampai") == HARI.isoformat()
    pg.select_option("#f-periode", "minggu_ini")
    senin = HARI - timedelta(days=HARI.weekday())
    assert pg.input_value("#f-dari") == senin.isoformat() and pg.input_value("#f-sampai") == (senin + timedelta(days=6)).isoformat()
    pg.select_option("#f-periode", "rentang")
    assert not pg.is_disabled("#f-dari") and not pg.is_disabled("#f-sampai")
    mulai = (HARI - timedelta(days=20)).isoformat()
    pg.fill("#f-dari", mulai); pg.dispatch_event("#f-dari", "change")
    assert pg.get_attribute("#f-sampai", "min") == mulai                           # tanggal selesai tidak bisa sebelum mulai
    pg.fill("#f-sampai", HARI.isoformat())
    pg.select_option("#f-karyawan", "EMP002"); pg.select_option("#f-status", "Terlambat")
    pg.click("text=Tampilkan Laporan"); pg.wait_for_load_state()
    assert "periode=rentang" in pg.url and f"dari={mulai}" in pg.url and "karyawan=EMP002" in pg.url and "status=Terlambat" in pg.url
    baris = pg.eval_on_selector_all(".table-laporan tbody tr", "e => e.map(r => [r.children[2].textContent, r.children[7].textContent.trim()])")
    assert baris and all(r == ["EMP002", "Terlambat"] for r in baris), baris
    assert pg.input_value("#f-karyawan") == "EMP002" and pg.input_value("#f-status") == "Terlambat" and pg.input_value("#f-dari") == mulai
    # pencarian di card tabel mempertahankan filter lain
    pg.fill("#f-q", "sari"); pg.wait_for_url("**q=sari**"); pg.wait_for_load_state()
    assert "karyawan=EMP002" in pg.url and "status=Terlambat" in pg.url and "periode=rentang" in pg.url
    assert pg.input_value("#f-q") == "sari" and pg.evaluate("document.activeElement.id") == "f-q"
    # tautan ekspor memuat filter aktif; file benar-benar terunduh dan berisi data terfilter
    with pg.expect_download() as dl:
        pg.click("#btn-csv")
    path = dl.value.path(); txt = open(path, encoding="utf-8-sig").read()
    assert "Laporan Absensi" in txt and "EMP002" in txt and "EMP001" not in txt and "Terlambat" in txt
    assert dl.value.suggested_filename == f"laporan_absensi_{mulai}_{HARI.isoformat()}.csv"
    with pg.expect_download() as dl:
        pg.click("#btn-xlsx")
    assert dl.value.suggested_filename.endswith(".xlsx") and os.path.getsize(dl.value.path()) > 3000
    # Reset
    pg.click("text=Reset Filter"); pg.wait_for_load_state()
    assert pg.url.endswith("/laporan") and pg.input_value("#f-periode") == "bulan_ini" and pg.input_value("#f-karyawan") == "" and pg.input_value("#f-q") == ""
    # Validasi: tanggal selesai < mulai (lewat URL, melewati validasi HTML5)
    pg.goto(URL + f"/laporan?periode=rentang&dari={HARI.isoformat()}&sampai={(HARI - timedelta(days=3)).isoformat()}")
    assert "Tanggal selesai tidak boleh lebih awal daripada tanggal mulai." in pg.inner_text(".filter-card")
    assert "Belum ada data laporan" in pg.inner_text(".table-laporan tbody")
    # Pagination mempertahankan filter
    pg.goto(URL + Q60 + "&status=Tidak+Hadir"); pg.click(".pagination a:text-is('2')"); pg.wait_for_load_state()
    assert "page=2" in pg.url and "status=Tidak+Hadir" in pg.url and "periode=rentang" in pg.url and pg.input_value("#f-status") == "Tidak Hadir"
    # Cetak: tab baru berisi laporan penuh
    pg.goto(URL + "/laporan?periode=hari_ini")
    with pg.context.expect_page() as np_:
        pg.click("#btn-cetak")
    cp = np_.value; cp.wait_for_load_state()
    assert "/laporan/cetak" in cp.url and "Laporan Absensi" in cp.inner_text("h1") and cp.locator("table tbody tr").count() >= 1
    cp.close()

    # ---- Mobile ----
    m = b.new_page(viewport={"width": 390, "height": 800})
    login(m); m.goto(URL + Q60)
    assert m.evaluate("document.documentElement.scrollWidth <= innerWidth"), m.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    assert m.evaluate("(e => e.scrollWidth > e.clientWidth)(document.querySelector('.scroll-laporan'))")   # tabel bergeser sendiri
    assert m.evaluate("(e => e.getBoundingClientRect().height <= innerHeight * 0.66)(document.querySelector('.scroll-laporan'))")
    assert m.is_visible("#btn-xlsx") and m.is_visible("button[type=submit]") and m.locator("#chart-tren svg").count() == 1
    m.screenshot(path=f"{SHOT}/laporan_mobile.png", full_page=True)
    b.close()
srv.shutdown()
assert not errs, errs
print("SEMUA TES BROWSER LAPORAN LULUS")
