## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| clean_h-charge_rest_ | 0.0000 | 2.8633 | 0.0000 | 2.2260 | 5.1999 | 3.1106 |
| clean_h-DCC-4.4A-2.5 | 0.0000 | 3.7057 | 0.0000 | 3.5581 | 1.5006 | 1.0830 |
| clean_h-Dynamic_Prof | 0.0000 | 3.5124 | 0.0000 | 3.2375 | 5.1443 | 2.7131 |
| clean_h-charging_7.3 | 0.0000 | 2.2413 | 0.0000 | 1.5520 | 4.4755 | 2.6968 |
| clean_h-DCC_4.4A_2.5 | 0.0000 | 3.3585 | 0.0000 | 2.9642 | 4.3625 | 2.3177 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.90 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 28.26 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 1.0e-06, `Q_11` = 1.0e-04
* **R Matriks (Measurement Noise):** Dynamic Observability R = 0.0001 / (|dOCV/dSOC| + 1e-4)
* **P_init (Initial Error Covariance):** `P[0][0]` = 1.0, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma dimulai dengan *offset error* sebesar 10% untuk menguji kekokohan EKF.