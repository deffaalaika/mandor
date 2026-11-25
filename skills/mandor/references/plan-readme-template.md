# Plan mandor: {{TASK}}

Folder plan: `{{PLAN_DIR}}`
Jumlah step: {{STEPS}}

## Daftar step

{{STEP_LIST}}

## Cara menjalankan tiap step

Ulangi untuk step 1 sampai {{STEPS}}, **berurutan**:

1. Buka **sesi baru** Agent Mode di Android Studio (jangan lanjutkan sesi step sebelumnya).
2. Copy isi step ke clipboard dari terminal:
   ```
   pbcopy < "{{PLAN_DIR}}/step-N.md"
   ```
   (ganti `N` dengan nomor step)
3. Paste ke Agent Mode, kirim.
4. Kalau Agent Mode minta izin menjalankan terminal, Gradle, git, atau adb: **tolak**.
5. Selesai: review sekilas perubahan, lalu **commit manual** (pesan commit bebas). Satu step = satu commit.
   Di commit dialog Android Studio, file baru **tidak dicentang secara default**: centang file baru
   dari step ini, dan jangan ikutkan file `.idea/`. Setelah commit, `git status` harus bersih.
6. Tutup sesi, lanjut ke step berikutnya.

## Kalau model lokal menulis `QUESTION:`

Jangan commit. Buang perubahan setengah jadi kalau ada, lalu di Claude Code jalankan:

```
/mandor question <N> <tempel isi QUESTION-nya>
```

Claude memperbaiki step-nya, lalu ulangi step itu di sesi Agent Mode baru.

## Setelah semua step selesai

Di Claude Code, dari root repo project:

```
/mandor verify
```

## Aturan selama run

- Jangan merge/rebase dari main dan jangan push sampai `/mandor verify` lolos.
- Jangan commit hal lain di branch ini selama run (verify mencocokkan commit ke-N dengan step N).
- Sebelum verify, unload model lokal supaya RAM lega untuk Gradle/emulator: `ollama stop <model>`.
