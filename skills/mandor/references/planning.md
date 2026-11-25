# Planning

Target pembaca plan: model kecil dengan context 32k yang **tidak bisa** menjalankan apa pun, tidak
melihat step lain, dan cenderung improvisasi. Setiap keputusan sudah diambil di plan.

## 1. Analisa

- Struktur modul, arsitektur, DI (Hilt/Koin/manual), konvensi penamaan, style.
- Library test yang **sudah** dipakai (JUnit4/5, MockK/Mockito, Turbine, coroutines-test,
  Robolectric). Test di plan hanya memakai library ini.
- Lint/detekt/ktlint yang dikonfigurasi project (untuk verify.md).
- Reproduksi masalah kalau perlu: `./gradlew :<module>:installDebug`, `adb shell am start ...`,
  `adb logcat -d -b crash`, `adb exec-out uiautomator dump /dev/tty`.
- **Setiap simbol yang signature/tipe-nya berubah: cari semua pemakainya**
  (`git grep -n "<simbol>"`), termasuk test. Semua pemakai wajib ikut diubah di step plan.
  Plan yang membuat pemakai lain gagal compile adalah plan yang salah.

## 2. Memecah step

- 1 step = 1 sesi Agent Mode = 1 commit user. Maksimal 2 file per step, maksimal 10 step.
- Urutkan supaya tiap commit sebisa mungkin tetap compile. Kalau tidak mungkin (perubahan
  signature + pemakai > 2 file), taruh step-step itu berurutan dan sebut di GOAL.
- Step bergantung ke step lain hanya lewat nama/signature yang ditulis persis di plan.
- Budget ±16k token per step (lihat plan-format.md). `check_plan.py` menghitungnya; kalau lewat,
  pecah.
- Test boleh satu step dengan implementasinya, atau step sendiri, selama budget cukup.
- Dependency baru hanya kalau task benar-benar membutuhkannya: step sendiri untuk file Gradle, dan
  beri tahu user di ringkasan.

## 3. Menulis step

- Bahasa Inggris, kalimat pendek, imperatif.
- `EXECUTOR RULES`: salin `references/executor-rules.md` **verbatim**.
- `GOAL`: konkret. "Make `ValasRepository.rate()` return `RateResult` instead of crashing on null"
  bukan "fix the crash".
- `FILES TO READ`: hanya kalau junior butuh konteks di luar file yang diubah. Pakai rentang baris.
  Sering cukup `- none`.
- `CHANGES`: kode **lengkap dan final**, termasuk import, siap terap. Ikuti style file sekitarnya
  (indentasi, urutan import, penamaan). Anchor SEARCH: ambil 2-5 baris yang pasti unik, salin
  persis dari isi file (perhatikan spasi). Mode edit: lihat plan-format.md.
- `FORBIDDEN`: tulis halusinasi yang paling mungkin untuk step itu, spesifik. Contoh:
  "Do not edit ValasViewModel.kt", "Do not use `?: 0.0` as a fallback", "Do not add MockK".
- `DONE WHEN`: pernyataan yang bisa dicek dengan membaca file. Contoh: "`ValasRepository.kt`
  contains no `!!`", "`RateResult.kt` declares `object Unavailable : RateResult()`".
- Tidak ada: step opsional, step manual user, "if needed", "choose", "TODO", pilihan untuk junior.

## 4. Menulis folder plan

Urutan (supaya bisa di-`resume` kalau sesi putus):

1. `meta` dengan `status=writing`: `repo` = `git rev-parse --show-toplevel`, `base` =
   `git rev-parse HEAD`, `steps` = jumlah step yang direncanakan, `revision=1`, `created`, `task`.
2. `step-1.md` ... `step-N.md`, satu per satu.
3. `README.md` dari `references/plan-readme-template.md`: isi `{{TASK}}`, `{{PLAN_DIR}}` (path
   absolut), `{{STEPS}}`, `{{STEP_LIST}}` (satu baris per step:
   ``N. <judul> — `pbcopy < "<PLAN_DIR>/step-N.md"` ``).
4. `verify.md`: lihat bagian 5.
5. `meta`: `status=ready`.
6. `python3 "<skill-dir>/scripts/check_plan.py" "<folder-plan>"`. Perbaiki sampai PASS.
   WARN near budget: pertimbangkan memecah step.

## 5. `verify.md`

Untuk dirimu sendiri saat `/mandor verify`. Isi:

- Gradle task yang targeted: compile modul yang disentuh (`:<module>:compileDebugKotlin`), unit test
  terkait (`:<module>:testDebugUnitTest --tests "<pattern>"`), lint/detekt kalau project punya.
- Skenario device langkah demi langkah dengan command adb dan hasil yang bisa diamati (teks di
  layar via uiautomator dump, tidak ada `FATAL EXCEPTION` di `logcat -b crash`, screenshot).
- Kontrol positif untuk tiap cek "tidak ada": cara membuktikan ceknya bisa mendeteksi (mis. grep
  teks yang pasti ada di layar yang sama).
- Hal semantik yang harus dibaca manual di diff.

## Resume

1. Tanyakan folder plan. Baca `meta`; harus `status=writing` dan `repo` = repo sekarang.
2. Pastikan `HEAD` masih `base` dan working tree bersih (plan belum dieksekusi).
3. Lihat step yang sudah ada, baca ulang untuk konteks, lanjutkan dari step berikutnya, lalu
   langkah 3-6 bagian 4.
