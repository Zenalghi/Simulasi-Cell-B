## Tabel Hasil Perbandingan Metrik (RMSE & MAE)
Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):

| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 0% | clean_h-charge_rest_ | 0.0000 | 1.3427 | 0.0000 | 0.9846 | 2.7681 | 1.4493 |
| 0% | clean_h-DCC-4.4A-2.5 | 0.0000 | 1.9632 | 0.0000 | 1.9005 | 1.6979 | 1.1614 |
| 0% | clean_h-Dynamic_Prof | 0.0000 | 0.7176 | 0.0000 | 0.6607 | 2.5948 | 1.2469 |
| 0% | clean_h-charging_7.3 | 0.0000 | 0.7452 | 0.0000 | 0.4868 | 1.6559 | 1.2485 |
| 0% | clean_h-DCC_4.4A_2.5 | 0.0000 | 1.1920 | 0.0000 | 0.9960 | 1.7606 | 1.3419 |
| 5% | clean_h-charge_rest_ | 4.2476 | 1.3406 | 3.6394 | 0.9823 | 5.8363 | 1.4927 |
| 5% | clean_h-DCC-4.4A-2.5 | 4.9145 | 2.1350 | 4.8723 | 2.0790 | 2.2536 | 1.1715 |
| 5% | clean_h-Dynamic_Prof | 4.6228 | 0.9402 | 4.3218 | 0.8688 | 2.8510 | 1.2800 |
| 5% | clean_h-charging_7.3 | 3.8385 | 0.7114 | 3.0500 | 0.4756 | 3.9349 | 1.2999 |
| 5% | clean_h-DCC_4.4A_2.5 | 3.0771 | 1.1929 | 1.9089 | 0.9993 | 3.2952 | 1.3652 |
| 10% | clean_h-charge_rest_ | 8.3473 | 1.3369 | 7.0921 | 0.9783 | 7.4203 | 1.5177 |
| 10% | clean_h-DCC-4.4A-2.5 | 9.6581 | 2.2882 | 9.4946 | 2.2368 | 2.8751 | 1.1778 |
| 10% | clean_h-Dynamic_Prof | 9.0670 | 1.7563 | 8.3954 | 1.6378 | 3.1176 | 1.3466 |
| 10% | clean_h-charging_7.3 | 7.5735 | 0.9323 | 5.8976 | 0.6928 | 2.3716 | 1.3041 |
| 10% | clean_h-DCC_4.4A_2.5 | 6.0558 | 1.1959 | 3.7275 | 0.9974 | 4.3007 | 1.3766 |

### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)
Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:

| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |
| :--- | :---: | :---: | :---: |
| **Coulomb Counting** | 0.92 | ~16 | O(1) Constant Time |
| **Extended Kalman Filter** | 18.64 | ~3200 (3.2 kB) | O(n^3) Cubic Time |

*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*

### Parameter Model & Tuning EKF yang Digunakan:
* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)
  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC
* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)
* **Q Matriks (Process Noise):** `Q_00` = 2.0e-06, `Q_11` = 1.0e-01
* **R Matriks (Measurement Noise):** Dynamic Observability R = 0.0001 / (|dOCV/dSOC| + 1e-4) | R_REST = 0.0001 (aktif setelah 30s arus ~0)
* **Jacobian h0:** fabsf(dOCV/dSOC) + 1e-4 [FIX: abs mencegah sign-flip di OCV-dip LiFePO4 region 15-22%]
* **Soft Deadband:** 1 mV + Correction Cap 10% SoC/step
* **P_init:** P[0][0]=offset*50+0.01, P[1][1]=0.001
* **Ground Truth Fix:** Dynamic Profiling soc_init=0.953 (dari OCV inverse: V_rest=3.420V)
* **Simulasi Memory Loss:** Algoritma divariasikan dengan *offset error* sebesar 0%, 5%, dan 10% untuk menguji kekokohan EKF secara komprehensif.
