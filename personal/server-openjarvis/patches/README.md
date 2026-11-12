# Tambalan kode inti OpenJarvis

`build.sh` memasang semua `*.patch` di folder ini ke `/opt/openjarvis/src` setiap kali build,
sesudah kode diperbarui dari GitHub. Kode inti di laptop (`~/OpenJarvis`) sengaja dibiarkan bersih.

| Patch | Isi |
|---|---|
| `0001-telegram-terima-file.patch` | Kanal Telegram menyimpan dokumen dari chat yang diizinkan ke folder `OPENJARVIS_TELEGRAM_INBOX`, lalu memberi tahu agen lokasinya. Tanpa variabel itu, atau tanpa `allowed_chat_ids`, dokumen diabaikan. Termasuk 7 tes baru di `tests/channels/test_telegram.py`. |

Dibuat dari commit `9797c9c1`. Kalau build gagal karena patch tidak cocok lagi setelah update upstream:

```bash
cd ~/OpenJarvis
git apply --3way personal/server-openjarvis/patches/0001-telegram-terima-file.patch
# selesaikan konflik, jalankan tes kanal, lalu simpan ulang patch dan bersihkan lagi:
git diff -- src/openjarvis/channels/telegram.py tests/channels/test_telegram.py \
    > personal/server-openjarvis/patches/0001-telegram-terima-file.patch
git checkout -- src/openjarvis/channels/telegram.py tests/channels/test_telegram.py
```

Menjalankan tes kanal tanpa mengubah `.venv` laptop:

```bash
uv run --no-sync --with "pytest>=8" --with "pytest-asyncio>=0.24" python -m pytest -q tests/channels/test_telegram.py
```
