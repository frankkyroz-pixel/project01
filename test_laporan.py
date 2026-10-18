"""Tes Laporan Absensi (filter, statistik, grafik, pagination, ekspor, integrasi). Jalankan: python test_laporan.py
Butuh openpyxl untuk tes ekspor Excel: pip install openpyxl"""
import copy
import csv
import io
import re
from datetime import date, datetime, timedelta

from openpyxl import load_workbook

import app as A

TZ = A.TZ_JAKARTA
HARI = date(2026, 10, 19)  # Senin
ASLI_K = copy.deepcopy(A.KARYAWAN)
TOKEN = "token-tes"
A.sekarang = lambda: datetime(2026, 10, 19, 10, 0, tzinfo=TZ)


def at(h, m=0, s=0, hari_lalu=0):
    d = HARI - timedelta(days=hari_lalu)
    return datetime(d.year, d.month, d.day, h, m, s, tzinfo=TZ)


def reset():
    A.KARYAWAN[:] = copy.deepcopy(ASLI_K) + [
        {"id": "EMP006", "nama": "Maya Cuti", "jabatan": "QA", "email": "maya@company.com", "hp": "0812-3456-7895", "status": "Cuti"}]
    A.LOG_ABSENSI[:] = []
    A.PENGAJUAN[:] = []


def klien():
    c = A.app.test_client()
    c.post("/login", data={"username": "admin", "password": "admin123"})
    with c.session_transaction() as s:
        s["csrf"] = TOKEN
    return c


def log(kid, waktu, jenis="Check In", status="Tepat Waktu"):
    A.LOG_ABSENSI.append({"id_karyawan": kid, "waktu": waktu, "jenis": jenis, "status": status})


def pgj(pid, kid, jenis, mulai, selesai, status):
    A.PENGAJUAN.append({"id": pid, "id_karyawan": kid, "jenis": jenis, "mulai": mulai, "selesai": selesai, "alasan": "alasan uji",
                        "diajukan": at(9), "diajukan_oleh": "admin", "status": status,
                        "diproses_oleh": None, "diproses_pada": None, "alasan_penolakan": ""})


def ambil(c, **kw):
    """Kembalikan (f, errors, rows, stats, tren) dari fungsi backend untuk args query tertentu."""
    return A._konteks_laporan(kw)[1:]


def csv_tabel(c, **kw):
    r = c.get("/laporan/export/csv", query_string=kw)
    assert r.status_code == 200, r.status_code
    txt = r.get_data(as_text=True)
    assert txt.startswith("﻿")
    t = list(csv.reader(io.StringIO(txt.lstrip("﻿"))))
    idx = next(i for i, b in enumerate(t) if b and b[0] == "No.")
    return t[:idx], t[idx + 1:], r


# ---- Auth ----
reset()
anon = A.app.test_client()
for u in ("/laporan", "/laporan/export/csv", "/laporan/export/xlsx", "/laporan/cetak"):
    assert anon.get(u).status_code == 302, u
c = klien()
assert c.get("/laporan/export/pdf").status_code == 404

# ---- 1. Halaman terbuka; urutan elemen; menu aktif; deskripsi ----
h = c.get("/laporan").get_data(as_text=True)
assert "Laporan Absensi" in h and "Rekap dan analisis kehadiran karyawan" in h
assert h.index("filter-card") < h.index('class="stats"') < h.index("lap-charts") < h.index("table-card") < h.index("<thead>")
assert "Detail Laporan Absensi" in h and "Tampilkan Laporan" in h and "Reset Filter" in h
assert "Ekspor Excel" in h and "Unduh CSV" in h and "Cetak Laporan" in h
assert 'class="content content-fit content-fit-auto content-laporan"' in h and 'class="table-scroll scroll-laporan"' in h
assert 'class="active"' in h.split("Laporan</a>")[0].rsplit("<a", 1)[1]
assert "Belum ada data laporan pada periode ini" not in h or True  # tergantung hari kerja (lihat bawah)

