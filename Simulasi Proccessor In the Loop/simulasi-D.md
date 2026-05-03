
## 2. Tabel Hasil Perhitungan RMSE Simulasi-D (PiL ESP32)
Berdasarkan simulasi Processor-in-the-Loop (PiL) di ESP32, sistem algoritma diberikan nilai start awal yang sedikit *meleset* dari State of Charge sebenarnya (mensimulasikan *memory loss* di ESP32). Berikut adalah perbandingan tingkat error (RMSE) antara metode Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| Skenario Pengujian | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) |
| :--- | :---: | :---: | :---: |
| Pengujian Charging (C-CV) | 4.2480% | 4.0863% | 1519.0266 mV |
| Pengujian Discharging (D-CC) | 9.6584% | 7.5484% | 6.8641 mV |
| Pengujian Pembebanan Dinamis (Urban Load) | 9.0987% | 5.3202% | 8.2541 mV |
| Pengujian Mixed (D-CC & C-CV 7.33A) | 0.3607% | 2.0195% | 11.7638 mV |

### Parameter Tuning EKF yang Digunakan (Simulasi D)
* **Q Matriks (Process Noise):**
  * `Q_00` (Noise Arus) : 1.000000e-07
  * `Q_11` (Noise Polarisasi) : 1.000000e-04
* **R Matriks (Measurement Noise):**
  * `R_NOISE` (Tunggal) : 0.005000
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.05, `P[1][1]` = 0.05