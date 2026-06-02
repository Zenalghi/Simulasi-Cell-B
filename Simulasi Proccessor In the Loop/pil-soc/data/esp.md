## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| h-charge_rest_60m.cs | 8.3473 | 11.9917 | 7.0921 | 7.8458 | 11.9228 | 4.6808 |
| h-DCC-4.4A-2.5V.csv | 9.6581 | 9.8590 | 9.4946 | 8.5248 | 3.3944 | 1.4086 |
| h-Dynamic_Profiling_ | 9.3166 | 7.9384 | 8.8197 | 6.8120 | 5.0107 | 2.0685 |
| h-charging_7.33A-res | 7.5735 | 8.0381 | 5.8976 | 4.3474 | 8.8626 | 4.5807 |
| h-DCC_4.4A_2.5V-CCV_ | 6.0558 | 10.0302 | 3.7275 | 7.7630 | 7.5327 | 3.4642 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (µs) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.94 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 21.81 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik, Polynomial Orde 1 per segmen)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Auto-detect dari data ZKEtech (bandingkan `V_rest` vs `V_active`)
* **Q Matriks (Process Noise):** `Q_00` = 5.0e-06, `Q_11` = 1.0e-04
* **R Matriks (Measurement Noise Base):** 0.000200 (adaptive: 0.5x rest, 5x discharge, 10x charge)
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.5, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma dimulai dengan *offset error* sebesar 10% untuk menguji kekokohan EKF.