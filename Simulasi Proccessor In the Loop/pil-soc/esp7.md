
## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
### Menggunakan Offset error 10%
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| clean_h-charge_rest_ | 8.3473 | 9.1827 | 7.0921 | 7.3393 | 9.4998 | 3.5564 |
| clean_h-DCC-4.4A-2.5 | 9.6581 | 9.9264 | 9.4946 | 9.2625 | 3.4536 | 1.3899 |
| clean_h-Dynamic_Prof | 9.3166 | 9.1721 | 8.8197 | 8.4046 | 7.5790 | 3.7865 |
| clean_h-charging_7.3 | 7.5735 | 7.3455 | 5.8976 | 5.4207 | 39.3671 | 18.0936 |
| clean_h-DCC_4.4A_2.5 | 6.0558 | 6.7906 | 3.7275 | 5.5058 | 21.6733 | 5.7060 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.89 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 24.25 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 1.0e-06, `Q_11` = 1.0e-04
* **R Matriks (Measurement Noise):** Dynamic Observability R = 0.0001 / (|dOCV/dSOC| + 1e-4)
* **P_init (Initial Error Covariance):** `P[0][0]` = 1.0, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma dimulai dengan *offset error* sebesar 10% untuk menguji kekokohan EKF.