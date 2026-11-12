# OpenJarvis di server ai

OpenJarvis berjalan 24 jam di server `ai`. Anda chat lewat bot Telegram, otaknya model cloud,
dan tool pengingat dipanggil langsung di server lewat MCP (tanpa SSH).

## Isi folder

- `install.sh`: pasang dengan sudo. Membuat folder dan layanan systemd, memasang `jarvis-model`,
  membangun OpenJarvis, lalu meminta Anda memilih model. Aman dijalankan ulang.
- `build.sh`: membangun atau memperbarui OpenJarvis di `/opt/openjarvis` tanpa sudo.
- `bin/jarvis-model`: ganti penyedia, model, dan kunci API.
- `config.toml.template`: konfigurasi awal `/var/lib/openjarvis/config.toml`.
- `systemd/openjarvis.service`: layanan yang menjalankan `jarvis serve`.
- `deploy.sh`: salin folder ini dari laptop (WSL) ke server `~/openjarvis-src`.

## Lokasi di server

| Apa | Di mana |
|---|---|
| Kode OpenJarvis | `/opt/openjarvis/src` (clone fork, branch `main`) |
| Python dan paket | `/opt/openjarvis/python`, `/opt/openjarvis/venv` |
| Konfigurasi dan riwayat chat | `/var/lib/openjarvis` (`config.toml`, `sessions.db`) |
| Kunci API | `/etc/openjarvis/keys.env` (semua kunci), `active.env` (yang aktif); hanya root |
| Token bot Telegram | `/etc/jarvis-tools/telegram.env`, dipakai bersama pengirim pengingat |

Layanan berjalan sebagai akun `jarvis` (tanpa sudo), hanya mendengarkan di `127.0.0.1:8000`,
dan hanya melayani chat Telegram yang ID-nya tercatat di `allowed_chat_ids`.

## Perintah

```bash
sudo jarvis-model                                   # menu; ketik "uji" untuk menguji model rekomendasi sekaligus
sudo jarvis-model use nvidia deepseek-ai/deepseek-v4.1-flash   # ganti cepat, kunci sudah tersimpan
sudo jarvis-model status
journalctl -u openjarvis -f                         # lihat log
bash ~/openjarvis-src/build.sh && sudo systemctl restart openjarvis   # perbarui OpenJarvis
```

## Ganti model tanpa kehilangan konteks

Riwayat chat disimpan OpenJarvis di `sessions.db`, bukan di model. Saat model diganti,
riwayat yang sama dikirim ke model baru. Sekitar 1000 pesan terakhir dipakai utuh; yang lebih lama
diringkas kasar oleh OpenJarvis (`consolidation_threshold` di `config.toml`).

Engine `nim` di OpenJarvis dipakai sebagai klien OpenAI-compatible untuk NVIDIA, OpenRouter,
DeepSeek, dan Moonshot (alamatnya lewat `NIM_HOST`). OpenAI memakai engine `cloud`.
Yang sudah diuji: lihat catatan di `CLAUDE.md`.
