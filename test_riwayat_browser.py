"""Tes Riwayat Absensi (data, filter, statistik, pagination, export). Jalankan: python test_riwayat.py"""
import copy
import csv
import io
from datetime import date, datetime, timedelta

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


def klien():
    c = A.app.test_client()
    c.post("/login", data={"username": "admin", "password": "admin123"})
    with c.session_transaction() as s:
        s["csrf"] = TOKEN
    return c


def log(kid, waktu, jenis="Check In", status="Tepat Waktu"):
    A.LOG_ABSENSI.append({"id_karyawan": kid, "waktu": waktu, "jenis": jenis, "status": status})


def rows(dari=HARI, sampai=HARI, q="", status=""):
    return A.bangun_riwayat(A.KARYAWAN, A.LOG_ABSENSI, dari, sampai, HARI, q, status)


def by(rs, kid):
    return [r for r in rs if r["id"] == kid]


# ---- Auth ----
anon = A.app.test_client()
assert anon.get("/riwayat").status_code == 302 and anon.get("/riwayat/export").status_code == 302

# ---- Satu baris per karyawan per hari: datang + pulang digabung ----
reset()
log("EMP001", at(7, 10)); log("EMP001", at(16, 30), "Check Out")
log("EMP002", at(7, 50), status="Terlambat")
rs = rows()
r1 = by(rs, "EMP001")
assert len(r1) == 1 and r1[0]["datang"] == at(7, 10) and r1[0]["pulang"] == at(16, 30) and r1[0]["status"] == "Tepat Waktu"
assert r1[0]["keterangan"] == "" and r1[0]["jabatan"] == "Software Engineer" and r1[0]["nama"] == "Andi Pratama"
r2 = by(rs, "EMP002")[0]
assert r2["status"] == "Terlambat" and r2["keterangan"] == "Terlambat 20 menit; Belum absen pulang", r2["keterangan"]
# Tidak Hadir: aktif tanpa check-in; Cuti hanya hari ini; Nonaktif tidak pernah dianggap bolos
assert {r["id"]: r["status"] for r in rs} == {"EMP001": "Tepat Waktu", "EMP002": "Terlambat", "EMP004": "Tidak Hadir",
                                              "EMP005": "Tidak Hadir", "EMP006": "Cuti"}
assert A.statistik_riwayat(rs) == {"hadir": 2, "terlambat": 1, "tidak_hadir": 2}
assert by(rs, "EMP004")[0]["keterangan"] == "Tidak ada absen datang" and by(rs, "EMP006")[0]["keterangan"] == "Sedang cuti"
# konsisten dengan Dashboard untuk hari ini (hadir/terlambat/tidak hadir karyawan aktif)
d = A.hitung_statistik(A.KARYAWAN, A.LOG_ABSENSI, HARI)
assert (d["hadir"], d["terlambat"], d["tidak_hadir"]) == (2, 1, 2)

# ---- Check Out tanpa Check In diabaikan; check-in awal dipakai bila ganda ----
reset()
log("EMP001", at(17, 0), "Check Out")
assert by(rows(), "EMP001")[0]["status"] == "Tidak Hadir"
log("EMP002", at(7, 0), status="Tepat Waktu"); log("EMP002", at(9, 0), status="Terlambat")
assert len(by(rows(), "EMP002")) == 1 and by(rows(), "EMP002")[0]["datang"] == at(7, 0)

# ---- Hari lalu: tidak absen pulang; lebih awal ----
reset()
log("EMP001", at(6, 45, hari_lalu=1 + 2))  # Jumat 16 Okt
rs = rows(HARI - timedelta(days=3), HARI - timedelta(days=3))
assert by(rs, "EMP001")[0]["keterangan"] == "Datang lebih awal; Tidak absen pulang"
assert not by(rs, "EMP006")  # Cuti tidak berlaku mundur

# ---- Akhir pekan tidak menghasilkan Tidak Hadir; catatan nyata tetap tampil ----
reset()
sab, mgg = HARI - timedelta(days=2), HARI - timedelta(days=1)
assert rows(sab, mgg) == []
log("EMP005", at(8, 0, hari_lalu=2), status="Terlambat")
rs = rows(sab, mgg)
assert len(rs) == 1 and rs[0]["id"] == "EMP005"

