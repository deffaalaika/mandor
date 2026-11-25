# mandor

Skill **Claude Code** untuk kerja Android dengan aturan *"eksekusi kode wajib model lokal"*.

Claude jadi **lead engineer** (mandor): menganalisa codebase, menulis plan super-detail, lalu
memverifikasi hasilnya. **Model lokal** (misal Gemma 4 12B di Android Studio Agent Mode) jadi
**junior** yang hanya menerapkan instruksi, step demi step. Claude tidak pernah menulis kode
project, tidak commit, dan tidak push.

```
/mandor <cerita task>        Claude: analisa + tulis plan (di luar repo project)
   │
   ├─ step 1 ── sesi Agent Mode baru ── kamu commit
   ├─ step 2 ── sesi Agent Mode baru ── kamu commit
   └─ step N ── sesi Agent Mode baru ── kamu commit
   │
/mandor verify               Claude: cek semua commit, test, build, device → checklist ✅/❌
   │
   └─ ada ❌ di step K → plan revisi mulai step K (step 1..K-1 dipertahankan)
```

## Kenapa

- Model lokal kecil gampang halu, improvisasi, dan context-nya cepat habis.
- Jadi semua yang butuh mikir (analisa, desain, kode lengkap) ada di plan, dan semua yang butuh
  bukti (diff, test, perilaku di device) dicek Claude di akhir.
- Plan boleh berisi kode lengkap. Yang **menulis ke file** tetap model lokal.

## Persyaratan

