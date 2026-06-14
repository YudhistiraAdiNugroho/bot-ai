# PRD — Hermes Telegram Bot

## 1. Overview
Hermes adalah AI assistant pribadi milik Yudhi, diakses via Telegram (`hermes_telegram.py` / `core/runtime.py`).
Berjalan di VPS pribadi (1GB RAM + 2GB swap).

## 2. Tujuan
- Asisten teknis harian: coding, debugging, problem solving server/VPS.
- Web search untuk info terkini (Tavily, fallback ke DeepSeek knowledge).
- Analisis gambar (Gemini Vision) & file (code, PDF, ZIP project).
- Eksekusi command di VPS (admin only) untuk monitoring/diagnosa.
- Semakin lama dipakai, semakin "kenal" konteks project Yudhi dan semakin sedikit ulangi kesalahan yang sama.

## 3. Tech Stack
- Python 3, `python-telegram-bot` v20+
- AI: DeepSeek — `deepseek-chat` (cepat) & `deepseek-reasoner` (mode deep/coding kompleks)
- Search: Tavily (fallback ke DeepSeek kalau limit/quota habis)
- Vision: Gemini 2.0 Flash
- File upload: Cloudinary (opsional, untuk link download)
- Redis: cache cepat (memory, ai cache, file session, context, rate limit, pending output)
- Firestore: **hanya untuk `bot_rules`** (rules pembelajaran, lihat bagian 6)
- Backend internal: FastAPI di `backend/` (port 7000, dipanggil via `127.0.0.1` dari `core/runtime.py`)

## 4. Struktur Proyek
- `core/runtime.py` — logic utama: chat handler, AI call, memory, cache, exec, dll (masih dalam proses dipecah ke modul-modul `services/`)
- `core/state.py` — shared state/lock antar thread
- `core/clients.py`, `clients/deepseek.py` — client DeepSeek
- `handlers/` — command & message handler (banyak masih import-proxy ke `core/runtime.py`)
- `services/` — modul terpisah: memory, cache, context, file_session, rules, rate_limit, dll
- `backend/` — REST API internal (admin/memory/exec/logs)
- `config/settings.py` — semua konstanta & env var

## 5. Sistem Memory & Cache (Redis + Disk)
Filosofi: **Redis untuk kecepatan (hot path), Disk untuk persistensi** — hindari network round-trip ke Firestore/cloud sebisa mungkin demi responsiveness.

| Data | Redis | Disk | TTL Redis |
|---|---|---|---|
| Chat history (`chat_memories`) | `memory:{user_id}` | `memories/{user_id}.json` (permanen) | `REDIS_TTL` (90 menit) |
| AI answer cache (`ai_cache`) | `aicache:{hash}` | `cache/{hash}.json` | `CACHE_TTL_HOURS` (7 hari) |
| File session (file aktif user) | `filesession:{user_id}` | `file_sessions/{user_id}.json` (permanen) | 30 menit |
| Context follow-up singkat | `ctx:{user_id}` | RAM fallback | `REDIS_TTL` (90 menit) |
| Rules | — | Firestore (`bot_rules`) | cache in-memory 5 menit |

- Auto-summarize: history diringkas otomatis pakai AI kalau ≥ `SUMMARY_THRESHOLD` (30) pesan, sisakan `SUMMARY_KEEP` (10) pesan asli + 1 blok ringkasan. Cap maksimal `MAX_MEMORY` (24).
- Disk pakai atomic write (`tmp` + `os.replace`) — aman dari korupsi kalau proses ke-interrupt.
- Cache disk expired dibersihkan via `scheduled_cleanup` (job berkala).

## 6. Sistem Rules (Pembelajaran Manual)
- Disimpan di Firestore `bot_rules`, dikelola via `/rules add|list|delete|clear` (admin only).
- Tujuan: kalau bot pernah salah/perlu diingatkan sesuatu, Yudhi tambahkan rule → otomatis di-inject ke system prompt setiap kali relevan dengan pertanyaan (keyword match).
- **Belum otomatis** — bot tidak mendeteksi sendiri "ini koreksi" dan menambah rule sendiri. Kalau mau itu, perlu fitur baru (lihat Roadmap).

