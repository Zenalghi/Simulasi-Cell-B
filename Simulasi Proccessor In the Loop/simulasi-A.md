
## Tabel Hasil Perhitungan RMSE Simulasi-A (PiL ESP32)
Berdasarkan simulasi Processor-in-the-Loop (PiL) di ESP32, sistem algoritma diberikan nilai start awal yang sedikit *meleset* dari State of Charge sebenarnya (mensimulasikan *memory loss* di ESP32). Berikut adalah perbandingan tingkat error (RMSE) antara metode Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| Skenario Pengujian | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) |
| :--- | :---: | :---: | :---: |
| Pengujian Charging (C-CV) | 4.2480% | 4.1856% | 40.3814 mV |
| Pengujian Discharging (D-CC) | 9.6584% | 6.8542% | 20.1105 mV |
| Pengujian Pembebanan Dinamis (Urban Load) | 9.0987% | 5.6364% | 27.8182 mV |
| Pengujian Mixed (D-CC & C-CV 7.33A) | 0.3607% | 1.9973% | 41.7878 mV |

### Parameter Tuning EKF yang Digunakan (Simulasi A)
* **Q Matriks (Process Noise):**
  * `Q_00` (Noise Arus) : 1.000000e-07
  * `Q_11` (Noise Polarisasi) : 1.000000e-05
* **R Matriks (Measurement Noise):**
  * `R_NOISE` (Tunggal) : 0.050000
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.01, `P[1][1]` = 0.01