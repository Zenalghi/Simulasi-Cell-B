# Analisis Mendalam & Penetapan Parameter Simulasi C

Mari kita bedah secara mendalam kelima poin analisis sebelum menetapkan parameter terbaik.

---

## 1. Diagnosis Skenario Charging (Mengapa Paling Sensitif?)

LiFePO4 memiliki kurva **Open Circuit Voltage (OCV)** yang sangat datar (*flat plateau*) pada rentang SoC 20% hingga 80%.

Pada fase **charging**, tegangan terminal baterai terdorong naik oleh:
- Arus pengisian
- Hambatan dalam ($R_0$)
- Efek polarisasi ($V_{c1}$)

### Masalah di Simulasi B
Ketika:
- Filter terlalu percaya sensor (**R kecil**)
- SoC diberi kebebasan berubah besar (**Q₀₀ besar**)

Maka:
- Sedikit error pada model ECM (misalnya $R_0$ meleset)
- EKF mengira **OCV naik drastis**

Karena kurva OCV datar:
- Perubahan kecil tegangan → diterjemahkan sebagai **lonjakan besar SoC**
- Jacobian ($H$) memperbesar efek ini

➡️ Dampak:
- SoC bisa loncat belasan persen
- RMSE Charging rusak parah (**10.49%**)

---

## 2. Analisis Trade-off Matriks Q vs R

- **R (Measurement Noise)** → kepercayaan terhadap sensor
- **Q (Process Noise)** → kepercayaan terhadap model (Coulomb Counting)

### Simulasi A (R = 0.05)
- Sensor kurang dipercaya
- SoC stabil (ikut CC)
- Tegangan lambat mengikuti real

➡️ Hasil:
- RMSE SoC bagus
- RMSE Tegangan buruk (> 26 mV)

---

### Simulasi B (R = 0.01)
- Sensor sangat dipercaya
- Tegangan sangat akurat

➡️ Hasil:
- RMSE Tegangan sangat baik (< 7 mV)
- SoC jadi sangat sensitif → mudah rusak

---

### Kesimpulan
- **R kecil (0.01) sebenarnya sudah benar**
- Masalah utama: **Q₀₀ terlalu besar (5e-6)**

➡️ Strategi:
- Pertahankan R kecil
- **Tekan Q₀₀**

---

## 3. Peran Matriks $P_{init}$ (Kovariansi Awal)

Menentukan seberapa tidak yakin EKF pada kondisi awal.

### Simulasi B (P_init = 0.1)
- Terlalu besar
- Kalman Gain awal meledak
- Muncul lonjakan liar di awal

➡️ Efek:
- Tidak stabil di area OCV datar

---

### Simulasi A (P_init = 0.01)
- Lebih stabil
- Konvergensi halus (tidak agresif)

➡️ Keputusan:
- Gunakan kembali **0.01**

---

## 4. Penetapan Parameter Simulasi C (Sweet Spot)

Target:
- RMSE Tegangan < 10 mV
- SoC tetap stabil

### Parameter Final

#### 🔹 R_NOISE = 0.02
- Tengah antara 0.05 dan 0.01
- Cukup responsif tapi tidak agresif

---

#### 🔹 Q_NOISE_00 = 5e-7 (SoC)
- Sangat kecil
- Menjaga SoC tetap stabil
- Mengandalkan Coulomb Counting

---

#### 🔹 Q_NOISE_11 = 5e-5 ($V_{c1}$)
- Lebih besar dari sebelumnya
- Memberi fleksibilitas pada dinamika polarisasi

➡️ Strategi:
> Biarkan error dikompensasi oleh $V_{c1}$, bukan SoC

---

#### 🔹 P_init [[0.01, 0], [0, 0.01]]


- Stabil
- Minim osilasi
- Konvergensi halus

---

## 5. Pertimbangan Tambahan (Model Fisik)

Realitas penting LiFePO4:

> Hambatan dalam ($R_0$) saat **charging ≠ discharging**

### Masalah Saat Ini
- LUT hanya punya satu $R_0$
- Tidak membedakan arah arus

➡️ Dampak:
- Discharge akurat
- Charging bermasalah

---

### Solusi Ideal (Hardware/Model)
Pisahkan:
- $R_{0,charge}$
- $R_{0,discharge}$

Namun:
- Perlu ubah arsitektur C++ (ESP32)
- Tidak praktis untuk sekarang

---

### Solusi Praktis (Software Tuning)

Gunakan pendekatan:

> Manipulasi rasio Q/R

➡️ Tujuan:
- Menyerap ketidakakuratan model
- Tanpa ubah struktur sistem

---

## Kesimpulan Akhir

Simulasi C adalah kompromi optimal:
- Tegangan tetap akurat
- SoC tetap stabil
- Model tetap sederhana

➡️ Pendekatan:
- **Kurangi Q₀₀ (SoC)**
- **Pertahankan R kecil**
- **Alihkan error ke $V_{c1}$**

---
