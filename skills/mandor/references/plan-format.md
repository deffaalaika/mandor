# Format folder plan

Format ini kontrak bersama antara Claude (penulis plan), model lokal (pembaca step), dan script
`check_plan.py` / `check_commits.py` (validator). Ikuti **persis**; script menolak penyimpangan.

## Lokasi

- Folder plan **selalu di luar repo project**. Path ditanyakan ke user setiap kali, tidak ada default.
- Path di dalam repo project ditolak (oleh `check_plan.py` dan oleh aturan skill).

## Isi folder

```
<folder-plan>/
  meta          key=value, dibaca script
  README.md     untuk user (bahasa Indonesia), dari references/plan-readme-template.md
  step-1.md     untuk model lokal (bahasa Inggris), self-contained
  step-2.md
  ...
  verify.md     untuk Claude saat /mandor verify: checklist + skenario device
  history/      arsip revisi: history/rev-<n>/ berisi salinan meta + step-*.md + verify.md lama
```

## `meta`

Satu `key=value` per baris, tanpa kutip. Baris kosong dan baris diawali `#` diabaikan.

| key | isi |
|---|---|
| `repo` | path absolut repo project |
| `base` | SHA lengkap commit dasar (step 1 dibangun di atas commit ini) |
| `steps` | jumlah step (int) |
| `revision` | nomor revisi, mulai `1` |
| `status` | `writing` selama plan ditulis, `ready` setelah lengkap dan `check_plan.py` PASS |
| `created` | `YYYY-MM-DD` |
| `task` | ringkasan task, satu baris |

## `step-N.md`

Nama file `step-<N>.md`, N mulai 1 tanpa lubang. Struktur persis:

```
<!-- mandor step=N -->
# Step N: <judul pendek>

## EXECUTOR RULES
<isi references/executor-rules.md, VERBATIM, tanpa diubah>

## GOAL
<1-2 kalimat: apa yang dicapai step ini dan kenapa>

## FILES TO CHANGE
- CREATE <path> (FULL FILE)
- MODIFY <path> (ANCHOR EDIT)
- MODIFY <path> (FULL FILE)
- DELETE <path>

## FILES TO READ
- <path>:<baris-awal>-<baris-akhir>
(atau satu baris: - none)

## CHANGES
FILE: <path>
<<<<<<< SEARCH
<teks lama, persis, muncul tepat 1x di file>
=======
<teks baru>
>>>>>>> REPLACE

FILE: <path>
<<<<<<< FULL FILE
<isi file utuh>
>>>>>>> END

## FORBIDDEN
- <larangan khusus step ini>

## DONE WHEN
- <kriteria yang bisa dicek model tanpa menjalankan apa pun>
```

Aturan:
- Tujuh section wajib ada, **urutan tetap**: EXECUTOR RULES, GOAL, FILES TO CHANGE, FILES TO READ,
  CHANGES, FORBIDDEN, DONE WHEN. Tidak ada section lain.
- Path relatif terhadap root repo project, tanpa spasi.
- `FILES TO CHANGE`: 1 sampai 2 baris. `CREATE` wajib `(FULL FILE)`. `DELETE` tanpa mode dan tanpa blok.
- `FILES TO READ`: file referensi yang perlu dibaca selain file yang diubah. Sesedikit mungkin,
  dengan rentang baris. Rentang baris mengacu ke isi file **setelah step sebelumnya diterapkan**.
- `CHANGES`: hanya blok `FILE:` + marker. Tidak ada teks bebas di luar blok (baris kosong boleh).
  - `MODIFY ... (ANCHOR EDIT)`: satu atau lebih blok SEARCH/REPLACE untuk file itu, diterapkan berurutan.
    Tiap SEARCH harus muncul **tepat 1x** di isi file saat itu. Ambil cukup baris di sekitar
    supaya unik. Untuk menghapus baris, sertakan baris tetangga di SEARCH dan REPLACE.
  - `MODIFY ... (FULL FILE)` dan `CREATE`: tepat satu blok FULL FILE.
- Isi blok dipertahankan persis. Baris di dalam blok yang diawali `## ` dianggap isi, bukan header.
- Teks SEARCH/REPLACE dicocokkan tanpa newline akhir; isi FULL FILE selalu diakhiri satu newline.

## Memilih mode edit

- File baru → `CREATE (FULL FILE)`.
- File lama yang kecil (ditulis ulang utuh masih muat budget, ingat file dihitung dua kali: dibaca
  dan ditulis) → `MODIFY (FULL FILE)` boleh.
- File lama yang besar → `MODIFY (ANCHOR EDIT)`.
- File besar yang tidak bisa diedit aman dengan anchor → pecah step atau ubah pendekatan. Jangan
  pernah menyuruh model menulis ulang file besar.

## Budget

- Estimasi token = jumlah karakter / 4, dari: isi step-N.md + rentang FILES TO READ + isi saat ini
  tiap file MODIFY (model biasanya membaca file utuh sebelum mengedit).
- Maksimal **16000** (FAIL), peringatan di atas **12000** (WARN). Context model lokal 32k; sisanya
  untuk system prompt Agent Mode, output model, dan cadangan.
- Maksimal **10** step per plan. Lebih dari itu: minta user memecah task.
