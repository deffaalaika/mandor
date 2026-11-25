# Jebakan Android untuk model kecil

Tempat model 9-12B paling sering menebak salah, dan apa yang harus ditulis plan supaya tidak ada
yang perlu ditebak. Semua ini panduan; konvensi project yang terlihat di kode selalu menang.

| Area | Yang sering salah | Yang ditulis di plan |
|---|---|---|
| Import | Import ditebak (`androidx.lifecycle.viewmodel.compose` vs `androidx.lifecycle.viewModelScope`, `org.junit.Assert` vs `kotlin.test`) | Daftar import lengkap di blok kode |
| Null-safety | Menambah `!!`, atau fallback diam-diam (`?: 0.0`, `?: ""`) yang menyembunyikan error | Penanganan null eksplisit di kode plan; FORBIDDEN menyebut fallback yang dilarang |
| Hilt/DI | Lupa `@Inject constructor`, binding di module yang salah, `@HiltViewModel` tanpa `@Inject` | Kode lengkap anotasi + module binding; sebut file module-nya |
| Coroutines test | `runBlocking` alih-alih `runTest`, lupa `Dispatchers.setMain` untuk `viewModelScope`, `advanceUntilIdle` | Ikuti pola test coroutine yang sudah ada di project; tulis test lengkap |
| Flow | Assert `StateFlow` sebelum emit, salah pakai Turbine (`test { awaitItem() }`) | Kode test lengkap; Turbine hanya kalau project sudah memakainya |
| Compose | State hoisting asal, `remember` vs `rememberSaveable`, modifier order, preview rusak | Composable lengkap; jangan minta junior mendesain UI |
| Resource | String hardcode alih-alih `strings.xml`, ID resource ditebak | Tambahkan entry `strings.xml` sebagai perubahan eksplisit (ANCHOR EDIT), sebut nama resource persis |
| Signature publik | Ubah signature tanpa mengubah pemakai; default param di interface Kotlin yang dipanggil Java/biner lain | Semua pemakai ada di step; hindari default param di API yang dikonsumsi modul lain |
| Gradle | Menambah dependency "biar jalan", ubah versi | Larang di FORBIDDEN kecuali step itu memang mengubah Gradle |
| Test lama | Melemahkan/menghapus assertion supaya cocok | Test lama yang harus berubah ditulis ulang lengkap di plan |
| File besar | Menulis ulang file utuh dan diam-diam menghapus bagian lain | ANCHOR EDIT untuk file besar; FULL FILE hanya untuk file kecil/baru |
