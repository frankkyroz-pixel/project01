"""Tes Absensi Harian dengan jam terkontrol. Jalankan: python test_absensi.py"""
import copy
from datetime import datetime, time, timedelta, timezone

import app as A

TZ = A.TZ_JAKARTA
HARI = datetime(2026, 10, 19, tzinfo=TZ).date()
ASLI_K = copy.deepcopy(A.KARYAWAN)
TOKEN = "token-tes"
NOW = [None]
A.sekarang = lambda: NOW[0]  # jam terkontrol: semua kode backend membaca A.sekarang()


def at(h, m=0, s=0, us=0, hari_lalu=0):
    d = HARI - timedelta(days=hari_lalu)
    return datetime(d.year, d.month, d.day, h, m, s, us, tzinfo=TZ)


def reset():
    A.KARYAWAN[:] = copy.deepcopy(ASLI_K) + [
        {"id": "EMP006", "nama": "Maya Cuti", "jabatan": "QA", "email": "maya@company.com", "hp": "0812-3456-7895", "status": "Cuti"}]
    A.LOG_ABSENSI[:] = []
    A.JAM_MULAI_DATANG, A.JAM_BATAS_TEPAT_WAKTU, A.JAM_MULAI_PULANG = time(7, 0), time(7, 30), time(16, 0)


def klien():
    c = A.app.test_client()
    c.post("/login", data={"username": "admin", "password": "admin123"})
    with c.session_transaction() as s:
        s["csrf"] = TOKEN
    return c


def absen(c, jenis, kid, waktu, token=TOKEN):
    """POST absen pada jam `waktu`; return HTML halaman hasil (pesan flash)."""
    NOW[0] = waktu
    r = c.post(f"/absensi/{jenis}", data={"id_karyawan": kid, "csrf_token": token})
    assert r.status_code == 302 and r.headers["Location"].endswith("/absensi"), r.status_code
    return c.get("/absensi").get_data(as_text=True)


def catatan(kid=None, jenis=None):
    return [r for r in A.LOG_ABSENSI if (kid is None or r["id_karyawan"] == kid) and (jenis is None or r["jenis"] == jenis)]


# ---- Auth, metode, CSRF ----
reset()
anon = A.app.test_client()
for url in ("/absensi", "/absensi/datang", "/absensi/pulang"):
    assert (anon.post(url) if url != "/absensi" else anon.get(url)).status_code == 302, url
c = klien()
assert c.get("/absensi/datang").status_code == 405 and c.get("/absensi/pulang").status_code == 405  # GET tidak boleh mengubah data
NOW[0] = at(7, 10)
html = absen(c, "datang", "EMP001", at(7, 10), token="salah")
assert "Sesi formulir tidak valid" in html and A.LOG_ABSENSI == []

# ---- Halaman: dua card vertikal, hanya karyawan Aktif di dropdown, jadwal dari konfigurasi ----
NOW[0] = at(9)
h = c.get("/absensi").get_data(as_text=True)
assert 'class="stack"' in h and h.index("Form Absensi") < h.index("Informasi Jadwal Absensi")
assert 'value="EMP001"' in h and 'value="EMP002"' in h and 'value="EMP004"' in h and 'value="EMP005"' in h
assert 'value="EMP003"' not in h and 'value="EMP006"' not in h  # Nonaktif & Cuti tidak muncul
assert "07.00 WIB" in h and "07.30 WIB" in h and "16.00 WIB" in h
assert 'class="active"' in h.split("Absensi</a>")[0].rsplit("<a", 1)[1]  # menu Absensi aktif

# 1. 06:50 -> Tepat Waktu, waktu aktual disimpan, ada keterangan lebih awal
reset(); c = klien()
h = absen(c, "datang", "EMP001", at(6, 50, 0))
r = catatan("EMP001")[0]
assert (r["jenis"], r["status"], r["waktu"]) == ("Check In", "Tepat Waktu", at(6, 50)), r
assert "06:50:00 WIB" in h and "lebih awal" in h and "alert-success" in h

# 2. 07:00 -> Tepat Waktu
reset(); c = klien()
h = absen(c, "datang", "EMP001", at(7, 0, 0))
assert catatan("EMP001")[0]["status"] == "Tepat Waktu" and "lebih awal" not in h