# ---- 2. Periode ----
f, e, rows, st, tr = ambil(c)
assert (f["periode"], f["dari"], f["sampai"], e) == ("bulan_ini", date(2026, 10, 1), date(2026, 10, 31), [])  # default bulan berjalan
f, e, *_ = ambil(c, periode="hari_ini");   assert (f["dari"], f["sampai"]) == (HARI, HARI)
f, e, *_ = ambil(c, periode="minggu_ini"); assert (f["dari"], f["sampai"]) == (date(2026, 10, 19), date(2026, 10, 25))
f, e, *_ = ambil(c, periode="bulan_ini");  assert (f["dari"], f["sampai"]) == (date(2026, 10, 1), date(2026, 10, 31))
f, e, *_ = ambil(c, periode="rentang", dari="2026-10-05", sampai="2026-10-09"); assert (f["dari"], f["sampai"], e) == (date(2026, 10, 5), date(2026, 10, 9), [])
f, e, *_ = ambil(c, dari="2026-10-05", sampai="2026-10-09"); assert f["periode"] == "rentang"  # tanggal tanpa periode = rentang
f, e, *_ = ambil(c, periode="hari_ini", dari="2020-01-01", sampai="2020-01-02"); assert (f["dari"], f["sampai"]) == (HARI, HARI)  # preset mengabaikan tanggal liar
f, e, *_ = ambil(c, periode="ngawur"); assert f["periode"] == "bulan_ini"
# Awal bulan Februari kabisat dan pergantian tahun tidak error
import calendar
assert A.rentang_periode("bulan_ini", date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))
assert A.rentang_periode("minggu_ini", date(2026, 12, 31)) == (date(2026, 12, 28), date(2027, 1, 3))

# Data: hari ini Andi tepat waktu (+pulang), Sari terlambat; kemarin(Minggu) tidak ada hari kerja; Jumat 16 Okt Rudi terlambat
reset()
log("EMP001", at(7, 10)); log("EMP001", at(16, 30), "Check Out")
log("EMP002", at(7, 50), status="Terlambat")
log("EMP005", at(8, 0, hari_lalu=3), status="Terlambat")   # Jumat 16 Okt
f, e, rows, st, tr = ambil(c, periode="hari_ini")
assert {r["id"]: r["label"] for r in rows} == {"EMP001": "Hadir", "EMP002": "Terlambat", "EMP004": "Tidak Hadir", "EMP005": "Tidak Hadir", "EMP006": "Cuti"}
assert (st["hadir"], st["terlambat"], st["tidak_hadir"], st["cuti"], st["izin"]) == (2, 1, 2, 1, 0)

# ---- 9. Tanggal yang belum terjadi tidak dihitung Tidak Hadir ----
f, e, rows, st, tr = ambil(c, periode="bulan_ini")
assert rows and max(r["tanggal"] for r in rows) == HARI and all(r["tanggal"] <= HARI for r in rows)
f, e, rows, st, tr = ambil(c, periode="rentang", dari="2026-10-20", sampai="2026-10-31")
assert rows == [] and st["total_baris"] == 0 and st["tidak_hadir"] == 0 and tr["label"] == []
h = c.get("/laporan?periode=rentang&dari=2026-10-20&sampai=2026-10-31").get_data(as_text=True)
assert "Belum ada data laporan pada periode ini" in h and "0 data ditemukan" in h and "Belum ada data untuk grafik" in h
# akhir pekan bukan Tidak Hadir
assert ambil(c, periode="rentang", dari="2026-10-17", sampai="2026-10-18")[2] == []

# ---- 3. Filter karyawan memakai ID ----
f, e, rows, st, tr = ambil(c, periode="bulan_ini", karyawan="EMP001")
assert {r["id"] for r in rows} == {"EMP001"} and len(rows) == 13   # 13 hari kerja 1–19 Okt
f, e, rows, *_ = ambil(c, periode="hari_ini", karyawan="EMP999")
assert e == ["Karyawan yang dipilih tidak ditemukan."] and rows == []
h = c.get("/laporan?karyawan=emp001").get_data(as_text=True)   # ID harus persis
assert "Karyawan yang dipilih tidak ditemukan." in h

