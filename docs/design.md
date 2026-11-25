# mandor: desain

Tanggal: 2026-11-24
Pemilik: Deffa Alaika (deffaalaika)

## 1. Intent dan alasan

User adalah Android developer (kantor full Kotlin) dengan MacBook M5 kantor, RAM 16 GB, storage 1 TB.
Aturan kantor: **eksekusi kode (menulis kode ke file) wajib dilakukan model lokal.** Planning dan
verifikasi boleh pakai cloud (Claude Code, langganan Pro). Konfirmasi user: *plan boleh berisi apa
pun, termasuk kode lengkap, asal yang menulis ke file tetap model lokal.*

Model lokal kecil (Gemma 4 12B, context 32k, lewat Ollama/LM Studio di Android Studio Agent Mode)
gampang halu, improvisasi, dan context-nya cepat habis. `mandor` adalah skill Claude Code yang
membuat Claude bertindak sebagai **lead Android engineer sangat berpengalaman yang micromanage
junior (model lokal)**: Claude yang berpikir dan memeriksa, model lokal hanya menerapkan instruksi.

Nama "mandor" = pengawas yang memastikan pekerja bekerja persis sesuai gambar kerja.

Sukses berarti: model lokal bisa menyelesaikan tiap step tanpa menebak, dan verifikasi Claude bisa
membuktikan (bukan mengasumsikan) bahwa hasilnya benar.

## 2. Goals

- Skill Claude Code global `/mandor`, dipanggil manual oleh user, tidak pernah otomatis.
- Fase **plan**: Claude menganalisa codebase (boleh jalankan adb, emulator, Gradle) lalu menulis plan
  yang sangat detail dan dipecah jadi step kecil, masing-masing muat dalam satu sesi model lokal.
- Fase **eksekusi** (di luar Claude): user menjalankan tiap step di sesi Agent Mode baru, lalu commit
  manual. **1 step = 1 sesi Agent Mode = 1 commit.**
- Fase **verifikasi**: Claude memeriksa seluruh rangkaian commit sekaligus di akhir, menjalankan unit
  test, build, dan menguji fitur di emulator/HP via adb, lalu mengeluarkan checklist bukti.
- Fase **revisi**: kalau step K gagal, plan baru ditulis mulai dari step K. Step 1..K-1 dipertahankan.
- Distribusi lewat repo GitHub public `deffaalaika/mandor`, bisa di-install tanpa login GitHub.

## 3. Non-goals

- Tidak memanggil model lokal secara otomatis. Perpindahan sesi selalu manual oleh user.
- Tidak di-install ke project. Skill hidup di `~/.claude/skills/mandor/`.
- Bukan router model, bukan wrapper Aider/CCR.
- Tidak terikat satu model lokal (default asumsi Gemma 4 12B, 32k).
- Tidak memverifikasi per step. Verifikasi sekali di akhir (keputusan user).

## 4. Anti-goals (gagal walaupun "jalan")

- Claude menulis atau mengedit kode project sendiri (melanggar policy kantor).
- Claude commit, push, `git reset`, `git checkout`, atau operasi git yang mengubah state. Itu semua
  tangan user. Ini **meng-override** CLAUDE.md global user yang membolehkan Claude commit.
- Skill terpicu otomatis tanpa `/mandor`.
- Plan yang ambigu sehingga model lokal harus menebak.
- Verifikasi yang percaya laporan model lokal ("done, tests pass") tanpa bukti diff/test/device.
- File apa pun (plan, catatan, config) ditulis ke repo project. Folder plan selalu di luar repo.
- Atribusi AI di commit repo `mandor` (author harus user).

## 5. Alur kerja

### 5.1 `/mandor <cerita task>`: plan

1. Baca cerita task dari user. Kalau ada hal yang hanya user bisa jawab (perilaku yang diharapkan,
   scope), tanya dulu, singkat.
2. Pelajari codebase: struktur modul, konvensi, DI, library test yang sudah dipakai (MockK/Mockito,
   Turbine, coroutines-test, JUnit4/5, Robolectric), style lint/detekt.