# 3. 07:30:00 -> masih Tepat Waktu (juga 07:30:00.9 karena dibulatkan ke detik)
reset(); c = klien()
absen(c, "datang", "EMP001", at(7, 30, 0))
absen(c, "datang", "EMP002", at(7, 30, 0, 900000))
assert catatan("EMP001")[0]["status"] == "Tepat Waktu" and catatan("EMP002")[0]["status"] == "Tepat Waktu"

# 4. 07:30:01 -> Terlambat (disimpan di backend, pesan oranye)
reset(); c = klien()
h = absen(c, "datang", "EMP001", at(7, 30, 1))
assert catatan("EMP001")[0]["status"] == "Terlambat" and "alert-warning" in h and "07:30:01 WIB" in h

# 5. Absen datang dua kali -> ditolak, tetap satu catatan, waktu pertama tidak ditimpa
reset(); c = klien()
absen(c, "datang", "EMP001", at(7, 10))
h = absen(c, "datang", "EMP001", at(7, 45))
assert len(catatan("EMP001", "Check In")) == 1 and catatan("EMP001")[0]["waktu"] == at(7, 10)
assert "sudah melakukan absen datang" in h and "alert-error" in h

# 6. Pulang sebelum datang -> ditolak (juga setelah jam 16:00)
reset(); c = klien()
h = absen(c, "pulang", "EMP001", at(17, 0))
assert "Silakan lakukan absen datang terlebih dahulu" in h and catatan() == []
h = absen(c, "pulang", "EMP001", at(10, 0))
assert "Silakan lakukan absen datang terlebih dahulu" in h and catatan() == []

# 7. Pulang sebelum 16:00 -> ditolak (15:59:59), tidak ada catatan Check Out
reset(); c = klien()
absen(c, "datang", "EMP001", at(7, 10))
h = absen(c, "pulang", "EMP001", at(15, 59, 59))
assert "belum dimulai" in h and "16.00 WIB" in h and catatan("EMP001", "Check Out") == []

# 8. Pulang tepat 16:00:00 dan setelahnya -> berhasil; status bukan Terlambat
h = absen(c, "pulang", "EMP001", at(16, 0, 0))
co = catatan("EMP001", "Check Out")
assert len(co) == 1 and co[0]["waktu"] == at(16, 0) and co[0]["status"] != "Terlambat" and "alert-success" in h and "16:00:00 WIB" in h
reset(); c = klien()
absen(c, "datang", "EMP002", at(8, 30))  # datang terlambat
absen(c, "pulang", "EMP002", at(17, 45))
assert catatan("EMP002", "Check Out")[0]["status"] == "Tepat Waktu" and catatan("EMP002", "Check In")[0]["status"] == "Terlambat"

# 9. Pulang dua kali -> catatan kedua tidak dibuat
h = absen(c, "pulang", "EMP002", at(18, 0))
assert len(catatan("EMP002", "Check Out")) == 1 and "sudah melakukan absen pulang" in h
assert catatan("EMP002", "Check Out")[0]["waktu"] == at(17, 45)

# 10. Nama tidak terdaftar / kosong / diganti nama (bukan ID) / karyawan dihapus
reset(); c = klien()
for nilai in ("EMP999", "", "Andi Pratama", "emp001", "EMP001 ' OR 1=1"):
    h = absen(c, "datang", nilai, at(7, 10))
    assert ("tidak terdaftar" in h or "pilih nama" in h), nilai
assert A.LOG_ABSENSI == []
A.KARYAWAN[0]["dihapus"] = True
assert "tidak terdaftar" in absen(c, "datang", "EMP001", at(7, 10)) and A.LOG_ABSENSI == []

# 11. Nonaktif / Cuti -> ditolak untuk datang dan pulang
reset(); c = klien()
for kid, st in (("EMP003", "Nonaktif"), ("EMP006", "Cuti")):
    for jenis in ("datang", "pulang"):
        h = absen(c, jenis, kid, at(17, 0))
        assert f"berstatus {st}" in h, (kid, jenis)
assert A.LOG_ABSENSI == []
# karyawan jadi Nonaktif setelah check-in -> pulang ditolak
absen(c, "datang", "EMP001", at(7, 0))
A.KARYAWAN[0]["status"] = "Nonaktif"
assert "berstatus Nonaktif" in absen(c, "pulang", "EMP001", at(17, 0)) and not catatan("EMP001", "Check Out")

