
## Tabel Hasil Perhitungan RMSE Simulasi-B Revisi (PiL ESP32)
Berdasarkan simulasi Processor-in-the-Loop (PiL) di ESP32, sistem algoritma diberikan nilai start awal yang sedikit *meleset* dari State of Charge sebenarnya (mensimulasikan *memory loss* di ESP32). Berikut adalah perbandingan tingkat error (RMSE) antara metode Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| Skenario Pengujian | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) |
| :--- | :---: | :---: | :---: |
| Pengujian Charging (C-CV) | 4.2480% | 10.4760% | 84.0119 mV |
| Pengujian Discharging (D-CC) | 9.6584% | 8.4104% | 3.9139 mV |
| Pengujian Pembebanan Dinamis (Urban Load) | 9.0987% | 5.7077% | 5.4674 mV |
| Pengujian Mixed (D-CC & C-CV 7.33A) | 0.3607% | 6.2522% | 8.4764 mV |

### Parameter Tuning EKF yang Digunakan (Simulasi B Revisi)
* **Q Matriks (Process Noise):**
  * `Q_00` (Noise Arus) : 5.000000e-06
  * `Q_11` (Noise Polarisasi) : 5.000000e-04
* **R Matriks (Measurement Noise):**
  * `R_NOISE` (Tunggal) : 0.010000
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.1, `P[1][1]` = 0.1