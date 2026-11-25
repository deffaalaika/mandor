# Revisi

## Setelah verify gagal

1. **K** = step paling awal yang commit-nya harus berubah (karena junior menyimpang, atau karena
   plan step itu salah/kurang). Step 1..K-1 dipertahankan apa adanya.
2. **Arsip**: salin `meta`, `README.md`, `verify.md`, `step-*.md` ke
   `<folder-plan>/history/rev-<revision lama>/`.
3. **Analisa ulang** mulai dari kondisi setelah step K-1 (`git show <sha step K-1>:<path>`).
   Perbaiki penyebabnya, termasuk celah plan yang ditemukan saat verify.
4. **Tulis ulang** `step-K.md` dan seterusnya (jumlahnya boleh berbeda). Hapus step lama di atas
   jumlah baru. Step 1..K-1 tidak disentuh.
5. **meta**: `base` **tidak berubah**; `steps` = total baru; `revision` + 1; `status=ready`. Update
   `README.md` dan `verify.md`.
6. `python3 "<skill-dir>/scripts/check_plan.py" "<folder-plan>"` sampai PASS.
7. **Beri user command untuk membuang commit step K dan seterusnya**, jangan menjalankannya:
   ```
   git branch mandor-backup-rev<n> HEAD        # opsional, simpan hasil lama
   git reset --hard <sha commit step K-1>     # K=1: pakai base dari meta
   ```
   Peringatkan bahwa `reset --hard` membuang perubahan yang belum di-commit.
8. User mengulang eksekusi mulai step K (sesi Agent Mode baru per step), lalu `/mandor verify`.

## QUESTION dari junior (`/mandor question <N> <teks>`)

Junior berhenti di step N dan belum commit.

1. Tanyakan folder plan. Baca `step-N.md` dan isi `QUESTION`.
2. Cek kondisi repo: `git log --oneline <base>..HEAD` harus berisi N-1 commit. Bandingkan file yang
   disebut junior dengan yang diharapkan plan (`git show HEAD:<path>`).
3. Cari penyebab: anchor salah di plan? Step sebelumnya dieksekusi menyimpang? Instruksi ambigu?
   - Step sebelumnya menyimpang → ini kasus revisi; jalankan `check_commits.py` pada kondisi
     sekarang dan ikuti bagian di atas dengan K = step yang menyimpang.
   - Plan step N (atau setelahnya) yang salah → arsip ke `history/rev-<n>/`, perbaiki step N dan
     step lain yang terdampak, `revision` + 1, `check_plan.py` sampai PASS.
4. Beri tahu user: buang perubahan setengah jadi (`git restore --staged --worktree .` dan hapus file
   baru yang belum di-track, user yang menjalankan), lalu ulangi step N di sesi Agent Mode baru.