# 12. Hari ini berbeda dari kemarin: catatan kemarin tidak menghalangi & tidak tertimpa
reset(); c = klien()
A.LOG_ABSENSI.append({"id_karyawan": "EMP001", "waktu": at(7, 0, hari_lalu=1), "jenis": "Check In", "status": "Tepat Waktu"})
assert "absen datang terlebih dahulu" in absen(c, "pulang", "EMP001", at(17, 0))
assert catatan("EMP001", "Check Out") == []  # check-in kemarin tidak dihitung untuk pulang hari ini
h = absen(c, "datang", "EMP001", at(7, 45))
assert len(catatan("EMP001", "Check In")) == 2 and catatan("EMP001", "Check In")[0]["waktu"] == at(7, 0, hari_lalu=1)
s = A.hitung_statistik(A.KARYAWAN, A.LOG_ABSENSI, HARI)
assert s["hadir"] == 1 and s["terlambat"] == 1

# 13 & 14. Dua karyawan berbeda, tercermin di Dashboard
reset(); c = klien()
absen(c, "datang", "EMP001", at(7, 5))     # Andi tepat waktu
absen(c, "datang", "EMP002", at(7, 50))    # Sari terlambat
absen(c, "pulang", "EMP001", at(16, 30))
assert [(r["id_karyawan"], r["jenis"], r["status"]) for r in A.LOG_ABSENSI] == [
    ("EMP001", "Check In", "Tepat Waktu"), ("EMP002", "Check In", "Terlambat"), ("EMP001", "Check Out", "Tepat Waktu")]
s = A.hitung_statistik(A.KARYAWAN, A.LOG_ABSENSI, HARI)
assert (s["aktif"], s["hadir"], s["terlambat"], s["tidak_hadir"]) == (4, 2, 1, 2), s  # Andi tidak dihitung dua kali
assert (s["persen_hadir"], s["persen_terlambat"], s["persen_tidak_hadir"]) == (50, 25, 50), s
NOW[0] = at(17)
dash = c.get("/dashboard").get_data(as_text=True)
assert "Andi Pratama" in dash and "Sari Dewi" in dash and "Check Out" in dash and "badge-orange" in dash
ln = A.log_terbaru(A.KARYAWAN, A.LOG_ABSENSI)
assert [(x["nama"], x["jenis"]) for x in ln] == [("Andi Pratama", "Check Out"), ("Sari Dewi", "Check In"), ("Andi Pratama", "Check In")]

# Konfigurasi: ubah jam di satu tempat -> validasi dan kartu jadwal ikut berubah
reset(); c = klien()
A.JAM_BATAS_TEPAT_WAKTU, A.JAM_MULAI_PULANG = time(8, 0), time(17, 0)
absen(c, "datang", "EMP001", at(7, 59, 59)); absen(c, "datang", "EMP002", at(8, 0, 1))
assert catatan("EMP001")[0]["status"] == "Tepat Waktu" and catatan("EMP002")[0]["status"] == "Terlambat"
assert "belum dimulai" in absen(c, "pulang", "EMP001", at(16, 30))
assert "berhasil" in absen(c, "pulang", "EMP001", at(17, 0))
NOW[0] = at(9)
h = c.get("/absensi").get_data(as_text=True)
assert "08.00 WIB" in h and "17.00 WIB" in h and "16.00 WIB" not in h

# Zona waktu: jam UTC dikonversi ke WIB (00:30 WIB = 17:30 UTC hari sebelumnya)
reset(); c = klien()
absen(c, "datang", "EMP001", datetime(2026, 10, 19, 0, 20, tzinfo=timezone.utc))  # 07:20 WIB
assert catatan("EMP001")[0]["waktu"] == at(7, 20) and catatan("EMP001")[0]["status"] == "Tepat Waktu"

# Halaman lain tidak terganggu
reset(); c = klien()
for p in ("/dashboard", "/karyawan", "/absensi", "/riwayat", "/pengajuan", "/laporan"):
    assert c.get(p).status_code == 200, p
print("SEMUA TES ABSENSI LULUS")