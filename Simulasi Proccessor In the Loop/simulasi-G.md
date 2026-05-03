
## Tabel Hasil Perhitungan RMSE Simulasi-G (PiL ESP32)
Berdasarkan simulasi Processor-in-the-Loop (PiL) di ESP32, sistem algoritma diberikan nilai start awal yang sedikit *meleset* dari State of Charge sebenarnya (mensimulasikan *memory loss* di ESP32). Berikut adalah perbandingan tingkat error (RMSE) antara metode Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| Skenario Pengujian | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) |
| :--- | :---: | :---: | :---: |
| Pengujian Charging (C-CV) | 4.2480% | 1.6141% | 16.0142 mV |
| Pengujian Discharging (D-CC) | 9.6584% | 4.6236% | 4.4116 mV |
| Pengujian Pembebanan Dinamis (Urban Load) | 9.0987% | 1.8007% | 5.1418 mV |
| Pengujian Mixed (D-CC & C-CV 7.33A) | 0.3607% | 0.6548% | 13.1502 mV |

### Parameter Tuning EKF yang Digunakan (Simulasi G - Tiga State)
* **Q Matriks (Process Noise):**
  * `Q_00` (Noise Arus) : 1.000000e-07
  * `Q_11` (Noise Polarisasi) : 5.000000e-04
* **R Matriks (Measurement Noise - Adaptive):**
  * `R_CHARGE` (Skeptis saat CV) : 0.035000
  * `R_DISCHARGE` (Tajam saat kuras) : 0.004000
  * `R_REST` (Sangat tajam saat OCV) : 0.000800
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.1, `P[1][1]` = 0.01