- macOS, `git`, `python3` (bawaan Xcode Command Line Tools: `xcode-select --install`)
- [Claude Code](https://docs.claude.com/en/docs/claude-code)
- Model lokal di Android Studio Agent Mode (Settings › Tools › AI › Model Providers, via Ollama/LM Studio)

## Install (satu command, tanpa login GitHub)

```bash
curl -fLO https://raw.githubusercontent.com/deffaalaika/mandor/main/get-mandor.sh
bash get-mandor.sh
```

Script mendownload paket dari [Release terbaru](../../releases/latest) ke `./mandor-download`,
memverifikasi SHA-256, lalu meng-install ke `~/.claude/skills/mandor`. Install yang sudah ada tidak
ditimpa; untuk mengganti (yang lama di-backup ke `~/.claude/skill-backups/mandor.bak-<timestamp>`):

```bash
bash get-mandor.sh --force
```

Lalu buka sesi Claude Code baru. Folder `mandor-download` boleh dihapus.

### Install manual (via browser)

1. Dari [Release terbaru](../../releases/latest), download `mandor.zip` dan `SHA256SUMS` ke satu folder.
2. Download `get-mandor.sh` ke folder yang sama, lalu jalankan dengan folder itu:
   ```bash
   bash get-mandor.sh .
   ```
   Atau manual: `shasum -a 256 -c SHA256SUMS && unzip mandor.zip && bash mandor/install.sh`

Skill **tidak** di-install ke project. Skill hanya jalan kalau kamu ketik `/mandor`.

## Pemakaian

Jalankan Claude Code dari root repo project, working tree bersih.

| Command | Fungsi |
|---|---|
| `/mandor <cerita task>` | Analisa + tulis plan baru. Claude akan **menanyakan lokasi folder plan** (harus di luar repo). |
| `/mandor resume` | Lanjutkan plan yang belum selesai ditulis (mis. sesi Claude sebelumnya putus). |
| `/mandor question <N> <teks>` | Model lokal menulis `QUESTION:` di step N → Claude memperbaiki step-nya. |
| `/mandor verify` | Setelah semua step di-commit: verifikasi lengkap + checklist. Kalau ada yang gagal, lanjut ke plan revisi. |

Selama fase plan dan verify, Claude boleh menjalankan `adb`, emulator, dan Gradle (HP fisik
didahulukan kalau terhubung).

### Satu step = satu sesi = satu commit

1. Buka **sesi baru** Agent Mode.
2. `pbcopy < "<folder-plan>/step-N.md"` lalu paste ke Agent Mode. File step sudah berisi aturan
   eksekutor + instruksi step itu saja.
3. Kalau Agent Mode minta izin menjalankan terminal/Gradle/git/adb: **tolak**.
4. Review sekilas, lalu **commit manual** (pesan commit bebas).
5. Tutup sesi, lanjut step berikutnya.

Folder plan juga berisi `README.md` dengan command `pbcopy` per step, siap tempel.

### Aturan selama satu run

- Jangan merge/rebase dari main, jangan push, dan jangan commit hal lain sampai `/mandor verify`
  lolos. Verify mencocokkan commit ke-N dengan step N berdasarkan urutan.
- Kalau verify menemukan step K gagal, Claude memberi command `git reset` untuk membuang commit
  step K dan seterusnya. **Kamu yang menjalankan.**

## Pengaman

- Saat `/mandor` dipanggil, skill memasang hook `PreToolUse` (`scripts/guard.py`) yang memblokir
  Claude menulis file di repo project dan menjalankan git yang mengubah state (`commit`, `push`,
  `reset`, `checkout`, `rebase`, `merge`, `stash`, dst.). Git baca-saja (`status`, `log`, `diff`,
  `show`) tetap boleh.
- Hook ini aktif **sampai sesi berakhir** (keluar, `/clear`, atau `/resume`). Mau Claude commit
  lagi untuk pekerjaan lain? Mulai sesi baru.
- Cek hook terpasang: ketik `/hooks` setelah `/mandor`. Kalau tidak muncul, organisasi mungkin
  mengunci hook (`strictPluginOnlyCustomization`, cek baris *Setting sources* di `/status`).
  Larangan tetap berlaku lewat instruksi skill, hanya tanpa pengaman otomatis.
- Plan dicek otomatis oleh `scripts/check_plan.py` (format, maksimal 2 file per step, budget
  token, setiap anchor `SEARCH` muncul tepat 1x setelah step sebelumnya diterapkan).
- Hasil eksekusi dicek otomatis oleh `scripts/check_commits.py` (file di luar daftar, isi
  menyimpang dari plan, `@Ignore`/TODO/assert yang hilang, base yang bergeser).

## Uji coba Agent Mode (sekali, ±5 menit)

Sebelum dipakai untuk task beneran, cek model lokalmu di laptop kantor:

1. Buat branch coba-coba di project mana pun.
2. `/mandor` dengan task sepele, misal *"tambah fungsi `isWeekend(date)` di util + unit test-nya"*.
3. Jalankan step-nya di Agent Mode dan perhatikan:
   - [ ] Blok `SEARCH/REPLACE` diterapkan **sebagian saja**, sisa file utuh?
   - [ ] Hanya file di `FILES TO CHANGE` yang berubah?
   - [ ] Tidak minta menjalankan terminal/Gradle (atau patuh saat ditolak)?
   - [ ] Kalau anchor sengaja dirusak, model berhenti dan menulis `QUESTION:`?
4. Commit, lalu `/mandor verify`. Buang branch-nya setelah selesai.

Kalau poin pertama gagal (model menulis ulang file utuh), pakai file yang lebih kecil per step;
plan memilih mode `FULL FILE` hanya untuk file kecil.

## Tips model lokal (16 GB RAM)

- Set context model `num_ctx` sekitar **32k**. Context lebih besar memakan RAM (KV cache) dan
  membuat model kecil makin mudah lupa instruksi. Cek yang benar-benar dipakai: `ollama ps`.
- Budget satu step ±16k token, jadi satu sesi muat jauh di bawah 32k.
- Sebelum `/mandor verify` (Gradle + emulator berat): `ollama stop <model>` supaya RAM lega.
- Default diasumsikan Gemma 4 12B. Cadangan kalau RAM sesak: Qwen 3.5 9B, Nemotron E4B. Bandingkan
  dengan 1–2 task nyata sebelum memilih.

## Privasi

Selama plan/verify, logcat, screenshot, dan isi layar terkirim ke Claude (cloud). Pakai debug
build dan akun test, bukan akun production.

## Isi repo

| Path | Isi |
|---|---|
| `skills/mandor/SKILL.md` | Instruksi untuk Claude |
| `skills/mandor/references/` | Format plan, aturan eksekutor, prosedur planning/verify/revisi, jebakan Android |
| `skills/mandor/scripts/` | `check_plan.py`, `check_commits.py`, `guard.py` (Python stdlib, 3.9+) |
| `get-mandor.sh`, `install.sh` | Installer |
| `build-release.sh` | Membuat `dist/mandor.zip` + `dist/SHA256SUMS` untuk Release |
| `tests/` | Unit test script (`cd tests && python3 -m unittest discover -s .`) dan test installer |
| `docs/design.md` | Dokumen desain |

## Lisensi

Provided as-is.