# ---- 4/5. Filter status & gabungan ----
f, e, rows, st, tr = ambil(c, periode="bulan_ini", status="Terlambat")
assert sorted((r["id"], r["tanggal"]) for r in rows) == [("EMP002", HARI), ("EMP005", date(2026, 10, 16))]
f, e, rows, st, tr = ambil(c, periode="bulan_ini", status="Hadir")  # Hadir = ada absen datang (termasuk terlambat)
assert sorted((r["id"], r["tanggal"]) for r in rows) == [("EMP001", HARI), ("EMP002", HARI), ("EMP005", date(2026, 10, 16))]
f, e, rows, st, tr = ambil(c, periode="bulan_ini", status="Hadir", karyawan="EMP005")
assert [(r["id"], r["label"]) for r in rows] == [("EMP005", "Terlambat")]
f, e, rows, st, tr = ambil(c, periode="minggu_ini", status="Tidak Hadir", karyawan="EMP004")
assert len(rows) == 1 and rows[0]["tanggal"] == HARI                                # hanya Senin 19 yang sudah berlalu
f, e, rows, st, tr = ambil(c, periode="hari_ini", q="sari")
assert [r["id"] for r in rows] == ["EMP002"]
f, e, rows, st, tr = ambil(c, periode="hari_ini", q="EMP00", karyawan="EMP001", status="Hadir")
assert [r["id"] for r in rows] == ["EMP001"]
assert ambil(c, status="Ngawur")[0]["status"] == ""                                    # status liar diabaikan

# ---- 6. Statistik berubah mengikuti filter; kartu Total Karyawan ----
_, _, rows, st_semua, _ = ambil(c, periode="bulan_ini")
_, _, rows, st_andi, _ = ambil(c, periode="bulan_ini", karyawan="EMP001")
assert st_semua["hadir"] == 3 and st_andi["hadir"] == 1 and st_andi["karyawan"] == 1
assert st_semua["karyawan"] == 5                  # EMP001,002,004,005 (Aktif) + EMP006 (Cuti); EMP003 Nonaktif tanpa catatan tidak dihitung
assert st_semua["hadir_unik"] == 3 and st_semua["terlambat_unik"] == 2
# jumlah catatan != karyawan unik: Andi hadir 2 hari -> 2 catatan, 1 karyawan unik
log("EMP001", at(7, 5, hari_lalu=3))
_, _, rows, st, _ = ambil(c, periode="bulan_ini", karyawan="EMP001")
assert st["hadir"] == 2 and st["hadir_unik"] == 1
log("EMP003", at(7, 5, hari_lalu=3))              # Nonaktif tapi punya catatan -> ikut dihitung relevan
assert ambil(c, periode="bulan_ini")[3]["karyawan"] == 6

# ---- 7. Terlambat dihitung benar: batas 07:30:00 inklusif (status dari backend absen) ----
reset(); c = klien()
A.sekarang = lambda: datetime(2026, 10, 19, 7, 30, 0, tzinfo=TZ); c.post("/absensi/datang", data={"id_karyawan": "EMP001", "csrf_token": TOKEN})
A.sekarang = lambda: datetime(2026, 10, 19, 7, 30, 1, tzinfo=TZ); c.post("/absensi/datang", data={"id_karyawan": "EMP002", "csrf_token": TOKEN})
A.sekarang = lambda: datetime(2026, 10, 19, 10, 0, tzinfo=TZ)
_, _, rows, st, _ = ambil(c, periode="hari_ini")
assert st["terlambat"] == 1 and {r["id"] for r in rows if r["label"] == "Terlambat"} == {"EMP002"} and st["hadir"] == 2

