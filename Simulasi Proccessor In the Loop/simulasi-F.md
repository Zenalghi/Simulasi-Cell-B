
## Tabel Hasil Perhitungan RMSE Simulasi-F (PiL ESP32)
Berdasarkan simulasi Processor-in-the-Loop (PiL) di ESP32, sistem algoritma diberikan nilai start awal yang sedikit *meleset* dari State of Charge sebenarnya (mensimulasikan *memory loss* di ESP32). Berikut adalah perbandingan tingkat error (RMSE) antara metode Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| Skenario Pengujian | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) |
| :--- | :---: | :---: | :---: |
| Pengujian Charging (C-CV) | 4.2480% | 1.5561% | 17.6450 mV |
| Pengujian Discharging (D-CC) | 9.6584% | 4.7076% | 4.6884 mV |
| Pengujian Pembebanan Dinamis (Urban Load) | 9.0987% | 2.1507% | 5.7418 mV |
| Pengujian Mixed (D-CC & C-CV 7.33A) | 0.3607% | 0.6218% | 16.4336 mV |

### Parameter Tuning EKF yang Digunakan (Simulasi F - Optimasi Final)
* **Q Matriks (Process Noise):**
  * `Q_00` (Noise Arus) : 1.000000e-07
  * `Q_11` (Noise Polarisasi) : 5.000000e-04
* **R Matriks (Measurement Noise - Adaptive):**
  * `R_CHARGE` (Skeptis saat CV) : 0.060000
  * `R_DISCHARGE` (Tajam saat kuras) : 0.005000
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.1, `P[1][1]` = 0.01