3. Boleh menjalankan: `adb` (devices, install, am start, logcat, screencap, uiautomator dump),
   emulator, Gradle (compile, unit test, assemble) untuk reproduce masalah dan memahami kondisi.
   Preferensi device: HP fisik kalau ada di `adb devices`, kalau tidak emulator.
4. Catat SHA `HEAD` sebagai **base commit**. Cek working tree bersih; kalau tidak bersih, beri tahu
   user dan minta dia bereskan (Claude tidak stash/commit).
5. Pecah pekerjaan jadi step. Aturan pemecahan:
   - Budget satu sesi model lokal sekitar **16k token** (setengah dari 32k; sisanya untuk system
     prompt + tools Agent Mode, output model, cadangan). Hitung: step-N.md (termasuk blok aturan) + file yang
     wajib dibaca + kode yang ditulis.
   - Maksimal 1–2 file yang diubah/dibuat per step.
   - Kalau estimasi lewat budget, wajib pecah.
   - Urutan step meminimalkan ketergantungan pada detail implementasi step sebelumnya; ketergantungan
     hanya pada signature/interface yang sudah dikunci di plan.
   - Test bisa jadi step sendiri atau bareng implementasinya, selama masih dalam budget.
6. **Tanya user lokasi folder plan, setiap kali.** Lokasinya bisa beda-beda per task, jadi tidak ada
   default yang diasumsikan. Folder plan **selalu di luar repo project**; kalau user menyebut path
   di dalam repo project, tolak dan minta path lain. Tidak ada file apa pun yang ditulis ke repo
   project.
7. Tulis plan ke folder itu (lihat §6).
8. Tutup dengan ringkasan singkat ke user: jumlah step, judul tiap step, dan command copy per step.

### 5.2 Eksekusi (user + Agent Mode, di luar Claude)

Per step:
1. Buka sesi baru Agent Mode di Android Studio.
2. Di terminal: `pbcopy < <folder-plan>/step-N.md`, lalu paste ke Agent Mode. File step sudah
   self-contained (aturan eksekutor + instruksi step), jadi model lokal tidak perlu membaca file plan
   apa pun, hanya file project yang disebut di step.
3. Model lokal menulis kode. Kalau Agent Mode minta izin menjalankan terminal/Gradle/git, user tolak.
4. User review sekilas, commit manual. **Pesan commit sepenuhnya ditentukan user**; skill tidak
   menyarankan atau mewajibkan format apa pun.
5. Tutup sesi, lanjut step berikutnya.

Kalau model lokal menulis `QUESTION:` (tidak yakin / anchor tidak ketemu), user bawa ke Claude.
Pengaturan untuk kasus ini diserahkan ke builder (lihat §9), tapi tidak boleh membuat Claude menulis
kode project.

### 5.3 `/mandor verify`: verifikasi (sekali di akhir)

Claude bersikap curiga, seperti mereview PR junior. Yang dipercaya hanya diff, hasil test, dan
perilaku di device.

1. **Tanya user lokasi folder plan** (setiap kali, tidak diasumsikan). Baca `meta` di folder itu
   (path repo project, base SHA, jumlah step, revisi). Kalau path repo di `meta` tidak cocok dengan
   repo tempat Claude berjalan, berhenti dan konfirmasi ke user.
2. `git log base..HEAD`: jumlah commit harus = jumlah step; commit ke-N dicocokkan dengan step N
   berdasarkan urutan (pesan commit tidak dipakai untuk pencocokan).
   Working tree harus bersih (kalau ada perubahan belum di-commit, laporkan).
3. Per commit:
   - File yang disentuh ⊆ daftar "boleh disentuh" di step-N.md. File liar = ❌.
   - Isi diff dibandingkan dengan kode yang ditulis di plan. Penyimpangan = ❌ (kecuali formatting
     murni, dilaporkan sebagai catatan).
4. Cek kecurangan global: test dihapus/dilemahkan, assertion hilang, `@Ignore`/`@Disabled`, TODO/
   stub, `!!` baru yang tidak ada di plan, dependency baru di Gradle, import/API yang tidak ada.
5. Jalankan: compile, unit test modul terkait (targeted, bukan full `build`), lint/detekt kalau
   project punya, assemble debug.