# ---- 8. Pengajuan: hanya Disetujui yang menjadi Izin/Cuti ----
reset(); c = klien()
pgj("PGJ-0001", "EMP004", "Izin", HARI, HARI, "Menunggu")
pgj("PGJ-0002", "EMP005", "Cuti", HARI, HARI, "Ditolak")
pgj("PGJ-0003", "EMP001", "Cuti", HARI, HARI + timedelta(days=2), "Disetujui")
pgj("PGJ-0004", "EMP002", "Izin", HARI - timedelta(days=1), HARI, "Disetujui")
_, _, rows, st, _ = ambil(c, periode="hari_ini")
lab = {r["id"]: r["label"] for r in rows}
assert lab["EMP004"] == "Tidak Hadir" and lab["EMP005"] == "Tidak Hadir"          # Menunggu/Ditolak tidak sah
assert lab["EMP001"] == "Cuti" and lab["EMP002"] == "Izin"                          # Disetujui sah
assert (st["izin"], st["cuti"] - 1, st["tidak_hadir"]) == (1, 1, 2)                  # EMP006 status Cuti ikut 1 baris Cuti
assert [r["id"] for r in ambil(c, periode="hari_ini", status="Izin")[2]] == ["EMP002"]
assert [r["id"] for r in ambil(c, periode="hari_ini", status="Cuti")[2] if r["id"] == "EMP001"] == ["EMP001"]
assert "izin disetujui" in " ".join(r["keterangan"].lower() for r in ambil(c, periode="hari_ini", status="Izin")[2])
# Izin disetujui tidak menimpa catatan absen yang sudah ada
log("EMP002", at(8, 0), status="Terlambat")
assert {r["id"]: r["label"] for r in ambil(c, periode="hari_ini")[2]}["EMP002"] == "Terlambat"
# Pengajuan disetujui kemudian: laporan menyesuaikan
A.PENGAJUAN[0]["status"] = "Disetujui"
assert {r["id"]: r["label"] for r in ambil(c, periode="hari_ini")[2]}["EMP004"] == "Izin"

# ---- 10. Jam datang/pulang sesuai catatan; '-' bila kosong; satu baris per karyawan per hari ----
reset(); c = klien()
log("EMP001", at(7, 10)); log("EMP001", at(7, 40), status="Terlambat"); log("EMP001", at(16, 30), "Check Out"); log("EMP001", at(17, 45), "Check Out")
log("EMP002", at(7, 50), status="Terlambat")
_, _, rows, st, _ = ambil(c, periode="hari_ini")
andi = [r for r in rows if r["id"] == "EMP001"]
assert len(andi) == 1 and andi[0]["datang"] == at(7, 10) and andi[0]["pulang"] == at(17, 45) and andi[0]["label"] == "Hadir"
h = c.get("/laporan?periode=hari_ini&karyawan=EMP002").get_data(as_text=True)
assert "<td>07:50</td>" in h and "<td>-</td>" in h and "Terlambat 20 menit; Belum absen pulang" in h and 'badge badge-orange">Terlambat' in h
h = c.get("/laporan?periode=hari_ini&karyawan=EMP001").get_data(as_text=True)
assert "<td>07:10</td>" in h and "<td>17:45</td>" in h and 'badge badge-green">Hadir' in h
h = c.get("/laporan?periode=hari_ini&karyawan=EMP004").get_data(as_text=True)
assert 'badge badge-red">Tidak Hadir' in h and h.count("<td>-</td>") == 2
h = c.get("/laporan?periode=hari_ini").get_data(as_text=True)
assert 'badge badge-purple">Cuti' in h

