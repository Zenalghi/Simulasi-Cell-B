# Eksperimen Perbandingan Akurasi SOC
## JK BMS (Vendor) vs Extended Kalman Filter (EKF)

Panduan ini berisi cara melakukan eksperimen, logging data nyata dari baterai 8S LiFePO4, me-replay algoritma EKF, dan memvisualisasikan hasilnya.

---

## 📁 Struktur Folder & File

```text
soc_experiment/
├── mqtt_logger.py       → Script untuk membaca data via MQTT dan menyimpan ke file CSV.
├── ekf_replayer.py      → Script untuk menghitung SOC EKF, mencari error (RMSE/MAE) vs JK BMS.
├── plot_v_a.py          → Script untuk memvisualisasikan Tegangan (V) & Arus (A) ke grafik.
├── requirements.txt     → Dependensi Python (paho-mqtt, matplotlib).
├── README.md            → Panduan ini.
└── data_logs/           → Folder tempat semua output data disimpan.
    ├── bms_session_YYYYMMDD_HHMMSS.csv           → Data mentah (V, I, T, SOC JK, cell voltage).
    ├── result_YYYYMMDD_HHMMSS.csv                → Hasil perhitungan EKF per sampel.
    ├── result_YYYYMMDD_HHMMSS.png                → Grafik 4-panel perbandingan SOC & Error.
    ├── summary_YYYYMMDD_HHMMSS.txt               → Teks ringkasan metrik akurasi (RMSE & MAE).
    └── bms_session_YYYYMMDD_HHMMSS_plot_v_a.png  → Grafik tegangan dan arus.
```

---

## 🚀 Penjelasan Script Python

### 1. `mqtt_logger.py` (Data Logger)
Script ini berfungsi untuk melakukan _subscribe_ ke broker MQTT (yang dikirim oleh ESP32) dan mencatat semua parameter penting seperti Tegangan Pack, Arus, Tegangan tiap sel, Temperatur, dan SOC bawaan JK BMS secara *real-time* (~1 detik per sampel).
*   **Cara Pakai**: `python mqtt_logger.py`
*   **Output**: File CSV baru di dalam folder `data_logs/` bernama `bms_session_<timestamp>.csv`.

### 2. `ekf_replayer.py` (EKF Replay & Analisis)
Script ini adalah **inti dari pembuktian**. Script ini akan:
1. Membaca data log CSV.
2. Mendeteksi otomatis SOC sebenarnya di awal berdasarkan **OCV (Open Circuit Voltage)** pada saat arus 0 (fase rest).
3. Menjalankan ulang (replay) algoritma **Extended Kalman Filter (EKF)** (sama persis dengan yang ada di ESP32/C++).
4. Menggunakan Coulomb Counting (CC) sebagai referensi pembanding.
5. Menghitung **RMSE** dan **MAE** antara EKF vs JK BMS.
*   **Cara Pakai**: `python ekf_replayer.py data_logs/bms_session_20260710_144650.csv`
*   **Output**: 
    - File hasil detail `result_<timestamp>.csv`
    - Teks ringkasan `summary_<timestamp>.txt`
    - Grafik lengkap `result_<timestamp>.png`

### 3. `plot_v_a.py` (Visualisasi Data Mentah)
Script pembantu untuk membuat grafik khusus pergerakan Tegangan Pack (warna biru) dan Arus (warna merah) terhadap waktu dari file log data mentah CSV. Cocok untuk ditaruh di lampiran laporan.
*   **Cara Pakai**: `python plot_v_a.py data_logs/bms_session_20260710_144650.csv`
*   **Output**: File gambar `..._plot_v_a.png` di dalam folder `data_logs/`.

---

## 🛠️ Langkah-Langkah Menjalankan Eksperimen

### 1. Persiapan Software
Pastikan dependensi python terinstal:
```bash
pip install -r requirements.txt
```

### 2. Pastikan Jaringan MQTT Tersambung
Jika ESP32 terhubung melalui *hotspot* laptop Windows (sementara broker ada di VM Linux atau laptop), pastikan *port forwarding* aktif. Jalankan ini di **PowerShell Administrator**:
```powershell
netsh interface portproxy add v4tov4 listenaddress=192.168.137.1 listenport=1883 connectaddress=192.168.230.131 connectport=1883
netsh advfirewall firewall add rule name="MQTT_1883_IN" dir=in action=allow protocol=TCP localport=1883
```

### 3. Mulai Merekam Data (Fase Eksperimen)
1. Colok Power Supply / Beban ke baterai. **Biarkan arus 0 Ampere (Fase Rest) selama ~30 detik di awal** agar script analisis nanti bisa membaca OCV dengan tepat.
2. Jalankan logger:
```bash
python mqtt_logger.py
```
3. Nyalakan beban/charger. Tunggu sampai kapasitas yang diinginkan.
4. Tekan `Ctrl+C` untuk berhenti. File CSV akan tersimpan otomatis di folder `data_logs/`.

### 4. Analisis & Visualisasi
Setelah selesai, proses data tersebut:

Bandingkan EKF dan buat grafik akurasi:
```bash
python ekf_replayer.py data_logs/bms_session_YYYYMMDD_HHMMSS.csv
```

Buat plot Tegangan dan Arus:
```bash
python plot_v_a.py data_logs/bms_session_YYYYMMDD_HHMMSS.csv
```

Semua hasil, baik CSV perhitungan maupun file grafik (`.png`), otomatis tersimpan berjejer rapi di folder `data_logs/`.

---

## 📝 Catatan Metodologi untuk Skripsi

*   **Pembuktian Kesalahan Vendor (t=0)**: Pada data eksperimen, JK BMS terbukti mengalami *offset* SOC sejak awal pengukuran karena BMS komersial seringkali tidak mampu mengukur SOC berbasis OCV secara akurat (atau hanya reset ketika 100% / 0%). Pada log `144650`, OCV menunjukkan 14.6% namun JK BMS mengklaim 30%.
*   **Kenapa Coulomb Counting (CC) digunakan sebagai Referensi?**: 
    Coulomb Counting diterapkan pada data pembacaan arus real-time (diasumsikan sensor JK cukup baik untuk arus relatif). Baik performa EKF maupun JK BMS diukur deviasinya terhadap CC.
*   **Kemenangan EKF**: Algoritma EKF secara konsisten menghasilkan RMSE dan MAE yang jauh lebih rendah berkat fungsi `Measurement Update` yang menggunakan kalibrasi kurva tegangan (*OCV-SOC curve*), sehingga mengeliminasi akumulasi *error* yang terjadi pada metode milik JK BMS.
