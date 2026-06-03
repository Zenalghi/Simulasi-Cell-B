## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 0% | clean_h-charge_rest_ | 0.0000 | 57.7165 | 0.0000 | 48.1195 | 68.5354 | 46.3559 |
| 0% | clean_h-DCC-4.4A-2.5 | 0.0000 | 11.4655 | 0.0000 | 10.2231 | 52.1029 | 19.2999 |
| 0% | clean_h-Dynamic_Prof | 0.0000 | 8.9261 | 0.0000 | 7.7230 | 37.4211 | 11.5110 |
| 0% | clean_h-charging_7.3 | 0.0000 | 7.0505 | 0.0000 | 3.7676 | 15.7896 | 9.1240 |
| 0% | clean_h-DCC_4.4A_2.5 | 0.0000 | 10.2887 | 0.0000 | 8.1813 | 39.7117 | 16.0413 |
| 5% | clean_h-charge_rest_ | 4.2476 | 57.7165 | 3.6394 | 48.1196 | 68.7083 | 46.3829 |
| 5% | clean_h-DCC-4.4A-2.5 | 4.9145 | 11.5321 | 4.8723 | 10.3116 | 52.0941 | 19.1948 |
| 5% | clean_h-Dynamic_Prof | 4.7350 | 9.2018 | 4.5127 | 8.0351 | 37.3970 | 11.4002 |
| 5% | clean_h-charging_7.3 | 3.8385 | 7.0526 | 3.0500 | 3.7821 | 15.8656 | 9.1970 |
| 5% | clean_h-DCC_4.4A_2.5 | 3.0771 | 10.2887 | 1.9089 | 8.1815 | 39.8232 | 16.0650 |
| 10% | clean_h-charge_rest_ | 8.3473 | 57.7166 | 7.0921 | 48.1401 | 68.8664 | 46.4040 |
| 10% | clean_h-DCC-4.4A-2.5 | 9.6581 | 11.7141 | 9.4946 | 10.5331 | 52.0715 | 18.9767 |
| 10% | clean_h-Dynamic_Prof | 9.3166 | 9.7318 | 8.8197 | 8.5876 | 37.4076 | 11.4693 |
| 10% | clean_h-charging_7.3 | 7.5735 | 7.7660 | 5.8976 | 4.2680 | 38.4122 | 14.0537 |
| 10% | clean_h-DCC_4.4A_2.5 | 6.0558 | 10.2901 | 3.7275 | 8.1891 | 39.9059 | 16.0726 |

### Diagnostik Internal EKF (Per-Dataset)
| NAMA DATASET | Avg |K[0]| | Avg R_dyn | Avg |h0| | Interpretasi |
| :--- | :---: | :---: | :---: | :--- |
| clean_h-charge_rest_ | 0.028456 | 0.019131 | 0.4693 | Gain seimbang |
| clean_h-DCC-4.4A-2.5 | 0.010682 | 0.024309 | 0.2117 | Gain seimbang |
| clean_h-Dynamic_Prof | 0.043559 | 0.016963 | 0.8411 | Gain seimbang |
| clean_h-charging_7.3 | 0.047594 | 0.010911 | 2.7493 | Gain seimbang |
| clean_h-DCC_4.4A_2.5 | 0.016142 | 0.021532 | 0.9149 | Gain seimbang |
| clean_h-charge_rest_ | 0.028462 | 0.019131 | 0.4691 | Gain seimbang |
| clean_h-DCC-4.4A-2.5 | 0.010661 | 0.024330 | 0.2050 | Gain seimbang |
| clean_h-Dynamic_Prof | 0.042887 | 0.017013 | 0.8266 | Gain seimbang |
| clean_h-charging_7.3 | 0.047514 | 0.010950 | 2.7374 | Gain seimbang |
| clean_h-DCC_4.4A_2.5 | 0.016150 | 0.021533 | 0.9146 | Gain seimbang |
| clean_h-charge_rest_ | 0.028562 | 0.019140 | 0.4664 | Gain seimbang |
| clean_h-DCC-4.4A-2.5 | 0.010775 | 0.024378 | 0.1903 | Gain seimbang |
| clean_h-Dynamic_Prof | 0.043954 | 0.017074 | 0.8050 | Gain seimbang |
| clean_h-charging_7.3 | 0.047218 | 0.011424 | 2.5898 | Gain seimbang |
| clean_h-DCC_4.4A_2.5 | 0.016147 | 0.021540 | 0.9125 | Gain seimbang |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.91 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 23.62 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 5.0e-06, `Q_11` = 1.0e-04
* **R Matriks (Measurement Noise):** Normalized Trust Factor: R_STEEP=0.0005, R_FLAT=0.0250, R_REST=0.0002
* **Rest Settling Time:** 30 s sebelum R_REST aktif
* **P_init (Initial Error Covariance):** `P[0][0]` = 0.02, `P[1][1]` = 0.1
* **Simulasi Memory Loss:** Algoritma divariasikan dengan *offset error* sebesar 0%, 5%, dan 10% untuk menguji kekokohan EKF secara komprehensif.