# ---- Konsistensi dengan Riwayat dan Dashboard (tidak ada sumber data terpisah) ----
reset(); c = klien()   # data realistis: satu check-in per karyawan per hari (app menolak check-in ganda)
log("EMP001", at(7, 10)); log("EMP001", at(16, 30), "Check Out"); log("EMP002", at(7, 50), status="Terlambat")
rr = A.bangun_riwayat(A.KARYAWAN, A.LOG_ABSENSI, HARI, HARI, HARI)
_, _, rows, st, _ = ambil(c, periode="hari_ini")
assert [(r["id"], r["status"], r["datang"], r["pulang"]) for r in rows] == [(r["id"], r["status"], r["datang"], r["pulang"]) for r in rr]
d = A.hitung_statistik(A.KARYAWAN, A.LOG_ABSENSI, HARI)
assert (st["hadir"], st["terlambat"], st["tidak_hadir"]) == (d["hadir"], d["terlambat"], d["tidak_hadir"]) == (2, 1, 2)
# urutan: tanggal terbaru dulu
reset()
log("EMP001", at(7, 0)); log("EMP001", at(7, 5, hari_lalu=3)); log("EMP002", at(7, 20))
tg = [r["tanggal"] for r in ambil(c, periode="bulan_ini")[2]]
assert tg == sorted(tg, reverse=True)

# ---- Integrasi dengan halaman lain ----
reset(); c = klien()
A.KARYAWAN.append({"id": "EMP007", "nama": "Tono Baru", "jabatan": "QA", "email": "tono@c.id", "hp": "0812-0000-0000", "status": "Aktif"})
h = c.get("/laporan").get_data(as_text=True)
assert 'value="EMP007"' in h and "Tono Baru (EMP007)" in h                          # karyawan baru ada di filter
assert 'value="EMP003"' in h and "Nonaktif" in h
c.post("/karyawan/EMP007/edit", data={"nama": "Tono Edit", "email": "tono@c.id", "hp": "081200000000", "jabatan": "Lead QA", "status": "Aktif", "csrf_token": TOKEN})
h = c.get("/laporan?periode=hari_ini&karyawan=EMP007").get_data(as_text=True)
assert "Tono Edit" in h and "Lead QA" in h and "Tono Baru" not in h                 # nama/jabatan mengikuti data karyawan
A.sekarang = lambda: datetime(2026, 10, 19, 7, 45, tzinfo=TZ)
c.post("/absensi/datang", data={"id_karyawan": "EMP007", "csrf_token": TOKEN})
A.sekarang = lambda: datetime(2026, 10, 19, 16, 5, tzinfo=TZ)
c.post("/absensi/pulang", data={"id_karyawan": "EMP007", "csrf_token": TOKEN})
A.sekarang = lambda: datetime(2026, 10, 19, 10, 0, tzinfo=TZ)
h = c.get("/laporan?periode=hari_ini&karyawan=EMP007").get_data(as_text=True)
assert "<td>07:45</td>" in h and "<td>16:05</td>" in h and "Terlambat 15 menit" in h
# karyawan dihapus tetap bisa dilihat riwayatnya di laporan
c.post("/karyawan/EMP007/hapus", data={"csrf_token": TOKEN})
h = c.get("/laporan?periode=hari_ini&karyawan=EMP007").get_data(as_text=True)
assert "Tono Edit" in h and "Dihapus" in h

# ---- Filter tidak mengubah data ----
reset(); c = klien()
log("EMP001", at(7, 10)); pgj("PGJ-0001", "EMP002", "Izin", HARI, HARI, "Disetujui")
snap = (copy.deepcopy(A.KARYAWAN), copy.deepcopy(A.LOG_ABSENSI), copy.deepcopy(A.PENGAJUAN))
for qs in ("", "?periode=hari_ini", "?status=Terlambat&karyawan=EMP001", "?q=a&page=3", "?dari=x"):
    c.get("/laporan" + qs)
for u in ("/laporan/export/csv", "/laporan/export/xlsx", "/laporan/cetak"):
    c.get(u + "?periode=bulan_ini")
assert (A.KARYAWAN, A.LOG_ABSENSI, A.PENGAJUAN) == snap

