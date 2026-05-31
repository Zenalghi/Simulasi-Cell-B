<!-- COPY MULAI DARI BAWAH INI -->
## Tabel Hasil Perhitungan RMSE (PiL ESP32) dengan Polinomial Orde 6
Berikut adalah perbandingan tingkat error (RMSE) antara metode Coulomb Counting (CC) dan Extended Kalman Filter (EKF) menggunakan pemodelan fungsi OCV berbasis polinomial orde 6:

| NAMA DATASET | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) | Beban CPU/Iterasi (us) | Penggunaan Memori (Bytes) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| h-charge_rest_60m.cs | 8.3473% | 8.7712% | 17.0718 mV | 236.15 | 51284 |
| h-DCC-4.4A-2.5V.csv | 9.6581% | 6.5390% | 4.5867 mV | 305.27 | 51548 |
| h-Dynamic_Profiling_ | 9.3166% | 6.0717% | 5.2762 mV | 283.84 | 51628 |
| h-charging_7.33A-res | 7.5671% | 5.6049% | 17.2523 mV | 222.84 | 51652 |
| h-DCC_4.4A_2.5V-CCV_ | 5.9570% | 15.8007% | 49.4045 mV | 278.45 | 51768 |

### Parameter Model & Tuning EKF yang Digunakan:
* **Polinomial Orde 6 (OCV-SoC):**
  * `p0` = 2.664967, `p1` = 9.485166, `p2` = -58.074181, `p3` = 169.872070, `p4` = -250.913864, `p5` = 179.845764, `p6` = -49.353786
* **Q Matriks (Process Noise):**
  * `Q_00` (Noise Arus) : 1.000000e-06
  * `Q_11` (Noise Polarisasi) : 1.000000e-04
* **R Matriks (Measurement Noise Base):**
  * `R_NOISE_BASE` : 0.000200
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.1, `P[1][1]` = 0.01
* **Simulasi Memory Loss:** Algoritma dimulai dengan *offset error* sebesar 10% untuk menguji kekokohan EKF.
<!-- COPY SAMPAI SINI -->