## 7. Konvensi Pengembangan (WAJIB DIIKUTI)
1. Semua respons ke user dalam **Bahasa Indonesia**, gaya terser/padat.
2. **Implement HANYA yang diminta** — jangan menambah fitur (tombol, opsi, dsb) yang tidak diminta eksplisit.
3. Untuk perbaikan/refactor file: **patch minimal** secara default. Rewrite besar hanya kalau user eksplisit minta "full/maksimal/semua/lengkap".
4. Hormati keterbatasan VPS (1GB RAM + 2GB swap) — tapi jangan terlalu konservatif kalau perubahan memang wajar (disk besar, network call ringan, dll).
5. **Jangan reintroduce dependency Firestore untuk memory/cache/file session** — sudah sengaja dipindah ke Redis+Disk demi responsiveness (lihat Decision Log #3).
6. Kalau menemukan bug/inkonsistensi saat mengerjakan task lain, laporkan dulu sebelum memperbaiki tanpa diminta (kecuali user sudah bilang "audit"/"full").

## 8. Decision Log (kronologis — JANGAN dihapus, biar tidak mengulang kesalahan yang sama)

- **2026-06-14** — Fix bug kritis: di `chat()`, statement `return` setelah cek rate-limit salah indentasi (gak masuk blok `if limited:`), menyebabkan SEMUA pesan teks (grup & pribadi) di-ignore, hanya `/command` yang jalan. Fixed: indent `return` ke dalam `if`.
- **2026-06-14** — Fix bug double file-injection: saat file session aktif + follow-up pendek/keyword match, isi file di-inject 2x bersarang (oleh `should_use_file_session` dan blok `else` sesudahnya). Akibatnya isi file ke AI terpotong & terduplikasi saat truncation (`_FILE_CONTENT_MAX`), bikin bot "lupa" bagian akhir file. Fixed: blok `else` skip re-inject kalau `text` sudah diawali `[FILE:`/`[ZIP PROJECT:`.
- **2026-06-14** — Naikkan kapasitas memory percakapan: `MAX_MEMORY` 12→24, `SUMMARY_THRESHOLD` 16→30, `SUMMARY_KEEP` 4→10, `_CONTEXT_TTL`/`REDIS_TTL` 45→90 menit.
- **2026-06-14** — Migrasi `chat_memories` & `ai_cache` dari Firestore → Redis+Disk. Alasan: tiap pesan bisa hit Firestore 6-8x (load_memory, rules, cache get/set, save_memory, stats) = network latency signifikan. Redis+Disk = lokal, sub-ms, tanpa quota.
- **2026-06-14** — Hapus quota harian cache (`_can_write_cache`/`CACHE_MAX_PER_USER`) — gak relevan lagi tanpa Firestore, disk cukup besar.
- **2026-06-14** — Rules di-cache in-memory 5 menit (sebelumnya query Firestore tiap pesan via `find_relevant_rules`). Cache di-invalidate otomatis saat `/rules add/delete/clear`.
- **2026-06-14** — File session dipersisten ke disk (`file_sessions/{user_id}.json`). Sebelumnya TTL efektif cuma 30 menit (`services/file_session.py`, BUKAN 21600 seperti konstanta dead-code di `core/runtime.py` — konstanta itu sudah dihapus). Sekarang isi file gak hilang sampai `/clearfile` atau upload file baru.
- **2026-06-14** — Tambah `PRD.md` ini sebagai referensi tetap (admin only, di-inject saat konteks relevan dengan development bot).

## 9. Known Issues / Security Notes (belum diperbaiki — perlu keputusan/aksi Yudhi)
- **Backend FastAPI (`backend/`) TANPA AUTENTIKASI**: `/memory/{user_id}` (GET & DELETE — bisa baca/hapus history user manapun), `/exec`, `/logs/*`, `/admin/*` semua publicly accessible tanpa token. Kalau backend bound ke `0.0.0.0` (bukan cuma `127.0.0.1`), ini RCE/data-leak risk. Perlu auth token minimal.
- **Group filter dimatikan**: bot membalas SEMUA pesan di grup, bukan cuma yang mention/reply bot (`if not bot_mentioned: return` di-comment). Review apakah ini disengaja.
- Beberapa fungsi terduplikasi di `core/runtime.py` (`get_user_mode`/`set_user_mode`/`clear_user_mode` didefinisikan 2x) — dead code dari proses refactor yang belum selesai.
- `core/clients.py` & `ask_deepseek` (di `clients/deepseek.py`) ter-import tapi tidak dipakai — dead code.

## 10. Roadmap / Belum Dikerjakan
- Auto-learning rules: deteksi otomatis kalau user mengoreksi jawaban bot → generate rule sendiri (dengan dedup, supaya rules gak numpuk/kontradiksi).
- Auth untuk backend API.
- Lanjutkan refactor `core/runtime.py` (~4000 baris) ke modul-modul `services/` & `handlers/` yang sudah disiapkan tapi belum semua dipakai.
- Migrasi rules dari Firestore ke disk (opsional — kalau mau full lepas dependency Firebase).