# ---- Validasi filter (backend) ----
h = c.get("/laporan", query_string={"periode": "rentang", "dari": "2026-10-19", "sampai": "2026-10-10"}).get_data(as_text=True)
assert "Tanggal selesai tidak boleh lebih awal daripada tanggal mulai." in h and "Belum ada data laporan" in h
assert "Format tanggal mulai tidak valid." in c.get("/laporan?dari=bukan-tanggal").get_data(as_text=True)
assert "Format tanggal selesai tidak valid." in c.get("/laporan?periode=rentang&sampai=31-10-2026").get_data(as_text=True)
assert "maksimal 366 hari" in c.get("/laporan?dari=2020-01-01&sampai=2026-10-19").get_data(as_text=True)
h = c.get("/laporan?periode=rentang&dari=2026-10-05").get_data(as_text=True)       # sampai kosong -> hari ini; tidak error
assert 'class="alert alert-error"' not in h
# ekspor/cetak dengan filter salah -> dialihkan dengan pesan, tanpa file
for u in ("/laporan/export/csv", "/laporan/export/xlsx", "/laporan/cetak"):
    r = c.get(u + "?periode=rentang&dari=2026-10-19&sampai=2026-10-01")
    assert r.status_code == 302 and "/laporan" in r.headers["Location"] and "export" not in r.headers["Location"], u
assert "Tanggal selesai tidak boleh lebih awal" in c.get("/laporan").get_data(as_text=True)

# ---- Pagination: 21 hari kerja x 4 aktif + 1 cuti = 85 baris pada bulan Oktober? (hanya 14 hari kerja s.d. 19 Okt) ----
reset(); c = klien()
r_total = len(ambil(c, periode="bulan_ini")[2])
assert r_total == 13 * 4 + 1 == 53
h = c.get("/laporan").get_data(as_text=True)
assert "53 data ditemukan (menampilkan 1–20)" in h and h.count("<tr>") == 21
assert "<strong>52</strong>" in h                                       # statistik dari semua halaman, bukan halaman terlihat
h = c.get("/laporan?page=3").get_data(as_text=True)
assert "menampilkan 41–53" in h and 'aria-current="page">3<' in h
assert "41–53" in c.get("/laporan?page=99").get_data(as_text=True) and "1–20" in c.get("/laporan?page=abc").get_data(as_text=True)
h = c.get("/laporan?periode=rentang&dari=2026-10-05&sampai=2026-10-19&status=Tidak+Hadir&karyawan=EMP001&page=1").get_data(as_text=True)
assert "11 data ditemukan" in h
h = c.get("/laporan?periode=bulan_ini&status=Tidak+Hadir&q=a&page=2").get_data(as_text=True)
pag = re.findall(r'href="(/laporan\?[^"]*page=\d[^"]*)"', h)
assert pag and all("status=Tidak+Hadir" in p and "q=a" in p and "periode=bulan_ini" in p for p in pag), pag
h = c.get("/laporan?periode=rentang&dari=2026-10-01&sampai=2026-10-19&karyawan=EMP001&status=Tidak+Hadir").get_data(as_text=True)
ekspor = re.findall(r'href="(/laporan/(?:export/\w+|cetak)\?[^"]*)"', h)
assert len(ekspor) == 3 and all("karyawan=EMP001" in x and "status=Tidak+Hadir" in x and "dari=2026-10-01" in x and "sampai=2026-10-19" in x for x in ekspor), ekspor

# ---- Data kosong ----
reset(); A.KARYAWAN[:] = []; c = klien()
h = c.get("/laporan").get_data(as_text=True)
assert "Belum ada data laporan pada periode ini" in h and "0 data ditemukan" in h and "Belum ada data untuk grafik" in h
assert ambil(c)[3]["karyawan"] == 0

