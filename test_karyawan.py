"""Tes CRUD, pencarian, pagination Data Karyawan. Jalankan: python test_karyawan.py"""
import copy
import re

import app as A

ASLI_K = copy.deepcopy(A.KARYAWAN)
ASLI_L = copy.deepcopy(A.LOG_ABSENSI)
TOKEN = "token-tes"


def reset():
    A.KARYAWAN[:] = copy.deepcopy(ASLI_K)
    A.LOG_ABSENSI[:] = copy.deepcopy(ASLI_L)


def klien():
    c = A.app.test_client()
    c.post("/login", data={"username": "admin", "password": "admin123"})
    with c.session_transaction() as s:
        s["csrf"] = TOKEN
    return c


def post(c, url, **data):
    data.setdefault("csrf_token", TOKEN)
    return c.post(url, data=data)


def aktif(kid):
    return next((k for k in A.KARYAWAN if k["id"] == kid), None)


VALID = dict(nama="Maya Sari", email="maya@company.com", hp="081234567899", jabatan="Designer")

# Auth: semua route karyawan dilindungi
anon = A.app.test_client()
for method, url in (("get", "/karyawan"), ("post", "/karyawan/tambah"),
                    ("post", "/karyawan/EMP001/edit"), ("post", "/karyawan/EMP001/hapus")):
    assert getattr(anon, method)(url).status_code == 302, url
assert klien().get("/karyawan/EMP001/hapus").status_code == 405  # GET tidak boleh menghapus

# 1. Tambah valid: ID otomatis, status Aktif, nomor dinormalisasi
reset(); c = klien()
r = post(c, "/karyawan/tambah", **VALID)
assert r.status_code == 302
baru = aktif("EMP006")
assert baru and baru["status"] == "Aktif" and baru["hp"] == "0812-3456-7899", baru
assert "Maya Sari" in c.get("/karyawan").get_data(as_text=True)
# +62 juga diterima
post(c, "/karyawan/tambah", nama="Tono", email="tono@company.com", hp="+6281234567000", jabatan="QA")
assert aktif("EMP007")["hp"] == "0812-3456-7000"

# 2. Field kosong ditolak, input lain tetap tampil
reset(); c = klien()
r = post(c, "/karyawan/tambah", nama="", email="", hp="", jabatan="")
html = r.get_data(as_text=True)
assert r.status_code == 400 and len(A.KARYAWAN) == 5
assert html.count("wajib diisi") == 4
r = post(c, "/karyawan/tambah", nama="Maya Sari", email="", hp="081234567899", jabatan="Designer")
html = r.get_data(as_text=True)
assert 'value="Maya Sari"' in html and "Email wajib diisi" in html and len(A.KARYAWAN) == 5

# 3. Email format salah, HP salah
r = post(c, "/karyawan/tambah", **{**VALID, "email": "bukan-email"})
assert r.status_code == 400 and "Format email tidak valid" in r.get_data(as_text=True)
r = post(c, "/karyawan/tambah", **{**VALID, "hp": "12345"})
assert r.status_code == 400 and "Nomor HP tidak valid" in r.get_data(as_text=True)
assert len(A.KARYAWAN) == 5

# 4. Email duplikat (tanpa beda huruf besar/kecil)
r = post(c, "/karyawan/tambah", **{**VALID, "email": "ANDI@company.com"})
assert r.status_code == 400 and "sudah digunakan" in r.get_data(as_text=True) and len(A.KARYAWAN) == 5

# CSRF salah ditolak
r = c.post("/karyawan/tambah", data={**VALID, "csrf_token": "salah"})
assert r.status_code == 302 and len(A.KARYAWAN) == 5

# 5. Edit nama, email, HP, jabatan (hanya baris yang dipilih)
reset(); c = klien()
r = post(c, "/karyawan/EMP002/edit", nama="Sari Dewi Putri", email="sari.putri@company.com",
         hp="081200000001", jabatan="Head of HR", status="Aktif")
assert r.status_code == 302
k = aktif("EMP002")
assert (k["nama"], k["email"], k["hp"], k["jabatan"]) == ("Sari Dewi Putri", "sari.putri@company.com", "0812-0000-0001", "Head of HR")
assert aktif("EMP001")["nama"] == "Andi Pratama" and aktif("EMP004")["nama"] == "Dewi Puspa"
# email sendiri boleh dipakai ulang; email orang lain tidak
r = post(c, "/karyawan/EMP001/edit", nama="Andi Pratama", email="andi@company.com", hp="081234567890", jabatan="Software Engineer", status="Aktif")
assert r.status_code == 302
r = post(c, "/karyawan/EMP001/edit", nama="Andi Pratama", email="sari.putri@company.com", hp="081234567890", jabatan="Software Engineer", status="Aktif")
assert r.status_code == 400 and "sudah digunakan" in r.get_data(as_text=True)
# status tidak valid ditolak, ID tidak ada ditangani
r = post(c, "/karyawan/EMP001/edit", nama="Andi", email="andi@company.com", hp="081234567890", jabatan="SE", status="Libur")
assert r.status_code == 400
assert post(c, "/karyawan/EMP999/edit", **VALID, status="Aktif").status_code == 302

