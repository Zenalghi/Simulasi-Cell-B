
# Hasil Pengujian PiL ESP32 (Hardware-in-the-Loop)

## 1. Tabel Hasil Perhitungan RMSE
| Skenario Pengujian | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) |
| :--- | :---: | :---: | :---: |
| h-charge_rest_60m.cs | 4.2480% | 2.5170% | 21.1743 mV |
| h-DCC-4.4A-2.5V.csv | 9.6584% | 5.6141% | 6.8272 mV |
| h-Dynamic_Profiling_ | 9.0987% | 2.7081% | 8.3288 mV |
| h-charging_7.33A-res | 0.3607% | 1.0776% | 19.9291 mV |

## 2. Parameter Tuning EKF yang Digunakan
* **Q Matriks (Process Noise):**
  * `Q_00` (Noise Arus) : 1.000000e-07
  * `Q_11` (Noise Polarisasi) : 2.000000e-04
* **R Matriks (Measurement Noise - Adaptive):**
  * `R_CHARGE` (Skeptis saat CV) : 0.040000
  * `R_DISCHARGE` (Tajam saat kuras) : 0.008000
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.1, `P[1][1]` = 0.01