6. Install debug ke device, jalankan skenario di `verify.md` (adb input/am start/uiautomator,
   screenshot, logcat untuk crash/exception). Sertakan **kontrol positif** (bukti bahwa cek-nya
   memang bisa mendeteksi masalah).
7. Output di chat: checklist per step (✅/❌ + bukti singkat) dan checklist global.
8. Kalau ada ❌, lanjut ke revisi (§5.4).

### 5.4 Revisi

1. Tentukan step K paling awal yang gagal. Step 1..K-1 dipertahankan.
2. Arsipkan plan lama ke `<folder-plan>/history/rev-<n>/`.
3. Analisa ulang, tulis step-K.md dan seterusnya yang baru (jumlahnya boleh beda dari plan lama).
   Base SHA baru = commit step K-1. Update `meta`.
4. Beri user command git untuk membuang commit step K.. (mis. `git reset --hard <sha step K-1>`),
   dengan peringatan bahwa ini membuang perubahan. **User yang menjalankan**, Claude tidak.
5. User mengulang eksekusi mulai step K, lalu `/mandor verify` lagi.

Push ke remote sebaiknya menunggu verifikasi lolos, dan jangan merge/rebase dari main selama satu
run berjalan (disebutkan di README folder plan). Squash atau tidak setelah verify: keputusan user.

## 6. Format folder plan

Lokasi: **di luar repo project**, path ditentukan user setiap kali (§5.1). Isi instruksi untuk model
lokal ditulis dalam **bahasa Inggris** (lebih patuh dan hemat token untuk model kecil). Bagian untuk
user ditulis **bahasa Indonesia**. Tidak perlu human-readable, kecuali `README.md`.

```
<folder-plan>/
  README.md      (ID) command `pbcopy` per step (path absolut), langkah per sesi, catatan
                 push/rebase (tanpa template pesan commit)
  step-1.md      (EN) self-contained: blok aturan eksekutor + instruksi step 1
  step-2.md
  ...
  verify.md      (EN/ID) checklist dan skenario device untuk Claude saat verify
  meta           path repo project, base SHA, jumlah step, nomor revisi, tanggal, ringkasan task,
                 progres penulisan plan
  history/       arsip revisi
```

- Maksimal sekitar 10 step per plan. Lebih dari itu: minta user memecah task.
- Penulisan plan bisa dilanjutkan lintas sesi Claude: progres dicatat di `meta`, `/mandor` bisa
  melanjutkan plan yang setengah jadi (setelah menanyakan lokasi folder plan).
- Verify mencocokkan commit dengan step **berdasarkan urutan**, bukan teks pesan commit, supaya aman
  terhadap aturan format pesan commit kantor.

### Blok aturan eksekutor (disisipkan di awal tiap step-N.md, minimal)
- Kerjakan HANYA step yang diminta. Baca hanya file yang disebut di step itu.
- Dilarang: git apa pun, Gradle, adb, perintah terminal apa pun.
- Dilarang menyentuh file di luar daftar step.
- Dilarang menambah dependency, menghapus/mengubah test yang sudah ada (kecuali disebut di step),
  `@Ignore`, TODO, stub, refactor di luar instruksi, "perbaikan" yang tidak diminta.
- Terapkan kode di plan **apa adanya**. Jangan "memperbaiki" atau mengganti nama.
- Kalau anchor/kode di plan tidak cocok dengan isi file, atau ragu: **berhenti**, jangan menebak,
  tulis `QUESTION: <apa yang tidak cocok>`.
- Selesai: tulis ringkasan file yang diubah. Jangan mengklaim test lolos (test tidak dijalankan).

### step-N.md (minimal)
- Goal (1–2 kalimat) dan konteks singkat kenapa.
- Files to modify/create (daftar tertutup, path persis).
- Files to read (path + rentang baris), sesedikit mungkin.
- Kode lengkap siap terap. **Mode edit dipilih Claude per file, sesuai situasi** dan ditulis
  eksplisit di step:
  - `FULL FILE`: isi file utuh. Untuk file baru, atau file lama yang kecil sehingga menulis ulang
    utuh masih muat budget (file dihitung dua kali: dibaca + ditulis).
  - `ANCHOR EDIT`: blok edit dengan anchor persis (teks yang dicari, teks pengganti) yang unik di
    file itu. Untuk file lama yang besar.
  - Kalau file besar dan perubahan tidak bisa dibuat aman dengan anchor, pecah step atau ubah
    pendekatan; jangan paksa model menulis ulang file besar.
