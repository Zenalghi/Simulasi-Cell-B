## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 0% | clean_h-charge_rest_ | 0.0000 | 4.4295 | 0.0000 | 3.2274 | 2.9390 | 1.5590 |
| 0% | clean_h-DCC-4.4A-2.5 | 0.0000 | 4.7029 | 0.0000 | 4.4770 | 1.5902 | 1.0525 |
| 0% | clean_h-Dynamic_Prof | 0.0000 | 3.9836 | 0.0000 | 3.7235 | 2.6651 | 1.1889 |
| 0% | clean_h-charging_7.3 | 0.0000 | 2.7649 | 0.0000 | 1.6885 | 1.8019 | 1.3558 |
| 0% | clean_h-DCC_4.4A_2.5 | 0.0000 | 4.0148 | 0.0000 | 3.4603 | 1.8518 | 1.3510 |
| 5% | clean_h-charge_rest_ | 4.2476 | 4.4333 | 3.6394 | 3.2324 | 5.6696 | 1.5807 |
| 5% | clean_h-DCC-4.4A-2.5 | 4.9145 | 5.8608 | 4.8723 | 5.6325 | 2.1442 | 1.0138 |
| 5% | clean_h-Dynamic_Prof | 4.7350 | 6.1241 | 4.5127 | 5.7280 | 2.3500 | 1.2109 |
| 5% | clean_h-charging_7.3 | 3.8385 | 2.7924 | 3.0500 | 1.7202 | 2.3093 | 1.4242 |
| 5% | clean_h-DCC_4.4A_2.5 | 3.0771 | 4.0149 | 1.9089 | 3.4593 | 3.6784 | 1.3929 |
| 10% | clean_h-charge_rest_ | 8.3473 | 4.6995 | 7.0921 | 3.5641 | 7.4968 | 1.6456 |
| 10% | clean_h-DCC-4.4A-2.5 | 9.6581 | 8.2082 | 9.4946 | 7.8931 | 2.8280 | 1.0191 |
| 10% | clean_h-Dynamic_Prof | 9.3166 | 9.0260 | 8.8197 | 8.3815 | 2.7209 | 1.3199 |
| 10% | clean_h-charging_7.3 | 7.5735 | 2.8454 | 5.8976 | 1.7607 | 2.5929 | 1.4872 |
| 10% | clean_h-DCC_4.4A_2.5 | 6.0558 | 4.0428 | 3.7275 | 3.5091 | 4.7176 | 1.4732 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.89 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 26.23 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 1.0e-05, `Q_11` = 5.0e-03
* **R Matriks (Measurement Noise):** Dynamic Observability R = 0.0001 / (|dOCV/dSOC| + 1e-4)
* **P_init (Initial Error Covariance):** `P[0][0]` = offset^2 + 0.01, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma divariasikan dengan *offset error* sebesar 0%, 5%, dan 10% untuk menguji kekokohan EKF secara komprehensif.