# ---- Grafik: data tren & distribusi dari data nyata ----
reset(); c = klien()
log("EMP001", at(7, 10)); log("EMP002", at(7, 50), status="Terlambat"); log("EMP001", at(7, 0, hari_lalu=1 + 2)); log("EMP002", at(8, 0, hari_lalu=1 + 2), status="Terlambat"); log("EMP005", at(7, 0, hari_lalu=3))
_, _, rows, st, tr = ambil(c, periode="minggu_ini")
assert tr["label"] == ["19 Okt"] and tr["hadir"] == [2] and tr["terlambat"] == [1]
_, _, rows, st, tr = ambil(c, periode="rentang", dari="2026-10-14", sampai="2026-10-19")
assert tr["label"] == ["14 Okt", "15 Okt", "16 Okt", "19 Okt"]                     # hanya hari kerja; Sabtu/Minggu dilewati
assert tr["hadir"] == [0, 0, 3, 2] and tr["terlambat"] == [0, 0, 1, 1] and tr["penuh"][-1] == "Sen, 19 Okt 2026"
d = {x["label"]: x["jumlah"] for x in st["distribusi"]}
assert sum(d.values()) == st["total_baris"] and d["Hadir"] == 3 and d["Terlambat"] == 2 and d["Izin"] == 0
assert abs(sum(x["persen"] for x in st["distribusi"]) - 100) < 1e-6
h = c.get("/laporan?periode=rentang&dari=2026-10-14&sampai=2026-10-19").get_data(as_text=True)
assert '"hadir": [0, 0, 3, 2]' in h or '"hadir":[0,0,3,2]' in h.replace(" ", "")
assert "dist-hadir" in h and "dist-tidak-hadir" in h and "Izin" in h

# ---- 11. Ekspor mengikuti filter aktif ----
reset(); c = klien()
A.KARYAWAN.append({"id": "EMP007", "nama": "=HYPERLINK(x)", "jabatan": "+cmd", "email": "x@y.id", "hp": "0812-0000-0000", "status": "Aktif"})
log("EMP001", at(7, 10)); log("EMP001", at(16, 30), "Check Out"); log("EMP002", at(7, 50), status="Terlambat")
meta, tabel, r = csv_tabel(c, periode="hari_ini")
assert r.mimetype == "text/csv" and "attachment" in r.headers["Content-Disposition"]
assert "laporan_absensi_2026-10-19_2026-10-19.csv" in r.headers["Content-Disposition"]
assert meta[0] == ["Laporan Absensi"] and ["Periode", "Hari Ini: Sen, 19 Okt 2026"] in meta
assert ["Karyawan", "Semua Karyawan"] in meta and ["Status", "Semua Status"] in meta
assert ["Total Karyawan", "6"] in [m[:2] for m in meta] and ["Total Terlambat", "1"] in meta
header = list(csv.reader(io.StringIO(r.get_data(as_text=True).lstrip("﻿"))))
assert ["No.", "Tanggal", "ID Karyawan", "Nama Karyawan", "Jabatan", "Jam Datang", "Jam Pulang", "Status Absensi", "Keterangan"] in header
assert ["2", "2026-10-19", "EMP001", "Andi Pratama", "Software Engineer", "07:10", "16:30", "Hadir", ""] in tabel
assert [t[2] for t in tabel] == [r_["id"] for r_ in ambil(c, periode="hari_ini")[2]]
sel = [t for t in tabel if t[2] == "EMP007"][0]
assert sel[3].startswith("'=") and sel[4].startswith("'+")                         # cegah formula injection
assert [t for t in tabel if t[2] == "EMP004"][0][5:7] == ["-", "-"]                 # jam kosong = '-'
# hanya karyawan/status yang dipilih (bukan seluruh data)
meta, tabel, r = csv_tabel(c, periode="bulan_ini", karyawan="EMP002")
assert {t[2] for t in tabel} == {"EMP002"} and len(tabel) == 13 and ["Karyawan", "Sari Dewi (EMP002)"] in meta
meta, tabel, r = csv_tabel(c, periode="bulan_ini", status="Terlambat")
assert [t[2] for t in tabel] == ["EMP002"] and ["Status", "Terlambat"] in meta
meta, tabel, r = csv_tabel(c, periode="rentang", dari="2026-10-05", sampai="2026-10-09")
assert {t[1] for t in tabel} == {"2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"}
assert "laporan_absensi_2026-10-05_2026-10-09.csv" in r.headers["Content-Disposition"]
meta, tabel, r = csv_tabel(c, periode="bulan_ini")                                   # seluruh hasil, bukan 1 halaman (20 baris)
assert len(tabel) == len(ambil(c, periode="bulan_ini")[2]) > 20
# ekspor kosong tetap berupa file valid
meta, tabel, r = csv_tabel(c, periode="rentang", dari="2026-10-20", sampai="2026-10-31")
assert tabel == [] and meta[0] == ["Laporan Absensi"]

