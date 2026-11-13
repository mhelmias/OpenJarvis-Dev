# Jarvis Panel

Panel web untuk mengelola server lewat AI. Semua pengaturan tool SSH ada di panel: daftar server,
mode tiap server, pola izin, riwayat perintah, dan persetujuan. Panel juga menampilkan model AI yang
aktif (dan bisa menggantinya) serta semua tool yang bisa dipakai AI.

## Halaman

| Halaman | Isi |
|---|---|
| Beranda | Perintah yang menunggu persetujuan, aktivitas terbaru, ringkasan model |
| Server | Daftar server, tambah/ubah, pindai kunci host, tes koneksi, kunci SSH panel |
| Model | Model aktif, ganti model (diuji dulu), muat daftar model, uji model rekomendasi, simpan kunci API |
| Tool | Tool yang dipakai AI di Telegram, diambil dari API OpenJarvis (`/v1/tools`) |
| Riwayat | 200 perintah terakhir beserta hasilnya |
| Pengaturan | Ganti kata sandi panel |

## Ganti model dari panel

Panel tidak punya hak mengubah OpenJarvis. Panel hanya menulis permintaan ke
`/var/lib/jarvis-ssh/spool/request.json`; `jarvis-panel-helper.path` lalu menjalankan pembantu root
`/usr/local/sbin/jarvis-panel-helper`. Pembantu hanya mengenal `status`, `models`, `scan`, `use`, dan
`key`, memeriksa semua masukan, dan memakai fungsi `jarvis-model` (model diuji dulu; `use` menyalakan
ulang OpenJarvis). Hasilnya ditulis ke `status.json` dan `result.json`; kunci API tidak pernah ikut ditulis.

## Cara kerja

- OpenJarvis memanggil tool `ssh_servers`, `ssh_run`, dan `ssh_request` (MCP di `127.0.0.1:8019`, pakai token).
- Perintah yang hanya membaca (`df`, `free`, `uptime`, `systemctl status`, `journalctl`, `docker ps`, ...)
  langsung dijalankan, dan hasilnya kembali ke AI.
- Perintah lain disimpan sebagai "menunggu persetujuan". Pemilik mendapat pesan Telegram berisi link
  ke panel. Setelah disetujui, panel menjalankan perintahnya dan mengirim hasilnya ke Telegram.
  Permintaan yang tidak diputuskan dalam 30 menit kedaluwarsa.
- Mode server: `baca` (perintah lain ditolak), `setuju` (perintah lain menunggu persetujuan),
  `bebas` (semua langsung jalan; berbahaya). Pola izin (regex) membuat perintah tertentu ikut otomatis.
- Tanda shell seperti `; && || > $( )` dan backtick selalu memerlukan persetujuan.

## Lokasi di server

| Apa | Di mana |
|---|---|
| Kode dan venv | `/opt/jarvis-tools/panel` |
| Database, kunci SSH panel, known_hosts | `/var/lib/jarvis-ssh` (akun `jarvis-ssh`, hanya pemiliknya) |
| Alamat panel | `/etc/jarvis-ssh/panel.env` (alamat Tailscale server, port 8020) |
| Layanan | `jarvis-panel-web.service`, `jarvis-panel-mcp.service`, `jarvis-panel-helper.path` (+ `.service`, root) |
| Permintaan ganti model | `/var/lib/jarvis-ssh/spool` (`request.json`, `status.json`, `result.json`) |
| Akun AI di server ini | `jarvis-ops` (tanpa sudo, grup `adm` dan `systemd-journal` untuk membaca log) |

## Keamanan

- Panel hanya mendengarkan di alamat Tailscale, jadi hanya perangkat di tailnet Anda yang bisa membukanya.
  Login memakai kata sandi (scrypt), cookie HttpOnly + SameSite=Strict, token CSRF di setiap formulir,
  batas 10 percobaan gagal per 10 menit, dan CSP tanpa JavaScript.
- Tool MCP hanya di `127.0.0.1` dan butuh token Bearer.
- Layanan berjalan sebagai `jarvis-ssh`, tidak bisa membaca data OpenJarvis, kunci API, atau folder file.
  Token bot Telegram diberikan lewat `LoadCredential`.
- SSH memakai kunci panel, `StrictHostKeyChecking=yes`, known_hosts milik panel, dan lingkungan bersih.
  Kunci panel di server tujuan sebaiknya ditulis dengan awalan `restrict`.

## Perintah

```bash
./deploy.sh                                                # dari laptop
sudo bash ~/jarvis-panel-src/install.sh                    # pasang atau pasang ulang
bash ~/jarvis-panel-src/build.sh && sudo systemctl restart jarvis-panel-web jarvis-panel-mcp   # perbarui
sudo jarvis-panel-setup --password                         # ganti kata sandi panel
journalctl -u jarvis-panel-web -u jarvis-panel-mcp --since today
```

## Menambah server lain

1. Di server tujuan, buat akun khusus tanpa sudo (misalnya `jarvis-ops`).
2. Tambahkan kunci panel ke `~/.ssh/authorized_keys` akun itu; perintah siap salin ada di halaman Server.
3. Di panel: Server → Tambah server. Panel memindai dan menyimpan kunci host server itu.
4. Tekan "Tes koneksi".

## Tes

```bash
uv run --no-project --python 3.13 --with-requirements requirements.lock \
    --with pytest --with httpx2 python -m pytest -q tests
```
