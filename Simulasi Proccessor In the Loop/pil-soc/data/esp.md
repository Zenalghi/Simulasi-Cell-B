
## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| h-charge_rest_60m.cs | 8.3473 | 8.7712 | 7.0921 | 5.7659 | 17.0718 | 10.5125 |
| h-DCC-4.4A-2.5V.csv | 9.6581 | 6.5390 | 9.4946 | 5.8515 | 4.5867 | 3.1081 |
| h-Dynamic_Profiling_ | 9.3166 | 6.0717 | 8.8197 | 5.3276 | 5.2762 | 3.3323 |
| h-charging_7.33A-res | 7.5671 | 5.6049 | 5.8288 | 3.0732 | 17.2523 | 9.4619 |
| h-DCC_4.4A_2.5V-CCV_ | 5.9570 | 15.8007 | 3.6682 | 12.8474 | 49.4045 | 29.4033 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (µs) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.90 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 251.07 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **Polinomial Orde 6 (OCV-SoC):**
  * `p0` = 2.664967, `p1` = 9.485166, `p2` = -58.074181, `p3` = 169.872070, `p4` = -250.913864, `p5` = 179.845764, `p6` = -49.353786
* **Q Matriks (Process Noise):** `Q_00` = 1e-6, `Q_11` = 1e-4
* **R Matriks (Measurement Noise Base):** 0.000200
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.1, `P[1][1]` = 0.01
* **Simulasi Memory Loss:** Algoritma dimulai dengan *offset error* sebesar 10% untuk menguji kekokohan EKF.