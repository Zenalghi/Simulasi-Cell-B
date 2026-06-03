## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 0% | clean_h-charge_rest_ | 0.0000 | 57.6587 | 0.0000 | 47.7237 | 68.6786 | 46.8158 |
| 0% | clean_h-DCC-4.4A-2.5 | 0.0000 | 11.1590 | 0.0000 | 10.0491 | 52.1375 | 19.5054 |
| 0% | clean_h-Dynamic_Prof | 0.0000 | 8.2245 | 0.0000 | 7.1654 | 37.4934 | 11.6422 |
| 0% | clean_h-charging_7.3 | 0.0000 | 7.0388 | 0.0000 | 3.7413 | 15.8091 | 9.3035 |
| 0% | clean_h-DCC_4.4A_2.5 | 0.0000 | 10.1032 | 0.0000 | 8.0782 | 39.7437 | 16.1873 |

### Diagnostik Internal EKF (Per-Dataset)
| NAMA DATASET | Avg |K[0]| | Avg R_dyn | Avg |h0| | Interpretasi |
| :--- | :---: | :---: | :---: | :--- |
| clean_h-charge_rest_ | 0.029416 | 0.019182 | 0.4538 | Gain seimbang |
| clean_h-DCC-4.4A-2.5 | 0.013123 | 0.024322 | 0.2075 | Gain seimbang |
| clean_h-Dynamic_Prof | 0.077539 | 0.016973 | 0.8389 | Gain seimbang |
| clean_h-charging_7.3 | 0.084476 | 0.010908 | 2.7501 | Gain seimbang |
| clean_h-DCC_4.4A_2.5 | 0.018849 | 0.021540 | 0.9124 | Gain seimbang |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.89 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 23.38 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 5.0e-06, `Q_11` = 1.0e-04
* **R Matriks (Measurement Noise):** Normalized Trust Factor: R_STEEP=0.0005, R_FLAT=0.0250, R_REST=0.0002
* **Rest Settling Time:** 30 s sebelum R_REST aktif
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.02, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma dimulai dengan *offset error* sebesar 10% untuk menguji kekokohan EKF.