- README repo `mandor` berisi checklist uji coba singkat Agent Mode (bisa edit parsial dengan
  anchor? patuh ke daftar file?) untuk dijalankan user sekali di laptop kantor.
- Imports persis.
- Untuk test: kode test lengkap, mengikuti library dan pola test yang sudah dipakai project.
- Forbidden (larangan spesifik step ini).
- Done criteria yang bisa dicek model tanpa menjalankan apa pun (mis. "file X berisi fungsi Y dengan
  signature Z").

## 7. Isi repo `mandor`

```
README.md                         (ID) apa ini, install, cara pakai, alur kerja, tips Ollama
get-mandor.sh                     download Release + verifikasi SHA256 + install
install.sh                        copy skill ke ~/.claude/skills/mandor (tidak overwrite tanpa --force, backup)
skills/mandor/SKILL.md            (ID) instruksi untuk Claude
skills/mandor/references/         format step, template rules, prosedur verify, prosedur revisi,
                                  jebakan Android untuk model kecil (Hilt/DI, coroutine/Flow test,
                                  Compose, dll.)
docs/design.md                    dokumen ini
```

- Pola distribusi mengikuti repo `deffaalaika/claude-portable`: zip + `SHA256SUMS` di GitHub Release,
  satu command install, MacBook kantor bisa buka GitHub tapi tidak login.
- `SKILL.md` frontmatter: `name: mandor`, `disable-model-invocation: true`, description, argument hint.
- Skill boleh memanfaatkan skill `android-field-notes` user kalau ter-install, tapi tidak bergantung.
- README menyebut tips: set `num_ctx` ~32k, cek `ollama ps`, unload model sebelum verifikasi berat
  (`ollama stop <model>`) supaya RAM lega untuk Gradle/emulator.

## 8. Constraints

- RAM 16 GB dibagi Android Studio, Gradle, model lokal, emulator. Fase plan/verify berjalan saat model
  lokal tidak dipakai.
- Model lokal: Gemma 4 12B, `num_ctx` 32k. Cadangan: Qwen 3.5 9B, Nemotron E4B. Tidak ada klaim
  benchmark; uji dengan 1–2 task nyata.
- Quota Claude Pro terbatas: verifikasi pakai diff + Gradle task targeted, hindari membaca ulang
  seluruh codebase.
- Data dari device (logcat, screenshot) terkirim ke cloud: README menyarankan debug build + akun test.
- Commit repo `mandor`: author user, **nol atribusi AI**. Identitas yang dipakai di repo public
  sebelumnya: `Deffa Alaika <89124623+deffaalaika@users.noreply.github.com>` (global git config user
  saat ini memakai email kantor; set identitas lokal repo sebelum commit, konfirmasi ke user).
- Commit, pembuatan repo GitHub, push, dan Release hanya atas perintah user.

## 9. Diserahkan ke builder

- Penulisan persis SKILL.md, references, dan template (struktur dan isi detail).
- Cara menangani `QUESTION:` dari model lokal (mis. `/mandor` dengan cerita pertanyaannya → Claude
  memperbaiki step-N.md), selama Claude tidak menulis kode project.
- Format persis `meta` (mis. key=value sederhana).
- Apakah perlu argumen tambahan (mis. `/mandor status`), selama `/mandor <task>` dan
  `/mandor verify` tetap ada.
- Cara estimasi token (heuristik kasar cukup, mis. ~4 karakter per token).
- Cek apakah fitur Claude Code (mis. `allowed-tools` atau hooks di frontmatter skill) bisa membatasi
  Edit/Write hanya ke folder plan selama skill aktif; kalau tidak bisa diandalkan, cukup instruksi.
- Isi detail referensi jebakan Android.
