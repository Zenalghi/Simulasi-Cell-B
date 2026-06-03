## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 0% | clean_h-charge_rest_ | 0.0000 | 1.3076 | 0.0000 | 0.9558 | 2.7678 | 1.4497 |
| 0% | clean_h-DCC-4.4A-2.5 | 0.0000 | 1.8255 | 0.0000 | 1.7879 | 1.5867 | 1.1071 |
| 0% | clean_h-Dynamic_Prof | 0.0000 | 2.7029 | 0.0000 | 2.5798 | 2.6146 | 1.1303 |
| 0% | clean_h-charging_7.3 | 0.0000 | 0.7247 | 0.0000 | 0.4730 | 1.6571 | 1.2495 |
| 0% | clean_h-DCC_4.4A_2.5 | 0.0000 | 1.0811 | 0.0000 | 0.9240 | 1.7080 | 1.3123 |
| 5% | clean_h-charge_rest_ | 4.2476 | 1.3054 | 3.6394 | 0.9535 | 5.8361 | 1.4930 |
| 5% | clean_h-DCC-4.4A-2.5 | 4.9145 | 2.0034 | 4.8723 | 1.9689 | 2.1697 | 1.1185 |
| 5% | clean_h-Dynamic_Prof | 4.7350 | 5.3392 | 4.5127 | 5.0791 | 2.5857 | 1.2373 |
| 5% | clean_h-charging_7.3 | 3.8385 | 0.6918 | 3.0500 | 0.4615 | 4.5283 | 1.3071 |
| 5% | clean_h-DCC_4.4A_2.5 | 3.0771 | 1.0821 | 1.9089 | 0.9273 | 3.2674 | 1.3356 |
| 10% | clean_h-charge_rest_ | 8.3473 | 1.3017 | 7.0921 | 0.9495 | 7.4192 | 1.5179 |
| 10% | clean_h-DCC-4.4A-2.5 | 9.6581 | 2.1598 | 9.4946 | 2.1273 | 2.8096 | 1.1266 |
| 10% | clean_h-Dynamic_Prof | 9.3166 | 5.0714 | 8.8197 | 4.8259 | 2.9039 | 1.2384 |
| 10% | clean_h-charging_7.3 | 7.5735 | 33.7356 | 5.8976 | 24.2821 | 51.4414 | 21.8024 |
| 10% | clean_h-DCC_4.4A_2.5 | 6.0558 | 1.0844 | 3.7275 | 0.9249 | 4.3309 | 1.3516 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.96 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 26.61 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 2.0e-06, `Q_11` = 1.0e-01
* **R Matriks (Measurement Noise):** Dynamic Observability R = 0.0001 / (|dOCV/dSOC| + 1e-4) | R_REST = 0.0001 (aktif setelah 30s arus ~0)
* **Jacobian h0:** dOCV/dSOC + 1e-4 (no hard floor — prevents Kalman gain over-clamping in LiFePO4 flat region)
* **Soft Deadband:** 3 mV threshold (diperkecil dari 8 mV untuk menekan voltage error akumulasi)
* **P_init (Initial Error Covariance):** `P[0][0]` = offset^2 + 0.01, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma divariasikan dengan *offset error* sebesar 0%, 5%, dan 10% untuk menguji kekokohan EKF secara komprehensif.
