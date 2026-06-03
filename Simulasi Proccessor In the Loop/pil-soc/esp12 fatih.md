## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 0% | clean_h-charge_rest_ | 0.0000 | 0.6526 | 0.0000 | 0.4966 | 2.6673 | 1.4365 |
| 0% | clean_h-DCC-4.4A-2.5 | 0.0000 | 1.4184 | 0.0000 | 1.4071 | 1.5243 | 1.0885 |
| 0% | clean_h-Dynamic_Prof | 0.0000 | 2.0258 | 0.0000 | 1.9400 | 2.5436 | 1.0980 |
| 0% | clean_h-charging_7.3 | 0.0000 | 0.4015 | 0.0000 | 0.2841 | 1.6878 | 1.2809 |
| 0% | clean_h-DCC_4.4A_2.5 | 0.0000 | 0.5944 | 0.0000 | 0.5000 | 1.6727 | 1.3021 |
| 5% | clean_h-charge_rest_ | 4.2476 | 0.8293 | 3.6394 | 0.6677 | 5.5802 | 1.4543 |
| 5% | clean_h-DCC-4.4A-2.5 | 4.9145 | 4.4153 | 4.8723 | 4.3784 | 2.4072 | 1.1431 |
| 5% | clean_h-Dynamic_Prof | 4.7350 | 5.2821 | 4.5127 | 5.0276 | 2.6113 | 1.2451 |
| 5% | clean_h-charging_7.3 | 3.8385 | 1.4985 | 3.0500 | 1.2042 | 2.5647 | 1.7051 |
| 5% | clean_h-DCC_4.4A_2.5 | 3.0771 | 1.0301 | 1.9089 | 0.9413 | 3.4292 | 1.3999 |
| 10% | clean_h-charge_rest_ | 8.3473 | 2.9011 | 7.0921 | 2.4867 | 7.8191 | 1.5729 |
| 10% | clean_h-DCC-4.4A-2.5 | 9.6581 | 8.1916 | 9.4946 | 8.0715 | 3.5319 | 1.4015 |
| 10% | clean_h-Dynamic_Prof | 9.3166 | 9.0616 | 8.8197 | 8.5773 | 3.5334 | 1.6462 |
| 10% | clean_h-charging_7.3 | 7.5735 | 15.7349 | 5.8976 | 11.9218 | 28.2204 | 10.8218 |
| 10% | clean_h-DCC_4.4A_2.5 | 6.0558 | 2.3912 | 3.7275 | 1.8486 | 4.9317 | 1.6699 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.96 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 24.90 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 1.0e-06, `Q_11` = 1.0e-01
* **R Matriks (Measurement Noise):** Dynamic Observability R = 0.0001 / (|dOCV/dSOC| + 1e-4) | R_REST = 0.0001 (aktif setelah 30s arus ~0)
* **Jacobian h0:** dOCV/dSOC + 1e-4 (no hard floor — prevents Kalman gain over-clamping in LiFePO4 flat region)
* **Soft Deadband:** 3 mV threshold (diperkecil dari 8 mV untuk menekan voltage error akumulasi)
* **P_init (Initial Error Covariance):** `P[0][0]` = offset^2 + 0.01, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma divariasikan dengan *offset error* sebesar 0%, 5%, dan 10% untuk menguji kekokohan EKF secara komprehensif.