## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 0% | clean_h-charge_rest_ | 0.0000 | 0.0005 | 0.0000 | 0.0005 | 2.5748 | 1.5718 |
| 0% | clean_h-DCC-4.4A-2.5 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.7953 | 1.2258 |
| 0% | clean_h-Dynamic_Prof | 0.0000 | 0.0007 | 0.0000 | 0.0002 | 2.8654 | 1.3005 |
| 0% | clean_h-charging_7.3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 2.1937 | 1.6149 |
| 0% | clean_h-DCC_4.4A_2.5 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 2.1392 | 1.5265 |
| 5% | clean_h-charge_rest_ | 4.2476 | 4.2464 | 3.6394 | 3.6384 | 5.8234 | 1.8192 |
| 5% | clean_h-DCC-4.4A-2.5 | 4.9145 | 4.9144 | 4.8723 | 4.8721 | 5.2096 | 2.1308 |
| 5% | clean_h-Dynamic_Prof | 4.7350 | 4.7321 | 4.5127 | 4.5097 | 4.3555 | 1.8509 |
| 5% | clean_h-charging_7.3 | 3.8385 | 3.8385 | 3.0500 | 3.0500 | 4.6543 | 3.0343 |
| 5% | clean_h-DCC_4.4A_2.5 | 3.0771 | 3.0768 | 1.9089 | 1.9087 | 4.1745 | 1.9395 |
| 10% | clean_h-charge_rest_ | 8.3473 | 8.2980 | 7.0921 | 7.0510 | 9.9082 | 2.3985 |
| 10% | clean_h-DCC-4.4A-2.5 | 9.6581 | 9.6580 | 9.4946 | 9.4945 | 8.1027 | 3.3656 |
| 10% | clean_h-Dynamic_Prof | 9.3166 | 9.3162 | 8.8197 | 8.8191 | 7.0880 | 3.0888 |
| 10% | clean_h-charging_7.3 | 7.5735 | 5.4432 | 5.8976 | 4.2643 | 10.7102 | 4.5049 |
| 10% | clean_h-DCC_4.4A_2.5 | 6.0558 | 4.1921 | 3.7275 | 2.5890 | 14.7523 | 3.5701 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.90 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 31.78 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 1.0e-06, `Q_11` = 1.0e-01
* **R Matriks (Measurement Noise):** Dynamic Observability R = 0.0001 / (|dOCV/dSOC| + 1e-4)
* **P_init (Initial Error Covariance):** `P[0][0]` = 1.0, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma divariasikan dengan *offset error* sebesar 0%, 5%, dan 10% untuk menguji kekokohan EKF secara komprehensif.