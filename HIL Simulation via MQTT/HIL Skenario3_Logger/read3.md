## Skenario 3: Pembebanan Dinamis (Urban Load / Fast Discharge)

Pengujian ini merupakan uji coba utama yang dirancang dengan memberikan arus fluktuatif tinggi beserta fase istirahat (*rest*) yang berulang. Tujuannya adalah untuk membuktikan bahwa algoritma **Extended Kalman Filter (EKF)** jauh lebih unggul dalam menangani dinamika tegangan dan *noise* sensor dibandingkan metode **Coulomb Counting (CC)** murni.

### Detail Pengujian
* **Metode:** Arus fluktuatif tinggi (15A, 10A, 5A) dengan fase *rest* berulang.
* **Dataset:** `Dynamic Profiling (Urban Load).csv`
* **Tujuan Eksperimen:** Membuktikan keunggulan EKF dalam menangani dinamika tegangan dan *noise* sensor dibanding metode CC murni pada kondisi beban dinamis.

---

## Ringkasan Output Skenario 3 `Analisa_RMSE.ipynb`

### Versi 1 (v1) - Tuning Parameter ESP32

Pada tahap ini, digunakan 10 titik pemetaan untuk *Look-Up Table* (LUT) OCV-SoC.

**Parameter:**
```cpp
// 10 titik (interval 5%) dari Cubic Spline Ground Truth
const int LUT_OCV_SIZE = 10;
const float lut_soc_ocv[LUT_OCV_SIZE] = {
    0.0, 0.098849, 0.212431, 0.326001, 0.439511,
    0.553234, 0.667017, 0.780667, 0.894377, 1.0};
const float lut_ocv[LUT_OCV_SIZE] = {
    2.655, 3.194, 3.223, 3.253, 3.282,
    3.288, 3.289, 3.297, 3.326, 3.537};

// TUNING NOISE PARAMETER
const float Q_NOISE_00 = 1e-6;
const float Q_NOISE_11 = 1e-4;
const float R_NOISE = 2e-4;
```

**Hasil Kalkulasi Root Mean Square Error (RMSE) v1**
=========================================
* **RMSE Metode Coulomb Counting:** 0.0000 %
* **RMSE Algoritma EKF:** 16.5742 %

---
![Skenario 3-Versi 1](Grafik_Skenario3_Dynamic_Load.png)

### Versi 2 (v2) - Tuning Parameter ESP32

Pada Skenario 3 ini, pengujian dengan parameter **Versi 2 (v2) tidak dilakukan** karena sudah mengetahui kurang bagusnya nilai RMSE berdasarkan hasil evaluasi pada Skenario 1 dan Skenario 2.

---

### Versi 3 (v3) - Tuning Parameter ESP32

Pada iterasi ketiga, jumlah titik LUT ditingkatkan menjadi 21 titik (nilai OCV monotonik naik) dengan *tuning noise parameter* yang telah disesuaikan.

**Parameter:**
```cpp
// Diperbarui menjadi 21 titik (interval 5%) dari Cubic Spline Ground Truth
const int LUT_OCV_SIZE = 21;
const float lut_soc_ocv[LUT_OCV_SIZE] = {
    0.00, 0.05, 0.10, 0.15, 0.20,
    0.25, 0.30, 0.35, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.65, 0.70,
    0.75, 0.80, 0.85, 0.90, 0.95, 1.00};

// Nilai OCV disesuaikan agar selalu memiliki gradien positif (monotonik naik)
// Sangat penting agar dOCV/dSOC (Matriks H) tidak pernah bernilai nol
const float lut_ocv[LUT_OCV_SIZE] = {
    2.655, 3.050, 3.194, 3.210, 3.220,
    3.232, 3.245, 3.258, 3.270, 3.282,
    3.285, 3.287, 3.288, 3.289, 3.291,
    3.294, 3.300, 3.310, 3.331, 3.385, 3.537};

// TUNING NOISE PARAMETER
const float Q_NOISE_00 = 1e-5;
const float Q_NOISE_11 = 1e-5;
const float R_NOISE = 1e-3;
```

**Hasil Kalkulasi Root Mean Square Error (RMSE) v3**
=========================================
* **RMSE Metode Coulomb Counting:** 0.0000 %
* **RMSE Algoritma EKF:** 12.3827 %

---
![Skenario 3-Versi 3](Grafik_Skenario3_Dynamic_Load.png)