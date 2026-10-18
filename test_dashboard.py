"""Tes skenario statistik dashboard. Jalankan: python test_dashboard.py"""
from datetime import datetime, timedelta

from app import TZ_JAKARTA, app, format_tanggal_id, hitung_statistik, log_terbaru

HARI = datetime(2026, 10, 19, 10, 0, tzinfo=TZ_JAKARTA).date()


def w(hari_lalu, jam, menit=0):
    d = HARI - timedelta(days=hari_lalu)
    return datetime(d.year, d.month, d.day, jam, menit, tzinfo=TZ_JAKARTA)


def emp(i, status="Aktif"):
    return {"id": f"E{i}", "nama": f"Nama {i}", "status": status}


def rec(i, waktu, jenis="Check In", status="Tepat Waktu"):
    return {"id_karyawan": f"E{i}", "waktu": waktu, "jenis": jenis, "status": status}


def cek(stats, total, hadir, terlambat, tidak, ph, pt, pth):
    assert (stats["total"], stats["hadir"], stats["terlambat"], stats["tidak_hadir"]) == (total, hadir, terlambat, tidak), stats
    assert (stats["persen_hadir"], stats["persen_terlambat"], stats["persen_tidak_hadir"]) == (ph, pt, pth), stats


# 1. Belum ada karyawan -> semua 0, tanpa error
cek(hitung_statistik([], [], HARI), 0, 0, 0, 0, 0, 0, 0)
# 1b. Ada log tapi tidak ada karyawan
cek(hitung_statistik([], [rec(1, w(0, 8))], HARI), 0, 0, 0, 0, 0, 0, 0)

K = [emp(1), emp(2), emp(3), emp(4)]
# 2. Aktif ada, belum ada absensi -> tidak hadir = semua aktif
cek(hitung_statistik(K, [], HARI), 4, 0, 0, 4, 0, 0, 100)
# 3. Satu check-in tepat waktu
cek(hitung_statistik(K, [rec(1, w(0, 8))], HARI), 4, 1, 0, 3, 25, 0, 75)
# 4. Satu check-in terlambat
cek(hitung_statistik(K, [rec(1, w(0, 8, 20), status="Terlambat")], HARI), 4, 1, 1, 3, 25, 25, 75)
# 5. Check-in + check-out hari sama -> dihitung sekali
cek(hitung_statistik(K, [rec(1, w(0, 8)), rec(1, w(0, 17), "Check Out")], HARI), 4, 1, 0, 3, 25, 0, 75)
# 6. Banyak catatan karyawan sama (termasuk terlambat dobel) -> sekali
L6 = [rec(1, w(0, 8, 20), status="Terlambat"), rec(1, w(0, 9), status="Terlambat"), rec(1, w(0, 17), "Check Out", "Terlambat")]
cek(hitung_statistik(K, L6, HARI), 4, 1, 1, 3, 25, 25, 75)
# 7. Karyawan nonaktif: tidak ikut aktif maupun hadir
K7 = [emp(1), emp(2, "Nonaktif")]
cek(hitung_statistik(K7, [rec(2, w(0, 8))], HARI), 2, 0, 0, 1, 0, 0, 100)
cek(hitung_statistik(K7, [], HARI), 2, 0, 0, 1, 0, 0, 100)
# 7b. Semua nonaktif -> bagi nol aman
cek(hitung_statistik([emp(1, "Nonaktif")], [], HARI), 1, 0, 0, 0, 0, 0, 0)
# 8. Catatan hari sebelumnya tidak dihitung
cek(hitung_statistik(K, [rec(1, w(1, 8), status="Terlambat")], HARI), 4, 0, 0, 4, 0, 0, 100)
# 9. Semua aktif sudah absen -> tidak hadir 0
L9 = [rec(i, w(0, 8)) for i in (1, 2, 3, 4)]
cek(hitung_statistik(K, L9, HARI), 4, 4, 0, 0, 100, 0, 0)
# Tambahan: catatan 'Tidak Hadir'/jenis '-' bukan absensi sah; id tidak dikenal diabaikan
LX = [{"id_karyawan": "E1", "waktu": w(0, 8), "jenis": "-", "status": "Tidak Hadir"}, rec(99, w(0, 8))]
cek(hitung_statistik(K, LX, HARI), 4, 0, 0, 4, 0, 0, 100)
# Tambahan: jam 00:30 WIB tetap hari yang sama; UTC 17:30 hari sebelumnya = 00:30 WIB
from datetime import timezone
utc = datetime(2026, 10, 18, 17, 30, tzinfo=timezone.utc)
cek(hitung_statistik(K, [rec(1, utc)], HARI), 4, 1, 0, 3, 25, 0, 75)

# Log terbaru: urut terbaru, nama dari data karyawan
lt = log_terbaru(K, [rec(1, w(1, 8)), rec(2, w(0, 9)), rec(3, w(0, 8))])
assert [r["nama"] for r in lt] == ["Nama 2", "Nama 3", "Nama 1"], lt
assert log_terbaru([], []) == []

# Format tanggal Indonesia
assert format_tanggal_id(HARI) == "Senin, 19 Oktober 2026", format_tanggal_id(HARI)

# Render nyata lewat Flask test client
c = app.test_client()
assert c.get("/dashboard").status_code == 302  # belum login -> redirect
c.post("/login", data={"username": "admin", "password": "admin123"})
r = c.get("/dashboard")
assert r.status_code == 200
html = r.get_data(as_text=True)
assert "7 Mei 2024" not in html and "1,248" not in html
assert "Belum ada pemberitahuan" in html and "Tutup Semua" not in html
for p in ("/karyawan", "/absensi", "/riwayat", "/pengajuan", "/laporan", "/logout"):
    assert c.get(p).status_code in (200, 302), p
print("SEMUA TES LULUS")