# ---- Nonaktif & dihapus ----
reset()
log("EMP003", at(7, 5, hari_lalu=3))  # Nonaktif punya catatan lama -> tampil
rs = rows(HARI - timedelta(days=7), HARI)
assert by(rs, "EMP003") and all(r["status"] != "Tidak Hadir" for r in by(rs, "EMP003"))
A.KARYAWAN[0]["dihapus"] = True; log("EMP001", at(7, 1, hari_lalu=3))
rs = rows(HARI - timedelta(days=7), HARI)
assert [r["status"] for r in by(rs, "EMP001")] == ["Tepat Waktu"]  # riwayat lama tampil, tidak dianggap bolos

# ---- Urutan: tanggal terbaru dulu, lalu jam datang terbaru ----
reset()
log("EMP001", at(7, 0)); log("EMP002", at(7, 20)); log("EMP001", at(7, 5, hari_lalu=3))
rs = rows(HARI - timedelta(days=3), HARI)
tgl = [r["tanggal"] for r in rs]
assert tgl == sorted(tgl, reverse=True)
hari_ini = [r for r in rs if r["tanggal"] == HARI]
assert [r["id"] for r in hari_ini[:2]] == ["EMP002", "EMP001"] and hari_ini[2]["datang"] is None

# ---- Filter gabungan: nama/ID + tanggal + status ----
reset()
log("EMP001", at(7, 40, hari_lalu=3), status="Terlambat"); log("EMP002", at(7, 40, hari_lalu=3), status="Terlambat")
log("EMP001", at(7, 10, hari_lalu=2 + 2), status="Tepat Waktu")
rs = rows(HARI - timedelta(days=7), HARI, q="andi", status="Terlambat")
assert [(r["id"], r["tanggal"]) for r in rs] == [("EMP001", HARI - timedelta(days=3))]
assert [r["id"] for r in rows(HARI - timedelta(days=3), HARI - timedelta(days=3), q="emp002", status="Terlambat")] == ["EMP002"]
assert rows(q="zzzz") == []
# pencarian tidak menghapus data
assert len(A.LOG_ABSENSI) == 3 and len(A.KARYAWAN) == 6

# ---- Validasi filter ----
c = klien()
h = c.get("/riwayat", query_string={"dari": "2026-10-19", "sampai": "2026-10-10"}).get_data(as_text=True)
assert "Tanggal awal tidak boleh melebihi tanggal akhir" in h and "Belum ada riwayat absensi" in h
assert "Format tanggal awal tidak valid" in c.get("/riwayat?dari=bukan-tanggal").get_data(as_text=True)
assert "maksimal 366 hari" in c.get("/riwayat?dari=2020-01-01&sampai=2026-10-19").get_data(as_text=True)
assert "Semua Status" in c.get("/riwayat?status=Ngawur").get_data(as_text=True)  # status liar diabaikan

# ---- Integrasi: absen dari halaman Absensi Harian muncul di Riwayat; statistik ikut ----
reset(); c = klien()
A.sekarang = lambda: datetime(2026, 10, 19, 7, 45, tzinfo=TZ)
c.post("/absensi/datang", data={"id_karyawan": "EMP004", "csrf_token": TOKEN})
A.sekarang = lambda: datetime(2026, 10, 19, 10, 0, tzinfo=TZ)
h = c.get("/riwayat?dari=2026-10-19&sampai=2026-10-19&q=EMP004").get_data(as_text=True)
assert "Dewi Puspa" in h and "07:45" in h and 'badge badge-orange">Terlambat' in h and "Terlambat 15 menit" in h
assert "Menampilkan 1–1 dari 1 data" in h

# ---- Halaman: satu hari vs rentang (satuan statistik tidak dicampur) ----
h1 = c.get("/riwayat?dari=2026-10-19&sampai=2026-10-19").get_data(as_text=True)
h2 = c.get("/riwayat?dari=2026-10-12&sampai=2026-10-19").get_data(as_text=True)
assert "karyawan × hari" not in h1 and "bukan karyawan unik" not in h1
assert "karyawan × hari" in h2 and "bukan karyawan unik" in h2
assert "Sen, 19 Okt 2026" in h1 and "—" in h1  # format tanggal Indonesia, jam pulang kosong = —

