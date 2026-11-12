# jarvis-tools

Tool OpenJarvis yang disimpan dan berjalan di server Ubuntu `ai` (i5-4590S).
OpenJarvis di server menjalankan `jarvis-mcp` langsung; OpenJarvis di laptop memanggilnya lewat SSH.

## Isi

- `jarvis_tools/mcp_server.py`: server MCP (stdio) yang menggabungkan semua tool di bawah.
- `jarvis_tools/tasks_tools.py`: tool `add_reminder`, `list_tasks`, `complete_task`, `snooze_task`.
- `jarvis_tools/files_tools.py`: tool `list_files` dan `send_file` (kirim file dari folder kerja ke Telegram).
- `jarvis_tools/timeparse.py`: mengubah frasa seperti "besok jam 9 pagi" menjadi tanggal WIB.
- `jarvis_tools/send_due.py`: dijalankan systemd tiap menit untuk mengirim pengingat ke Telegram.
- `jarvis_tools/setup_telegram.py`: menyimpan token dan chat Telegram (`sudo jarvis-telegram-setup`).
- `excel/`: tool Excel pihak ketiga (`excel-mcp-server`), versi dan hash dikunci di `requirements.lock`.
- `install.sh`: pemasangan dasar di server, butuh sudo, aman dijalankan ulang.
- `install-excel.sh`: memasang folder kerja, layanan `jarvis-excel`, dan menyambungkannya ke OpenJarvis (sudo).
- `deploy.sh`: menyalin kode dari laptop ke server.

## Lokasi di server

- `/opt/jarvis-tools`: kode program, milik akun admin. Tool Excel di `/opt/jarvis-tools/excel/venv`.
- `/var/lib/jarvis-tools/tasks.db`: database tugas, milik akun `jarvis`.
- `/etc/jarvis-tools/telegram.env`: token dan chat Telegram, hanya bisa dibaca root dan `jarvis`.
- `/srv/jarvis-files`: folder kerja untuk file Excel dan file lain, grup `jarvis-files` (`jarvis` dan akun admin).
- `jarvis-reminders.timer`: menjalankan pengirim pengingat setiap menit.
- `jarvis-excel.service`: tool Excel di `127.0.0.1:8017/mcp`.

## Keamanan

Akun `jarvis` tidak punya kata sandi dan tidak bisa memakai sudo. Kunci SSH OpenJarvis
(`~/.ssh/jarvis_tools` di laptop) hanya boleh menjalankan `/opt/jarvis-tools/bin/jarvis-mcp`.

Tool Excel adalah kode pihak ketiga, jadi dijalankan sebagai layanan terpisah, bukan anak proses
OpenJarvis (anak proses ikut menerima kunci API). Layanannya tidak punya akses internet, tidak bisa
membaca kunci, token, atau data OpenJarvis, dan hanya boleh menulis ke `/srv/jarvis-files`.
`excel-mcp-server` sendiri juga menolak path di luar folder itu.

Catatan: file buatan tool Excel berizin 600 (hanya akun `jarvis`), jadi akun admin bisa melihat
namanya tetapi belum bisa membuka isinya.

## Perintah (dari Ubuntu/WSL di laptop)

```bash
./deploy.sh
ssh ai 'cd jarvis-tools-src && python3 -m unittest discover -s tests'
ssh -t ai 'sudo bash ~/jarvis-tools-src/install.sh'
ssh -t ai 'sudo bash ~/jarvis-tools-src/install-excel.sh'
ssh ai 'journalctl -u jarvis-reminders --since today'
ssh ai 'journalctl -u jarvis-excel --since today'
```
