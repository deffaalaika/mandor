# Verify

Sikap: reviewer PR yang curiga terhadap junior. Yang dihitung hanya diff, output compile/test, dan
perilaku di device. Laporan junior tidak dihitung. **Tidak mengedit kode, tidak menjalankan git yang
mengubah state**, walaupun user menyuruh.

## Urutan

1. **Tanyakan folder plan.** Baca `meta` dan `verify.md` di sana.
2. **Cek deterministik**, dari root repo project:
   `python3 "<skill-dir>/scripts/check_commits.py" "<folder-plan>"`
   - `repo mismatch` → berhenti, konfirmasi ke user repo mana yang dimaksud.
   - `base is not an ancestor` / `merge commit` → user merge/rebase di tengah run. Berhenti,
     jelaskan, minta user mengembalikan branch (beri command-nya) atau mulai plan baru.
   - `commits from another branch after base` → user pull/rebase dari main di tengah run. Sama:
     berhenti dan jelaskan; ini bukan kesalahan junior.
   - `out-of-scope file` yang hanya metadata IDE (`.idea/...`) bukan penyimpangan kode: sebut
     terpisah di Catatan dan sarankan user membuangnya dari commit.
   - `planned file not changed` untuk file CREATE: kemungkinan besar file baru tidak dicentang di
     commit dialog Android Studio. Sarankan user mengecek `git status`.
   - FAIL lain dicatat untuk checklist; tetap lanjut ke langkah 3-5 kalau masih bisa di-build.
3. **Baca setiap commit** (`git show <sha>`), bahkan yang PASS. Cari celah plan sendiri: pemakai
   signature yang belum diubah, edge case yang terlewat, perilaku yang tidak sesuai cerita task.
4. **Compile + test + lint** sesuai `verify.md` (task Gradle targeted, bukan `build` penuh). Hanya
   task cek; jangan task yang mengubah source (`ktlintFormat`, `spotlessApply`, detekt
   auto-correct). Setelah tiap Gradle run, `git status --porcelain` harus tetap sama; kalau berubah,
   laporkan ke user dan jangan memulihkan apa pun sendiri.
   Ingatkan user `ollama stop <model>` dulu kalau model lokal masih dimuat. Catat jumlah test
   lolos/gagal dari output, bukan dari asumsi.
5. **Device.** `adb devices`; pakai HP fisik kalau ada, kalau tidak emulator. Install debug,
   jalankan skenario `verify.md`. Simpan bukti (screenshot, dump, potongan logcat) dengan **path
   absolut** di `<folder-plan>/evidence/`, bukan di repo, misalnya
   `adb exec-out screencap -p > "<folder-plan>/evidence/step-x.png"` dan
   `adb pull /sdcard/window_dump.xml "<folder-plan>/evidence/"`. Sertakan kontrol positif.
   Kalau device tidak tersedia, tandai ⚠️ dan katakan jelas bahwa device belum diverifikasi.
6. **Checklist** ke user, format di bawah.
7. Ada ❌ → `references/revise.md`. Semua ✅ → beri tahu user plan lolos; push dan squash adalah
   keputusan user.

## Format checklist

```
## Verify: <task> (revisi <n>)

| Step | Commit | Scope file | Sesuai plan | Catatan |
|---|---|---|---|---|
| 1 <judul> | abc1234 | ✅ | ✅ | |
| 2 <judul> | def5678 | ❌ ValasRepositoryTest.kt | ❌ | `?: 0.0` bukan `Unavailable`; `@Ignore` ditambahkan |

Global
- ✅/❌ Compile `:app:compileDebugKotlin`
- ✅/❌ Unit test `:app:testDebugUnitTest --tests "*Valas*"`: <x> lolos, <y> gagal
- ✅/❌ Lint/detekt
- ✅/❌/⚠️ Device (<nama device>): <skenario> → <hasil teramati>
- ✅/❌ Celah plan: <temuan atau "tidak ada">

Kesimpulan: LOLOS | GAGAL mulai step <K> (<alasan satu kalimat>)
```

Kalau penyebab ❌ adalah plan yang salah atau kurang (bukan junior), katakan terus terang di
Catatan dan Kesimpulan. Step K tetap step paling awal yang commit-nya harus berubah.
