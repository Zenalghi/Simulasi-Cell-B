## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 0% | clean_h-charge_rest_ | 0.0000 | 4.6491 | 0.0000 | 3.3607 | 3.1853 | 1.7681 |
| 0% | clean_h-DCC-4.4A-2.5 | 0.0000 | 4.7883 | 0.0000 | 4.5516 | 1.6559 | 1.1683 |
| 0% | clean_h-Dynamic_Prof | 0.0000 | 5.0222 | 0.0000 | 4.7055 | 2.7071 | 1.2474 |
| 0% | clean_h-charging_7.3 | 0.0000 | 2.8807 | 0.0000 | 1.7418 | 1.9372 | 1.4809 |
| 0% | clean_h-DCC_4.4A_2.5 | 0.0000 | 4.1074 | 0.0000 | 3.5294 | 1.9775 | 1.5123 |
| 5% | clean_h-charge_rest_ | 4.2476 | 4.6493 | 3.6394 | 3.3609 | 5.9020 | 1.8025 |
| 5% | clean_h-DCC-4.4A-2.5 | 4.9145 | 5.1521 | 4.8723 | 4.9213 | 2.2279 | 1.1629 |
| 5% | clean_h-Dynamic_Prof | 4.7350 | 6.0991 | 4.5127 | 5.7061 | 2.3601 | 1.2608 |
| 5% | clean_h-charging_7.3 | 3.8385 | 2.8987 | 3.0500 | 1.7637 | 2.5576 | 1.5395 |
| 5% | clean_h-DCC_4.4A_2.5 | 3.0771 | 4.1074 | 1.9089 | 3.5290 | 3.4996 | 1.5408 |
| 10% | clean_h-charge_rest_ | 8.3473 | 4.6976 | 7.0921 | 3.4267 | 7.2618 | 1.8027 |
| 10% | clean_h-DCC-4.4A-2.5 | 9.6581 | 6.5475 | 9.4946 | 6.2972 | 2.9334 | 1.1215 |
| 10% | clean_h-Dynamic_Prof | 9.3166 | 8.0726 | 8.8197 | 7.5159 | 2.6825 | 1.3163 |
| 10% | clean_h-charging_7.3 | 7.5735 | 2.9321 | 5.8976 | 1.7948 | 2.6390 | 1.5872 |
| 10% | clean_h-DCC_4.4A_2.5 | 6.0558 | 4.1232 | 3.7275 | 3.5595 | 5.5269 | 1.6276 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.89 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 22.50 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 1.0e-05, `Q_11` = 5.0e-03
* **R Matriks (Measurement Noise):** Dynamic Observability R = 0.0001 / (|dOCV/dSOC| + 1e-4)
* **P_init (Initial Error Covariance):** `P[0][0]` = offset^2 + 0.01, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma divariasikan dengan *offset error* sebesar 0%, 5%, dan 10% untuk menguji kekokohan EKF secara komprehensif.