# 6-8. Status Aktif -> Nonaktif -> Cuti -> Aktif tersimpan nyata
def ubah_status(kid, st):
    k = aktif(kid)
    post(c, f"/karyawan/{kid}/edit", nama=k["nama"], email=k["email"], hp=k["hp"], jabatan=k["jabatan"], status=st)
    return aktif(kid)["status"]

reset(); c = klien()
assert ubah_status("EMP001", "Nonaktif") == "Nonaktif"
assert ubah_status("EMP001", "Cuti") == "Cuti"
assert 'badge-orange">Cuti' in c.get("/karyawan").get_data(as_text=True)
# Cuti/Nonaktif tidak dihitung tidak hadir di dashboard; Total tetap
s = A.hitung_statistik(A.KARYAWAN, A.LOG_ABSENSI, A.sekarang().date())
assert s["aktif"] == 3 and s["total"] == 5 and s["hadir"] == 1 and s["tidak_hadir"] == 2, s
assert ubah_status("EMP001", "Aktif") == "Aktif"

# 9. Batal hapus: tidak ada request -> data utuh (dialog hanya client side); GET tak menghapus
reset(); c = klien()
assert len(A.karyawan_terlihat()) == 5
# 10. Hapus setelah konfirmasi (POST): soft delete, riwayat absensi aman
n_log = len(A.LOG_ABSENSI)
r = post(c, "/karyawan/EMP003/hapus")
assert r.status_code == 302
h = c.get("/karyawan").get_data(as_text=True)
assert "<td>EMP003</td>" not in h and "<td>Budi Santoso</td>" not in h
assert aktif("EMP003")["dihapus"] is True and len(A.LOG_ABSENSI) == n_log
dash = c.get("/dashboard").get_data(as_text=True)
assert "Budi Santoso" in dash  # riwayat tetap menampilkan nama
assert A.hitung_statistik(A.KARYAWAN, A.LOG_ABSENSI, A.sekarang().date())["total"] == 4
# email milik karyawan terhapus boleh dipakai lagi; ID tidak dipakai ulang
post(c, "/karyawan/tambah", **{**VALID, "email": "budi@company.com"})
assert aktif("EMP006") is not None and A.cari_karyawan("EMP003") is None

# 11-12. Pencarian
reset(); c = klien()
h = c.get("/karyawan?q=sari").get_data(as_text=True)
assert "Sari Dewi" in h and "Andi Pratama" not in h
h = c.get("/karyawan?q=ENGINEER").get_data(as_text=True)
assert "Andi Pratama" in h and "Sari Dewi" not in h
h = c.get("/karyawan?q=emp004").get_data(as_text=True)
assert "Dewi Puspa" in h and "Rudi" not in h
h = c.get("/karyawan?q=081234567894").get_data(as_text=True)  # HP tanpa tanda hubung
assert "Rudi Hartono" in h
h = c.get("/karyawan?q=zzzz").get_data(as_text=True)
assert "Data karyawan tidak ditemukan" in h
assert "Andi Pratama" in c.get("/karyawan?q=").get_data(as_text=True)

# 13-14. Pagination + hapus di halaman terakhir
reset(); c = klien()
for i in range(6, 26):  # total 25 karyawan -> 3 halaman
    A.KARYAWAN.append({"id": f"EMP{i:03d}", "nama": f"Karyawan {i}", "jabatan": "Staff",
                       "email": f"k{i}@company.com", "hp": f"0812-0000-{i:04d}", "status": "Aktif"})
h = c.get("/karyawan").get_data(as_text=True)
assert "Menampilkan 1–10 dari 25 data" in h and h.count("<tr>") == 11  # 10 baris + header
h = c.get("/karyawan?page=3").get_data(as_text=True)
assert "Menampilkan 21–25 dari 25 data" in h and "Karyawan 25" in h
assert 'aria-current="page">3<' in h
# di luar rentang -> halaman valid terdekat
assert "21–25 dari 25" in c.get("/karyawan?page=99").get_data(as_text=True)
assert "1–10 dari 25" in c.get("/karyawan?page=abc").get_data(as_text=True)
# pencarian + pagination: parameter q dipertahankan di tautan
h = c.get("/karyawan?q=karyawan&page=2").get_data(as_text=True)
assert "q=karyawan" in h and "11–20 dari 20" in h
# hapus sampai halaman 3 kosong -> pindah ke halaman terakhir yang valid
for i in range(21, 26):
    r = post(c, f"/karyawan/EMP{i:03d}/hapus", page="3")
h = c.get(r.headers["Location"]).get_data(as_text=True)
assert "11–20 dari 20" in h and "Menampilkan" in h
# tambah -> diarahkan ke halaman terakhir
post(c, "/karyawan/tambah", **VALID)
h = c.get(c.post("/karyawan/tambah", data={**VALID, "email": "lain@company.com", "csrf_token": TOKEN}).headers["Location"]).get_data(as_text=True)
assert "Maya Sari" in h

# 15. Struktur layout scroll (diverifikasi visual di tes browser terpisah)
h = klien().get("/karyawan").get_data(as_text=True)
assert 'class="content content-fit"' in h and 'class="table-scroll"' in h

# 16. Halaman lain dan riwayat absensi aman
reset(); c = klien()
for p in ("/dashboard", "/absensi", "/riwayat", "/pengajuan", "/laporan"):
    assert c.get(p).status_code == 200, p
assert A.LOG_ABSENSI == ASLI_L
print("SEMUA TES KARYAWAN LULUS")