# ---- Pagination: 85 baris (21 hari kerja x 4 aktif + 1 cuti), statistik dari semua halaman ----
reset(); c = klien()
h = c.get("/riwayat").get_data(as_text=True)
assert "Menampilkan 1–20 dari 85 data" in h and h.count("<tr>") == 21  # 20 baris + header
assert "<strong>84</strong>" in h  # Tidak Hadir bukan hanya halaman terlihat
h = c.get("/riwayat?page=5").get_data(as_text=True)
assert "Menampilkan 81–85 dari 85 data" in h and 'aria-current="page">5<' in h
assert "81–85 dari 85" in c.get("/riwayat?page=99").get_data(as_text=True)
assert "1–20 dari 85" in c.get("/riwayat?page=abc").get_data(as_text=True)
h = c.get("/riwayat?status=Tidak+Hadir&q=a&page=2").get_data(as_text=True)
assert "status=Tidak" in h and "q=a" in h and "dari=2026-09-20" in h  # filter terbawa di tautan halaman

# ---- Data kosong ----
reset(); A.KARYAWAN[:] = []; c = klien()
h = c.get("/riwayat").get_data(as_text=True)
assert "Belum ada riwayat absensi pada periode ini" in h and "Menampilkan 0 data" in h

# ---- Export CSV: seluruh hasil filter, bukan hanya halaman ----
reset(); c = klien()
A.KARYAWAN.append({"id": "EMP007", "nama": "=HYPERLINK(x)", "jabatan": "+cmd", "email": "x@y.id", "hp": "0812-0000-0000", "status": "Aktif"})
log("EMP001", at(7, 10)); log("EMP001", at(16, 30), "Check Out")
r = c.get("/riwayat/export")
assert r.status_code == 200 and r.mimetype == "text/csv" and "attachment" in r.headers["Content-Disposition"]
assert "riwayat_absensi_2026-09-20_2026-10-19.csv" in r.headers["Content-Disposition"]
txt = r.get_data(as_text=True)
assert txt.startswith("\ufeff")
tabel = list(csv.reader(io.StringIO(txt.lstrip("\ufeff"))))
assert tabel[0] == ["Tanggal", "ID Karyawan", "Nama", "Jabatan", "Jam Datang", "Jam Pulang", "Status", "Keterangan"]
assert len(tabel) - 1 == len(rows(HARI - timedelta(days=29), HARI)) > 20
assert ["2026-10-19", "EMP001", "Andi Pratama", "Software Engineer", "07:10", "16:30", "Tepat Waktu", ""] in tabel
sel = [t for t in tabel if t[1] == "EMP007"][0]
assert sel[2].startswith("'=") and sel[3].startswith("'+")  # cegah formula injection
t2 = list(csv.reader(io.StringIO(c.get("/riwayat/export?status=Tepat+Waktu&dari=2026-10-19&sampai=2026-10-19").get_data(as_text=True).lstrip("\ufeff"))))
assert len(t2) == 2 and t2[1][1] == "EMP001"
r = c.get("/riwayat/export?dari=2026-10-19&sampai=2026-10-01")
assert r.status_code == 302 and "/riwayat" in r.headers["Location"]
assert "Tanggal awal tidak boleh melebihi" in c.get("/riwayat").get_data(as_text=True)

# ---- Struktur layout scroll ----
h = klien().get("/riwayat").get_data(as_text=True)
assert 'class="content content-fit content-fit-auto"' in h and 'class="table-scroll scroll-riwayat"' in h
assert h.index("stats-3") < h.index("filter-card") < h.index("table-card") < h.index("<thead>")

# ---- Halaman lain tidak rusak (termasuk data contoh bawaan) ----
A.KARYAWAN[:] = copy.deepcopy(ASLI_K)
c = klien()
for p in ("/dashboard", "/karyawan", "/absensi", "/riwayat", "/pengajuan", "/laporan"):
    assert c.get(p).status_code == 200, p
print("SEMUA TES RIWAYAT LULUS")