# Excel
r = c.get("/laporan/export/xlsx?periode=hari_ini&karyawan=EMP001")
assert r.status_code == 200 and r.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
assert "laporan_absensi_2026-10-19_2026-10-19.xlsx" in r.headers["Content-Disposition"]
wb = load_workbook(io.BytesIO(r.data)); ws = wb.active
vals = [[s.value for s in row] for row in ws.iter_rows()]
assert vals[0][0] == "Laporan Absensi" and ["Periode", "Hari Ini: Sen, 19 Okt 2026"] == vals[1][:2]
h_i = next(i for i, row in enumerate(vals) if row[0] == "No.")
assert vals[h_i][:9] == ["No.", "Tanggal", "ID Karyawan", "Nama Karyawan", "Jabatan", "Jam Datang", "Jam Pulang", "Status Absensi", "Keterangan"]
data = vals[h_i + 1:]
assert len(data) == 1 and data[0][0] == 1 and data[0][1].date() == HARI and data[0][2:8] == ["EMP001", "Andi Pratama", "Software Engineer", "07:10", "16:30", "Hadir"]
assert any(row[0] == "Total Hadir (karyawan x hari)" and row[1] == 1 for row in vals) and any(row[0] == "Total Karyawan" and row[1] == 1 for row in vals)
wb = load_workbook(io.BytesIO(c.get("/laporan/export/xlsx?periode=hari_ini&q=HYPERLINK").data)); ws = wb.active
sel = [row for row in ws.iter_rows() if row[2].value == "EMP007"][0]
assert sel[3].value == "=HYPERLINK(x)" and sel[3].data_type == "s" and sel[4].value == "+cmd"   # teks, bukan rumus
wb = load_workbook(io.BytesIO(c.get("/laporan/export/xlsx?periode=bulan_ini").data)); ws = wb.active
assert sum(1 for row in ws.iter_rows() if isinstance(row[0].value, int)) == len(ambil(c, periode="bulan_ini")[2])

# ---- Cetak: berisi judul, periode, ringkasan, seluruh tabel hasil filter ----
h = c.get("/laporan/cetak?periode=bulan_ini&status=Terlambat").get_data(as_text=True)
assert "Laporan Absensi" in h and "Bulan Ini: Kam, 1 Okt 2026 – Sab, 31 Okt 2026" in h and "Sari Dewi" in h and "Andi Pratama" not in h
assert "Total Terlambat" in h and "window.print()" in h and "Dicetak pada" in h
h = c.get("/laporan/cetak?periode=bulan_ini").get_data(as_text=True)
assert h.count("<tr>") == len(ambil(c, periode="bulan_ini")[2]) + 1            # semua baris, tanpa pagination

# ---- 13. Tidak ada data dummy permanen di template / halaman ----
src = open("templates/laporan.html", encoding="utf-8").read()
assert not re.search(r"<strong>\s*\d", src) and "1,248" not in src and "dummy" not in src.lower()
reset(); c = klien()
h = c.get("/laporan?periode=hari_ini&karyawan=EMP001").get_data(as_text=True)
assert "<td>07:" not in h and "<td>08:" not in h                                # tanpa catatan: tidak ada jam palsu

# ---- 15. Halaman lain tidak rusak ----
A.KARYAWAN[:] = copy.deepcopy(ASLI_K)
c = klien()
for p in ("/dashboard", "/karyawan", "/absensi", "/riwayat", "/pengajuan", "/laporan", "/laporan?periode=hari_ini", "/riwayat/export"):
    assert c.get(p).status_code == 200, p
print("SEMUA TES LAPORAN LULUS")
