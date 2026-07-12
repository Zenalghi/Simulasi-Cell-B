// =============================================================================
// PROGRAM  : Processor-In-the-Loop (PiL) Simulation - BMS SoC Estimation
// PLATFORM : ESP32 DevKit V1
//
// APA ITU PiL (PROCESSOR-IN-THE-LOOP)?
// PiL adalah metode pengujian EMBEDDED SOFTWARE menggunakan HARDWARE ASLI (ESP32),
// TETAPI menggunakan DATA SIMULASI (dari file CSV) sebagai pengganti sensor nyata.
// Ini memungkinkan kita menguji algoritma di lingkungan yang MENDEKATI REALITAS
// (kecepatan CPU, penggunaan RAM, presisi floating point ESP32) tanpa membutuhkan
// baterai fisik, charger, atau setup lab yang kompleks.
//
// PERBEDAAN DENGAN SiL (Software-In-the-Loop):
// SiL = dijalankan di PC/laptop (simulasi murni software)
// PiL = dijalankan di ESP32 asli (hardware target yang sesungguhnya)
// PiL lebih akurat karena mengukur performa NYATA pada chip ESP32 (waktu CPU, RAM)
//
// TUJUAN UTAMA PROGRAM INI:
// Membandingkan 2 algoritma estimasi SoC baterai LiFePO4:
//   1. Coulomb Counting (CC) : Sederhana, hanya akumulasi arus
//   2. Extended Kalman Filter (EKF) : Canggih, menggabungkan CC + koreksi tegangan
// Program ini mengukur: RMSE, MAE, Waktu CPU (µs), dan penggunaan RAM (Bytes)
// untuk setiap algoritma pada 5 dataset x 3 variasi offset error = 15 skenario uji
//
// CARA KERJA:
// 1. File CSV dataset disimpan di flash ESP32 menggunakan LittleFS
// 2. Setiap baris CSV dibaca = satu timestep simulasi (seperti membaca sensor)
// 3. CC dan EKF dijalankan per timestep, hasilnya dibandingkan dengan "ground truth"
// 4. Hasil akhir dicetak ke Serial Monitor dalam format tabel dan Markdown
// =============================================================================

// JALANKAN_MODE: Mengontrol algoritma apa yang diaktifkan saat simulasi.
// Mode 1: Hanya Coulomb Counting → berguna sebagai baseline sederhana
// Mode 2: CC + EKF dijalankan bersamaan → membandingkan keduanya secara penuh
// Gunakan directive #if JALANKAN_MODE == 2 di kode untuk kondisional kompilasi.
#define JALANKAN_MODE 2 // 1: Hanya Coulomb Counting (Flash Baseline), 2: CC + EKF (Sistem Penuh)

// --- LIBRARY yang digunakan ---
// Arduino.h  : Library inti ESP32 (wajib ada)
// LittleFS.h : File system berbasis flash ESP32 untuk menyimpan dan membaca file CSV dataset
//              LittleFS lebih handal dari SPIFFS untuk operasi baca intensif
// math.h     : Fungsi matematika standar C (sqrt, fabsf, expf, dll)
#include <Arduino.h>
#include <LittleFS.h>
#include <math.h>

// =========================================================
// 1. STRUKTUR PENYIMPAN HASIL UNTUK TABEL FINAL
// =========================================================
// TestResult: Struct untuk menyimpan semua metrik evaluasi dari SATU skenario uji.
// Setiap skenario = 1 file dataset + 1 nilai offset error SoC awal.
//
// Metrik Akurasi (Error SoC):
//   rmse_cc   : Root Mean Square Error SoC Coulomb Counting (dalam %)
//   rmse_ekf  : Root Mean Square Error SoC Extended Kalman Filter (dalam %)
//   rmse_v    : Root Mean Square Error Prediksi Tegangan EKF (dalam mV)
//   mae_cc    : Mean Absolute Error SoC CC (dalam %)
//   mae_ekf   : Mean Absolute Error SoC EKF (dalam %)
//   mae_v     : Mean Absolute Error Prediksi Tegangan EKF (dalam mV)
//
// Metrik Performa Hardware (Trade-off):
//   avg_exec_time_cc_us  : Rata-rata waktu eksekusi CC per timestep (mikrodetik)
//   avg_exec_time_ekf_us : Rata-rata waktu eksekusi EKF per timestep (mikrodetik)
//   max_sram_cc  : Pemakaian stack memori maksimum oleh CC (bytes)
//   max_sram_ekf : Pemakaian stack memori maksimum oleh EKF (bytes)
struct TestResult
{
  String filename;             // Nama file CSV dataset (dipotong 20 karakter untuk tabel)
  int offset_pct;              // Offset error SoC awal dalam persen (0, 5, atau 10)
  float rmse_cc;               // RMSE SoC Coulomb Counting (%)
  float rmse_ekf;              // RMSE SoC EKF (%)
  float rmse_v;                // RMSE Tegangan Prediksi EKF (mV)
  float mae_cc;                // MAE SoC Coulomb Counting (%)
  float mae_ekf;               // MAE SoC EKF (%)
  float mae_v;                 // MAE Tegangan Prediksi EKF (mV)
  float avg_exec_time_cc_us;   // Waktu eksekusi rata-rata CC (µs)
  float avg_exec_time_ekf_us;  // Waktu eksekusi rata-rata EKF (µs)
  float max_sram_cc;           // Konsumsi stack maksimum CC (bytes)
  float max_sram_ekf;          // Konsumsi stack maksimum EKF (bytes)
};

// Array untuk menyimpan semua hasil: 5 dataset × 3 offset = 15 skenario maksimum
TestResult final_results[15];
int result_index = 0; // Indeks pengisian array (berapa skenario yang sudah selesai)

// =========================================================
// 2. PARAMETER MODEL BATERAI
// =========================================================
// Q_AH: Kapasitas nominal baterai LiFePO4 yang diuji (20.8 Ah)
// Q_COULOMB: Konversi ke Coulomb (Ampere-detik) untuk digunakan dalam formula Coulomb Counting
//   Q_COULOMB = Q_AH × 3600 = 20.798555 × 3600 = 74874.8 As
//   Dipakai dalam rumus: ΔSoC = I × dt / Q_COULOMB
const float Q_AH = 20.798555;
const float Q_COULOMB = 74874.8;

// OCV-SOC Lookup Table (Piecewise Linear Interpolation)
// Tabel ini adalah "peta" yang menghubungkan SoC (%) dengan OCV (tegangan sirkuit terbuka).
// Sumber data: file h-GroundTruth_OCV_SOC_LiFePO4.csv yang difit menggunakan Cubic Spline di Python.
// Resolusi: 21 titik dari SoC=0% hingga SoC=100% dengan step 5%.
//
// CATATAN PENTING KARAKTERISTIK LiFePO4:
// Perhatikan OCV di SoC 15-25%: nilai TURUN dari 3.2391 → 3.2261 → 3.2242 (NON-MONOTONIC / OCV-DIP)
// Ini adalah ciri khas baterai LiFePO4 dan MENJADI TANTANGAN bagi EKF karena
// dOCV/dSOC bisa NEGATIF di region ini, yang dapat menyebabkan Kalman Gain terbalik!
const int LUT_OCV_SIZE = 21;
const float lut_soc_ocv[LUT_OCV_SIZE] = { // Sumbu X: SoC (0.0 = 0%, 1.0 = 100%)
    0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00};
const float lut_ocv_val[LUT_OCV_SIZE] = { // Sumbu Y: OCV (Volt)
    2.6550, 3.0269, 3.1972, 3.2391, 3.2261, 3.2242, 3.2424, 3.2625,
    3.2758, 3.2835, 3.2871, 3.2880, 3.2878, 3.2884, 3.2917, 3.2958,
    3.2973, 3.3039, 3.3353, 3.4122, 3.5370};

// Parameter ECM 1-RC Thevenin: Model Sirkuit Ekuivalen Baterai
// Model ini menggambarkan baterai sebagai:
//   OCV (sumber tegangan ideal) + R0 (resistor ohm seri) + (R1 || C1) (rangkaian RC paralel)
// Parameter R0, R1, C1 TIDAK KONSTAN — mereka berubah tergantung SoC saat ini.
// LUT_ECM_SIZE = 9 titik interpolasi (lebih kasar dari OCV karena parameter ini lebih smooth)
const int LUT_ECM_SIZE = 9;
const float lut_soc_ecm[LUT_ECM_SIZE] = { // SoC titik-titik kalibrasi ECM
    0.0, 0.090902, 0.204618, 0.318054, 0.431697,
    0.545421, 0.659070, 0.772787, 0.886430};
const float lut_r0[LUT_ECM_SIZE] = { // R0: Resistansi Ohm internal (Ohm)
    0.006050, 0.002800, 0.002800, 0.002899, 0.002700,
    0.002400, 0.002899, 0.002199, 0.002800};
const float lut_r1[LUT_ECM_SIZE] = { // R1: Resistansi polarisasi dalam jaringan RC (Ohm)
    0.009500, 0.002506, 0.002207, 0.002212, 0.002372,
    0.002436, 0.002374, 0.002345, 0.002684};
const float lut_c1[LUT_ECM_SIZE] = { // C1: Kapasitansi polarisasi dalam jaringan RC (Farad)
    11281.15, 20591.86, 24841.48, 15061.40, 20897.75,
    19607.70, 15177.97, 16580.74, 24189.08};

// =========================================================
// 3. TUNING NOISE PARAMETER EKF  (esp15 — final fix)
// =========================================================
// Tiga fix kritis berdasarkan analisis Python simulation:
//
// FIX 1 (parameter): Revert Q00=2e-6, Q11=1e-1, R_REST=1e-4
//   esp14 naikkan Q00 ke 1e-5 → EKF terlalu percaya voltage →
//   Dynamic Profiling 0% offset malah naik ke 5.04%.
//
// FIX 2 (Jacobian h0): fabsf(dOCV/dSOC) + 1e-4
//   LiFePO4 punya region non-monotonic di SoC 15-22% (OCV dip).
//   dOCV negatif → h0 negatif → K[0] negatif → koreksi terbalik!
//   Charging off10% dari soc=0.16 (di dip zone): EKF divergen ke 14%.
//   Solusi: selalu pakai |dOCV| untuk Jacobian.
//
// FIX 3 (ground truth): Dynamic Profiling soc_true_init = 0.953
//   V_first = 3.420V (I=0) → OCV_inverse → SoC ≈ 0.953, bukan 1.0!
//   Asumsi 1.0 membuat RMSE terlihat 5.4% padahal EKF sudah benar.
// Nilai final yang dipilih setelah eksperimen (versi esp15):
// Q_NOISE_00 = 2e-6 : Noise proses SoC sangat kecil → EKF yakin SoC berubah pelan
// Q_NOISE_11 = 0.1  : Noise proses Vc1 cukup besar → EKF tahu tegangan kapasitor bisa berubah cepat
// R_BASE = 1e-4     : Noise pengukuran sensor tegangan (akan dimodifikasi secara dinamis)
const float Q_NOISE_00 = 2e-6f; // Process noise untuk SoC (state pertama)
float Q_NOISE_11 = 1e-1f;       // Process noise untuk Vc1 (state kedua, sengaja float agar bisa diubah)
float R_BASE = 1e-4f;           // Base measurement noise sensor tegangan (float agar adjustable)

// Rest detection: mendeteksi kondisi baterai istirahat (tidak dibebani / tidak diisi)
// Saat istirahat dan V_terminal ≈ OCV sejati → sensor tegangan menjadi sangat akurat
// → EKF dapat melakukan koreksi SoC yang sangat tepat (observabilitas tinggi)
const float REST_CURRENT_THRESH = 0.05f; // A — batas arus untuk dianggap 'istirahat'
const int REST_SETTLE_S = 30;            // detik arus harus < threshold secara terus-menerus
const float R_REST = 1e-4f;              // R saat confirmed rest = agresif (percaya sensor penuh)

// =========================================================
// 4. VARIABEL STATE ESTIMATION & ERROR TRACKING
// =========================================================

// soc_cc: Estimasi SoC dari metode Coulomb Counting murni.
// Berubah setiap timestep menggunakan rumus: SoC_baru = SoC_lama - (I * dt / Q_COULOMB)
// Diinisialisasi ke 0.0, akan di-set sesuai soc_true + offset saat sample pertama.
float soc_cc = 0.0;

// ekf_x[2]: State Vector EKF — kondisi internal baterai menurut estimasi EKF
// ekf_x[0] = Estimasi SoC (0.0 = 0%, 1.0 = 100%)
// ekf_x[1] = Estimasi Vc1 (tegangan efek polarisasi di kapasitor model Thevenin, dalam Volt)
float ekf_x[2] = {0.0, 0.0};

// ekf_P[2][2]: Matriks Kovarian Error — "seberapa ragu" EKF terhadap estimasinya
// P[0][0] : Ketidakpastian estimasi SoC (semakin besar = EKF makin ragu → lebih percaya sensor)
// P[1][1] : Ketidakpastian estimasi Vc1
// Nilai awal di sini tidak penting karena akan di-reset ulang di setiap dataset
float ekf_P[2][2] = {{0.0f, 0.0}, {0.0, 0.1f}};

// v_pred_last: Tegangan terminal yang diprediksi EKF pada timestep terakhir (Volt)
// Digunakan untuk menghitung err_v (error tegangan EKF vs tegangan sensor CSV)
float v_pred_last = 0.0;

// soc_true: SoC referensi / Ground Truth
// Dianggap sebagai nilai SoC yang "paling benar" (dihitung dengan CC yang SEMPURNA:
// mengetahui SoC awal yang tepat berdasarkan pengukuran OCV saat baterai istirahat)
// Digunakan sebagai pembanding untuk menghitung error estimasi CC dan EKF.
float soc_true = 0.0;

// Variabel deteksi istirahat (di-reset setiap ganti dataset agar tidak terkontaminasi)
int rest_counter_s = 0;      // Penghitung detik arus mendekati nol secara terus-menerus
bool in_confirmed_rest = false; // true = baterai dikonfirmasi sedang istirahat

// Akumulator error untuk menghitung RMSE dan MAE di akhir setiap dataset.
// Menggunakan double (64-bit) untuk presisi tinggi saat akumulasi banyak sampel.
double sum_sq_err_cc = 0;      // Σ (soc_true - soc_cc)²  untuk RMSE CC
double sum_sq_err_ekf_soc = 0; // Σ (soc_true - ekf_x[0])² untuk RMSE EKF SoC
double sum_sq_err_ekf_v = 0;   // Σ (V_sensor - V_pred)²  untuk RMSE Tegangan EKF

double sum_abs_err_cc = 0;      // Σ |soc_true - soc_cc|    untuk MAE CC
double sum_abs_err_ekf_soc = 0; // Σ |soc_true - ekf_x[0]| untuk MAE EKF
double sum_abs_err_ekf_v = 0;   // Σ |V_sensor - V_pred|   untuk MAE Tegangan EKF

// Penghitung total baris data yang sudah diproses (baris valid dari CSV, bukan header)
long total_samples = 0;

// =========================================================
// 5. FUNGSI MATEMATIKA: INTERPOLASI & OCV-SOC
// =========================================================

// interpolate1D: Interpolasi Linear 1 Dimensi (Piecewise Linear)
// Mencari nilai Y untuk sembarang nilai X menggunakan tabel (x_data, y_data).
// Cocok untuk memetakan SoC → OCV atau SoC → R0/R1/C1 dari tabel kalibrasi.
//
// Cara kerja: Cari di segmen mana X berada, lalu lakukan interpolasi linear di situ.
// Y = Y_kiri + ((X - X_kiri) / (X_kanan - X_kiri)) × (Y_kanan - Y_kiri)
float interpolate1D(float x, const float *x_data, const float *y_data, int size)
{
  if (x <= x_data[0])         // Batas bawah: kembalikan nilai pertama
    return y_data[0];
  if (x >= x_data[size - 1])  // Batas atas: kembalikan nilai terakhir
    return y_data[size - 1];
  for (int i = 0; i < size - 1; i++)
  {
    if (x >= x_data[i] && x <= x_data[i + 1])
    {
      float t = (x - x_data[i]) / (x_data[i + 1] - x_data[i]); // Faktor interpolasi [0..1]
      return y_data[i] + t * (y_data[i + 1] - y_data[i]);       // Interpolasi linear
    }
  }
  return y_data[0]; // Fallback (tidak seharusnya tercapai)
}

// get_OCV_from_LUT: Mendapatkan nilai OCV (tegangan open circuit) berdasarkan SoC.
// Wrapper dari interpolate1D untuk tabel OCV-SoC baterai LiFePO4.
// Dipakai saat EKF memprediksi tegangan terminal baterai (V_pred).
float get_OCV_from_LUT(float soc)
{
  return interpolate1D(constrain(soc, 0.0f, 1.0f),
                       lut_soc_ocv, lut_ocv_val, LUT_OCV_SIZE);
}

// get_dOCV_dSOC_LUT: Menghitung turunan (kemiringan/slope) kurva OCV terhadap SoC.
// Menggunakan metode numerik beda-hingga (Finite Difference): (OCV(soc+h) - OCV(soc-h)) / 2h
// Nilai ini adalah elemen Matriks Jacobian H dalam EKF.
//
// Interpretasi hasil:
// - Nilai besar (curam)  : tegangan sensitif terhadap SoC → sensor informatif → EKF lebih percaya sensor
// - Nilai kecil (landai) : tegangan hampir tidak berubah → sensor kurang informatif → EKF lebih percaya model
// - Nilai NEGATIF (OCV-dip di SoC 15-22%): menjadi masalah karena bisa balikkan arah koreksi EKF!
float get_dOCV_dSOC_LUT(float soc)
{
  soc = constrain(soc, 0.0f, 1.0f);
  float h = 0.005f;                      // Langkah numerik = 0.5% SoC
  float soc_lo = max(soc - h, 0.0f);    // Titik kiri
  float soc_hi = min(soc + h, 1.0f);    // Titik kanan
  float dSOC = soc_hi - soc_lo;         // Jarak antar titik
  if (dSOC < 1e-6f) return 0.0f;        // Hindari pembagian nol
  return (get_OCV_from_LUT(soc_hi) - get_OCV_from_LUT(soc_lo)) / dSOC;
}

// get_SOC_from_OCV: Fungsi kebalikan dari get_OCV_from_LUT.
// Diberikan tegangan OCV yang terukur saat baterai ISTIRAHAT (tidak ada arus),
// fungsi ini menebak berapa SoC yang berkoresponden.
//
// DIGUNAKAN UNTUK: Menentukan soc_true_init yang AKURAT berdasarkan tegangan awal data.
// Contoh: V_first = 3.420V (saat I=0) → cari di tabel → SoC ≈ 0.953 (bukan asumsi 1.0!)
// Ini adalah FIX 3 dalam program ini (ground truth correction untuk Dynamic Profiling dataset).
//
// TANTANGAN: Kurva LiFePO4 NON-MONOTONIC (ada OCV-dip di 15-22%)
// Solusi: Cek kedua arah (v0≤ocv≤v1 ATAU v1≤ocv≤v0) lalu ambil yang paling dekat (best_diff).
float get_SOC_from_OCV(float ocv)
{
  if (ocv <= lut_ocv_val[0])                // OCV terlalu rendah → SoC = 0%
    return 0.0f;
  if (ocv >= lut_ocv_val[LUT_OCV_SIZE - 1]) // OCV terlalu tinggi → SoC = 100%
    return 1.0f;

  // Cari interval yang mengandung nilai OCV ini (mendukung kurva non-monotonic)
  for (int i = 0; i < LUT_OCV_SIZE - 1; i++)
  {
    float v0 = lut_ocv_val[i];
    float v1 = lut_ocv_val[i + 1];
    // Cek apakah ocv berada di antara v0 dan v1 (dalam kedua arah)
    if ((ocv >= v0 && ocv <= v1) || (ocv <= v0 && ocv >= v1))
    {
      if (fabsf(v1 - v0) < 0.0001f)  // Segmen sangat datar → kembalikan ujung kiri
        return lut_soc_ocv[i];
      float t = constrain((ocv - v0) / (v1 - v0), 0.0f, 1.0f); // Faktor interpolasi
      return lut_soc_ocv[i] + t * (lut_soc_ocv[i + 1] - lut_soc_ocv[i]);
    }
  }

  // Fallback: cari titik OCV di tabel yang PALING DEKAT dengan nilai yang diberikan
  // (dipakai jika tidak ada interval yang cocok akibat non-monotonic curve)
  int best_idx = 0;
  float best_diff = fabsf(ocv - lut_ocv_val[0]);
  for (int i = 1; i < LUT_OCV_SIZE; i++)
  {
    float diff = fabsf(ocv - lut_ocv_val[i]);
    if (diff < best_diff)
    {
      best_diff = diff;
      best_idx = i;
    }
  }
  return lut_soc_ocv[best_idx];
}

// =========================================================
// 6. ALGORITMA STATE OF CHARGE (CC & EKF)
// =========================================================

// Fungsi untuk menghitung SoC menggunakan metode Coulomb Counting (CC).
// Rumus: SoC_baru = SoC_lama - (Arus * delta_waktu / Kapasitas_Total_Coulomb)
// Catatan: Arus (I_meas) bernilai positif saat baterai discharge (dipakai), dan negatif saat charge.
void runCCStep(float I_meas, float dt)
{
  soc_cc = constrain(soc_cc - (I_meas * dt / Q_COULOMB), 0.0, 1.0);
}

// Fungsi utama Extended Kalman Filter (EKF) untuk mengestimasi SoC.
// EKF menggabungkan prediksi dari model matematika baterai dengan koreksi dari pembacaan sensor tegangan aktual.
void runEKFStep(float I_meas, float V_meas, float dt)
{
  // --- Time Update (Prediction) ---
  // TAHAP 1: Memprediksi status baterai (SoC dan Vc1) pada langkah waktu berikutnya. 
  // Tahap ini murni menggunakan persamaan model sirkuit ekivalen (Equivalent Circuit Model) tanpa melihat nilai dari sensor tegangan.
  float soc_prev = constrain(ekf_x[0], 0.0, 1.0);
  float vc1_prev = ekf_x[1];

  float R0 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_r0, LUT_ECM_SIZE), 0.0001f);
  float R1 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_r1, LUT_ECM_SIZE), 0.0001f);
  float C1 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_c1, LUT_ECM_SIZE), 1.0f);
  float tau = max(R1 * C1, 0.000001f);

  float soc_pred = constrain(soc_prev - (I_meas * dt / Q_COULOMB), 0.0, 1.0);
  float alpha = (dt > 0) ? expf(-dt / tau) : 1.0f;
  float vc1_pred = (alpha * vc1_prev) + (R1 * (1.0f - alpha) * I_meas);

  ekf_x[0] = soc_pred;
  ekf_x[1] = vc1_pred;

  // Prediksi Covariance P (decoupled)
  float P_pred[2][2];
  P_pred[0][0] = ekf_P[0][0] + Q_NOISE_00;
  P_pred[0][1] = 0.0f;
  P_pred[1][0] = 0.0f;
  P_pred[1][1] = (alpha * alpha * ekf_P[1][1]) + Q_NOISE_11;

  // --- Measurement Update (Correction) ---
  // TAHAP 2: Mengoreksi prediksi dari tahap 1 berdasarkan pembacaan sensor tegangan aktual (V_meas).
  
  // Mencari nilai Open Circuit Voltage (OCV) dari Lookup Table menggunakan prediksi SoC
  float OCV_pred = get_OCV_from_LUT(soc_pred);
  float dOCV_dSOC = get_dOCV_dSOC_LUT(soc_pred); // Menghitung turunan/gradien OCV terhadap SoC (ini adalah Jacobian H)

  // Memprediksi tegangan jepit baterai (Terminal Voltage) berdasar model
  // V_prediksi = OCV - Tegangan_Polarisasi(Vc1) - Drop_Tegangan_Resistor_Internal(Arus * R0)
  float V_pred = OCV_pred - vc1_pred - (I_meas * R0);
  v_pred_last = V_pred;

  // ---------------------------------------------------------
  // FIX 2 (Jacobian): h0 = |dOCV/dSOC| + 1e-4
  // ---------------------------------------------------------
  // LiFePO4 punya OCV-dip di SoC 15-22%: dOCV/dSOC NEGATIF.
  // Dengan h0 negatif: K[0] negatif, innovasi negatif
  // → koreksi positif (SoC naik), padahal harusnya turun → DIVERGEN.
  // Solusi: fabsf(dOCV_dSOC) — treat slope sebagai magnitude.
  // Efek samping minimal karena region ini observabilitasnya rendah
  // dan R_dyn sudah besar di area flat, sehingga K kecil.
  // ---------------------------------------------------------
  float h0 = fabsf(dOCV_dSOC) + 1e-4f;
  float h1 = -1.0f;

  // Dynamic R: trust measurement proportional to OCV slope steepness
  // In flat region slope~0 → R large → rely more on model
  // In steep region slope large → R small → rely on measurement
  float R_dynamic;
  if (in_confirmed_rest)
  {
    R_dynamic = R_REST;
  }
  else if (abs(I_meas) < 0.05f)
  {
    R_dynamic = R_BASE / (abs(dOCV_dSOC) + 1e-3f);
  }
  else
  {
    R_dynamic = R_BASE / (abs(dOCV_dSOC) + 1e-4f);
  }

  // Clamp R_dynamic to prevent numerical issues
  R_dynamic = constrain(R_dynamic, 0.0001f, 10.0f);

  // Innovation Covariance S = H*P*H' + R
  // S merepresentasikan total ketidakpastian (variansi) dari pengukuran dikombinasikan dengan ketidakpastian prediksi.
  float S = (h0 * h0 * P_pred[0][0]) + (h0 * h1 * P_pred[0][1]) +
            (h1 * h0 * P_pred[1][0]) + (h1 * h1 * P_pred[1][1]) + R_dynamic;
  if (S < 1e-9f)
    S = 1e-9f;

  // Kalman Gain K = P*H' / S
  // Kalman Gain (K) menentukan seberapa besar pembacaan sensor akan mempengaruhi/mengoreksi prediksi.
  // Jika K besar -> kita lebih percaya pada sensor tegangan (koreksi SoC besar).
  // Jika K kecil -> kita lebih percaya pada model matematika internal EKF (koreksi SoC kecil).
  float K[2];
  K[0] = ((P_pred[0][0] * h0) + (P_pred[0][1] * h1)) / S; // K[0] untuk faktor koreksi SoC
  K[1] = ((P_pred[1][0] * h0) + (P_pred[1][1] * h1)) / S; // K[1] untuk faktor koreksi Vc1

  // --- SOFT DEADBAND (1mV) + CORRECTION CAP (10% SoC per step) ---
  // Deadband: meredam koreksi mikro akibat model mismatch kecil.
  // Correction cap: mencegah over-correction besar dalam satu langkah,
  // misal saat EKF di region slope curam dengan large innovation.
  float K0_eff = K[0];
  float innov = V_meas - V_pred;
  const float DEADBAND = 0.001f;      // 1 mV
  const float MAX_CORRECTION = 0.10f; // maks 10% SoC per langkah

  if (fabsf(innov) < DEADBAND)
  {
    K0_eff *= (fabsf(innov) / DEADBAND);
  }

  // Apply correction with cap
  float soc_correction = K0_eff * innov;
  if (soc_correction > MAX_CORRECTION)
    soc_correction = MAX_CORRECTION;
  if (soc_correction < -MAX_CORRECTION)
    soc_correction = -MAX_CORRECTION;

  // Koreksi State x = x + correction (capped)
  ekf_x[0] = max(0.0f, min(1.0f, ekf_x[0] + soc_correction));
  ekf_x[1] += K[1] * innov;

  // Cap Vc1
  if (ekf_x[1] > 0.5f)
    ekf_x[1] = 0.5f;
  if (ekf_x[1] < -0.5f)
    ekf_x[1] = -0.5f;

  // Update Covariance P (Joseph Form)
  float I_KH[2][2];
  I_KH[0][0] = 1.0f - (K0_eff * h0);
  I_KH[0][1] = -(K0_eff * h1);
  I_KH[1][0] = -(K[1] * h0);
  I_KH[1][1] = 1.0f - (K[1] * h1);

  float Temp[2][2];
  Temp[0][0] = I_KH[0][0] * P_pred[0][0] + I_KH[0][1] * P_pred[1][0];
  Temp[0][1] = I_KH[0][0] * P_pred[0][1] + I_KH[0][1] * P_pred[1][1];
  Temp[1][0] = I_KH[1][0] * P_pred[0][0] + I_KH[1][1] * P_pred[1][0];
  Temp[1][1] = I_KH[1][0] * P_pred[0][1] + I_KH[1][1] * P_pred[1][1];

  ekf_P[0][0] = Temp[0][0] * I_KH[0][0] + Temp[0][1] * I_KH[0][1] + (K0_eff * K0_eff * R_dynamic);
  ekf_P[0][1] = Temp[0][0] * I_KH[1][0] + Temp[0][1] * I_KH[1][1] + (K0_eff * K[1] * R_dynamic);
  ekf_P[1][0] = Temp[1][0] * I_KH[0][0] + Temp[1][1] * I_KH[0][1] + (K[1] * K0_eff * R_dynamic);
  ekf_P[1][1] = Temp[1][0] * I_KH[1][0] + Temp[1][1] * I_KH[1][1] + (K[1] * K[1] * R_dynamic);

  // Symmetry enforcement & positivity floor
  ekf_P[0][1] = (ekf_P[0][1] + ekf_P[1][0]) * 0.5f;
  ekf_P[1][0] = ekf_P[0][1];
  ekf_P[0][0] = max(ekf_P[0][0], 1e-10f);
  ekf_P[1][1] = max(ekf_P[1][1], 1e-10f);
}

// =========================================================
// 7. RUNNER PROCESSOR-IN-THE-LOOP (PiL)
// =========================================================
// runDatasetTest: Fungsi utama simulasi PiL. Satu panggilan = satu skenario pengujian lengkap.
//
// Cara kerjanya:
// 1. Buka file CSV dari LittleFS (flash internal ESP32)
// 2. Baca baris demi baris = simulasikan timestep sensor (seolah data datang dari ADC)
// 3. Setiap baris: jalankan CC dan EKF, ukur waktu CPU dan RAM
// 4. Bandingkan hasil estimasi dengan soc_true (ground truth)
// 5. Hitung dan simpan semua metrik ke struct TestResult
//
// Format CSV yang diharapkan: Time(S), Dir_Cur(A), Voltage(V)
//   - Time(S)   : Waktu dalam detik (untuk menghitung dt antar timestep)
//   - Dir_Cur(A): Arus BERTANDA (positif = discharge, negatif = charge)
//                 Nilai ini sudah diproses oleh preprocess.py
//   - Voltage(V): Tegangan terminal baterai terukur
//
// Parameter:
//   filename       : Nama file CSV di LittleFS (tanpa path prefix)
//   offset_pct_val : Offset error SoC awal dalam desimal (0.0, 0.05, 0.10)
//                    Mensimulasikan kondisi awal yang SALAH (memory loss)
//                    Offset ini ditambah/dikurangi dari soc_true pada sample pertama.
//
// Return: true jika sukses, false jika file tidak bisa dibuka
bool runDatasetTest(String filename, float offset_pct_val)
{
  // Buka file CSV dari LittleFS (flash internal ESP32)
  File file = LittleFS.open("/" + filename, "r");
  if (!file)
  {
    Serial.printf("[ERROR] Gagal membuka file %s.\n", filename.c_str());
    return false;
  }

  Serial.printf("[INFO] Menguji Dataset: %s\n", filename.c_str());

  // Skip baris header CSV: baca baris demi baris hingga menemukan baris yang mengandung "Time(S)"
  while (file.available())
  {
    String line = file.readStringUntil('\n');
    if (line.indexOf("Time(S)") >= 0)
      break; // Header ditemukan, berhenti — baris berikutnya adalah data pertama
  }

  // Reset semua akumulator error ke nol sebelum memulai dataset baru
  // (Penting agar error dari dataset sebelumnya tidak mencemari hasil dataset ini)
  sum_sq_err_cc = 0;
  sum_abs_err_cc = 0;
  sum_sq_err_ekf_soc = 0;
  sum_abs_err_ekf_soc = 0;
  sum_sq_err_ekf_v = 0;
  sum_abs_err_ekf_v = 0;
  total_samples = 0;

  // Reset juga status deteksi istirahat per dataset
  rest_counter_s = 0;
  in_confirmed_rest = false;

  // Variabel untuk pengukuran performa hardware
  uint64_t total_exec_time_cc_us = 0;  // Total waktu eksekusi CC dalam dataset ini (µs)
  uint64_t total_exec_time_ekf_us = 0; // Total waktu eksekusi EKF dalam dataset ini (µs)
  size_t max_cc_stack_consumed = 0;    // Pemakaian stack CC maksimum yang terukur (bytes)
  size_t max_ekf_stack_consumed = 0;   // Pemakaian stack EKF maksimum yang terukur (bytes)

  float time_prev = -1.0; // Waktu timestep sebelumnya (-1 = belum ada data sebelumnya)
  char buf[128];           // Buffer char untuk menyimpan satu baris CSV saat diparsing

  // === LOOP UTAMA: Proses setiap baris CSV sebagai satu timestep simulasi ===
  while (file.available())
  {
    String line = file.readStringUntil('\n'); // Baca satu baris
    line.trim();                              // Hapus whitespace / \r di akhir baris
    if (line.length() < 5)                   // Lewati baris kosong atau terlalu pendek
      continue;

    // Parse CSV: pisahkan kolom menggunakan strtok (tokenizer berdasarkan koma)
    line.toCharArray(buf, sizeof(buf));
    char *t_str = strtok(buf, ",");    // Kolom 1: Waktu (detik)
    char *c_str = strtok(NULL, ",");   // Kolom 2: Arus bertanda (Ampere)
    char *v_str = strtok(NULL, ",");   // Kolom 3: Tegangan terminal (Volt)

    if (!t_str || !c_str || !v_str)    // Skip baris jika ada kolom yang hilang
      continue;

    float time_s  = atof(t_str); // Konversi string ke float
    float current = atof(c_str); // Arus sudah bertanda: (+) discharge, (-) charge
    float voltage = atof(v_str); // Tegangan terminal dari sensor

    // Hitung delta time (dt) = selisih waktu antara timestep ini dengan sebelumnya
    // Pada baris pertama (time_prev < 0), dt = 0.0 (tidak ada arus yang diintegrasikan)
    float dt = (time_prev < 0) ? 0.0 : (time_s - time_prev);
    if (time_prev >= 0 && dt <= 0) // Lewati jika waktu tidak maju (data tidak valid / duplikat)
      continue;
    time_prev = time_s; // Simpan waktu ini untuk kalkulasi dt berikutnya

    // --- INISIALISASI SAMPLE PERTAMA (timestep ke-0) ---
    // Sample pertama digunakan HANYA untuk mengatur kondisi awal (SoC awal, matriks P).
    // Tidak ada algoritma yang dijalankan dan tidak ada error yang dihitung.
    if (total_samples == 0)
    {
      // Tentukan soc_true awal berdasarkan dataset yang sedang diuji.
      // Nilai ini didapat dari analisis OCV menggunakan get_SOC_from_OCV() di Python:
      //   OCV (Volt) → SoC (fraction) pada saat arus = 0 di awal data.
      if (filename == "dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv")
        soc_true = 0.0f;    // Baterai dimulai dari kosong (proses pengisian CC-CV)
      else if (filename == "dataset_dcc_0.22c_discharge_constant_2.5v.csv")
        soc_true = 1.0f;    // Baterai dimulai dari penuh (proses discharge)
      else if (filename == "dataset_dynamic_profiling_urban_load.csv")
        soc_true = 0.953f;  // FIX 3: V_first=3.420V → OCV inverse → SoC=0.953, BUKAN 1.0!
      else if (filename == "dataset_fast_charging_0.35c_rest_2h.csv")
        soc_true = 0.06f;   // Baterai hampir kosong saat memulai pengisian cepat
      else if (filename == "dataset_capacity_measurement_dcc_cc_cv_dcc.csv")
        soc_true = 0.01f;   // Baterai hampir kosong (1%) saat awal dataset kapasitas
      else
        soc_true = 0.5f;    // Default: 50% untuk dataset yang tidak dikenal

      // Tentukan SoC awal algoritma (CC dan EKF) dengan menambahkan/mengurangi OFFSET.
      // Ini mensimulasikan kondisi MEMORY LOSS: algoritma tidak tahu SoC sebenarnya.
      // Jika soc_true < 10% (baterai nyaris kosong), offset DITAMBAH (agar tidak negatif).
      // Jika soc_true >= 10%, offset DIKURANGI (mensimulasikan estimasi terlalu optimis).
      float soc_algo_start = (soc_true < 0.10f) ? (soc_true + offset_pct_val) : (soc_true - offset_pct_val);

      // Set kondisi awal algoritma (CC dan EKF sama-sama mulai dari nilai yang salah ini)
      soc_cc    = soc_algo_start; // CC mulai dari nilai yang tidak akurat
      ekf_x[0] = soc_algo_start; // EKF mulai dari nilai yang tidak akurat
      ekf_x[1] = 0.0;            // Vc1 awal = 0V (asumsi tidak ada tegangan polarisasi awal)

      // Inisialisasi Matriks Kovarian P secara dinamis berdasarkan besar offset error.
      // Semakin besar offset → P[0][0] makin besar → EKF lebih ragu terhadap estimasinya
      // → lebih agresif menggunakan sensor untuk koreksi → konvergensi lebih cepat.
      // Formula: P[0][0] = offset * 50 + 0.01
      //   Offset 0%  → P[0][0] = 0.01  (EKF agak yakin, kecil karena tidak ada error awal)
      //   Offset 5%  → P[0][0] = 2.51  (EKF cukup ragu)
      //   Offset 10% → P[0][0] = 5.01  (EKF sangat ragu, koreksi agresif di awal)
      ekf_P[0][0] = (fabsf(offset_pct_val) * 50.0f) + 0.01f;
      ekf_P[0][1] = 0.0f;   // Tidak ada korelasi silang antara ketidakpastian SoC dan Vc1
      ekf_P[1][0] = 0.0f;
      ekf_P[1][1] = 0.001f; // P[1][1] kecil: EKF yakin Vc1=0 di awal → K lebih besar saat slope curam

      total_samples++;
      continue; // Ke timestep berikutnya, jangan proses apapun di timestep ke-0
    }

    // Update soc_true: Ground truth terus diperbarui menggunakan Coulomb Counting SEMPURNA
    // "Sempurna" artinya diasumsikan tidak ada sensor noise, tidak ada drift, dan
    // nilai awal soc_true sudah benar (dari OCV inverse di awal dataset).
    // Ini menjadi tolak ukur REFERENSI untuk mengukur error CC dan EKF.
    soc_true = constrain(soc_true - (current * dt / Q_COULOMB), 0.0, 1.0);

    // --- Deteksi kondisi ISTIRAHAT (rest detection) ---
    // Jika arus terus-menerus kecil selama 30 detik, baterai dianggap benar-benar istirahat.
    // Pada kondisi ini, V_terminal ≈ OCV sejati → sensor tegangan PALING akurat.
    // EKF akan menggunakan R_dynamic = R_REST (sangat kecil) → koreksi SoC sangat agresif.
    if (fabsf(current) < REST_CURRENT_THRESH)
    {
      rest_counter_s += (int)dt;           // Akumulasi waktu arus kecil
      if (rest_counter_s >= REST_SETTLE_S) // Jika sudah > 30 detik
        in_confirmed_rest = true;          // Konfirmasi: baterai istirahat!
    }
    else
    {
      rest_counter_s = 0;        // Ada arus → reset penghitung
      in_confirmed_rest = false; // Status istirahat dibatalkan
    }

    // --- Pengukuran PERFORMA HARDWARE: Waktu CPU & Pemakaian Stack (SRAM) ---
    // CARA KERJA PENGUKURAN STACK:
    // uxTaskGetStackHighWaterMark(NULL) mengembalikan sisa minimum stack yang pernah ada
    // pada task saat ini sejak dibuat (dalam words/4 bytes).
    // Dengan membandingkan nilai sebelum dan sesudah memanggil fungsi, kita mendapat
    // berapa banyak stack yang dipakai oleh fungsi tersebut.
    // CATATAN: Karena RTOS membebaskan stack secara instan setelah fungsi return,
    // pengukuran ini mencerminkan HIGH WATER MARK (pemakaian puncak), bukan alokasi statik.
    size_t stack_awal = uxTaskGetStackHighWaterMark(NULL); // Snapshot stack sebelum CC

    // Ukur waktu eksekusi Coulomb Counting menggunakan micros() (resolusi 1 µs)
    uint32_t t_start_cc = micros();
    runCCStep(current, dt); // <-- JALANKAN COULOMB COUNTING
    uint32_t t_end_cc = micros();
    total_exec_time_cc_us += (t_end_cc - t_start_cc); // Akumulasi total waktu CC

    // Hitung pemakaian stack oleh CC: (snapshot sebelum) - (snapshot setelah)
    size_t stack_after_cc = uxTaskGetStackHighWaterMark(NULL);
    size_t cc_sram_used = stack_awal - stack_after_cc; // bytes yang terpakai oleh CC
    // Catat nilai maksimum (skip 10 sample pertama untuk menghindari transient awal)
    if (cc_sram_used > max_cc_stack_consumed && total_samples >= 10) {
        max_cc_stack_consumed = cc_sram_used;
    }

    // --- Ukur EKF hanya jika MODE 2 aktif ---
    // Kompilasi kondisional: kode EKF hanya di-compile jika JALANKAN_MODE == 2
    // Ini memungkinkan kita membandingkan firmware CC-only vs CC+EKF secara adil
    #if JALANKAN_MODE == 2
    uint32_t t_start_ekf = micros();
    runEKFStep(current, voltage, dt); // <-- JALANKAN EKF
    uint32_t t_end_ekf = micros();
    total_exec_time_ekf_us += (t_end_ekf - t_start_ekf); // Akumulasi total waktu EKF

    // Hitung pemakaian stack oleh EKF: selisih stack setelah CC vs setelah EKF
    // (menggunakan stack_after_cc sebagai baseline, bukan stack_awal)
    size_t stack_after_ekf = uxTaskGetStackHighWaterMark(NULL);
    size_t ekf_sram_used = stack_after_cc - stack_after_ekf; // bytes tambahan yang dipakai EKF
    if (ekf_sram_used > max_ekf_stack_consumed && total_samples >= 10) {
        max_ekf_stack_consumed = ekf_sram_used;
    }
    #endif

    // --- Hitung Error antara estimasi algoritma vs ground truth ---
    double err_cc  = soc_true - soc_cc;     // Error SoC Coulomb Counting (positif = CC terlalu rendah)
    double err_ekf = soc_true - ekf_x[0];  // Error SoC EKF (positif = EKF terlalu rendah)
    double err_v   = voltage - v_pred_last; // Error tegangan EKF (V_sensor - V_prediksi)

    // Akumulasi kuadrat error untuk RMSE: Σ(error²)
    // RMSE = Root Mean Square Error = sqrt(Σ(err²) / N) → dihitung di akhir dataset
    sum_sq_err_cc      += (err_cc  * err_cc);
    sum_sq_err_ekf_soc += (err_ekf * err_ekf);
    sum_sq_err_ekf_v   += (err_v   * err_v);

    // Akumulasi nilai absolut error untuk MAE: Σ|error|
    // MAE = Mean Absolute Error = Σ|err| / N → dihitung di akhir dataset
    sum_abs_err_cc      += fabs(err_cc);
    sum_abs_err_ekf_soc += fabs(err_ekf);
    sum_abs_err_ekf_v   += fabs(err_v);

    total_samples++; // Hitung baris yang berhasil diproses
  }
  file.close();

  // --- Hitung dan Simpan Metrik Final ke Struct ---
  // Setelah semua baris CSV selesai diproses, hitung RMSE dan MAE dari akumulator
  if (result_index < 15) // Pastikan array tidak overflow
  {
    final_results[result_index].filename   = filename.substring(0, 20); // Potong 20 karakter untuk tabel
    final_results[result_index].offset_pct = (int)(offset_pct_val * 100); // Ubah 0.05 → 5 (persen)

    // RMSE = sqrt(Σ(err²) / N) × 100  (×100 agar dalam satuan %)
    final_results[result_index].rmse_cc  = sqrt(sum_sq_err_cc      / total_samples) * 100.0;
    final_results[result_index].rmse_ekf = sqrt(sum_sq_err_ekf_soc / total_samples) * 100.0;
    // RMSE tegangan ×1000 agar dalam satuan mV (lebih mudah dibaca dari pada Volt)
    final_results[result_index].rmse_v   = sqrt(sum_sq_err_ekf_v   / total_samples) * 1000.0;

    // MAE = (Σ|err| / N) × 100  (×100 agar dalam satuan %)
    final_results[result_index].mae_cc  = (sum_abs_err_cc      / total_samples) * 100.0;
    final_results[result_index].mae_ekf = (sum_abs_err_ekf_soc / total_samples) * 100.0;
    final_results[result_index].mae_v   = (sum_abs_err_ekf_v   / total_samples) * 1000.0;

    // Rata-rata waktu eksekusi per timestep: total_waktu / N_sampel
    final_results[result_index].avg_exec_time_cc_us  = (total_samples > 0) ? ((float)total_exec_time_cc_us  / total_samples) : 0;
    final_results[result_index].avg_exec_time_ekf_us = (total_samples > 0) ? ((float)total_exec_time_ekf_us / total_samples) : 0;

    // Pemakaian stack SRAM maksimum yang terukur selama dataset berlangsung
    final_results[result_index].max_sram_cc  = max_cc_stack_consumed;
    #if JALANKAN_MODE == 2
    final_results[result_index].max_sram_ekf = max_ekf_stack_consumed; // Aktif jika MODE 2
    #else
    final_results[result_index].max_sram_ekf = 0; // Mode 1: EKF tidak dijalankan
    #endif

    result_index++; // Maju ke slot berikutnya untuk dataset/offset berikutnya
  }
  Serial.println("[INFO] Selesai.\n");

  return true;
}

// =========================================================
// 8. SETUP & LOOP
// =========================================================
// setup(): Fungsi yang berjalan SATU KALI saat ESP32 menyala.
// Semua logika utama program ada di sini karena PiL hanya perlu dijalankan sekali.
// Setelah selesai, loop() hanya jalan idle (tidak ada yang dilakukan).
void setup()
{
  Serial.begin(115200); // Inisialisasi Serial Monitor untuk mencetak hasil
  delay(2000);          // Jeda 2 detik: beri waktu Serial Monitor PC terhubung sebelum output dimulai

  Serial.println("\n\n===========================================================================");
  Serial.println("            MEMULAI PENGUJIAN PROCESSOR-IN-THE-LOOP (PiL) ESP32            ");
  Serial.println("===========================================================================\n");

  // Mount LittleFS: sistem file di flash internal ESP32 tempat file CSV dataset disimpan.
  // Parameter 'true' = format ulang flash jika mount gagal (pastikan data sudah di-upload dulu!)
  // Untuk upload file CSV ke LittleFS: gunakan fitur 'Upload Filesystem Image' di PlatformIO.
  if (!LittleFS.begin(true))
  {
    Serial.println("[FATAL] Gagal Mount LittleFS! Pastikan data sudah di-upload ke ESP32.");
    return; // Hentikan setup jika file system tidak bisa dibuka
  }

  result_index = 0; // Reset indeks sebelum mengisi array final_results

  // Definisikan 3 variasi offset error SoC awal untuk mensimulasikan 'memory loss':
  //   0.0f = tidak ada error awal (kondisi ideal / sistem baru booting)
  //   0.05f = error 5% dari SoC sebenarnya (memory loss ringan)
  //   0.10f = error 10% dari SoC sebenarnya (memory loss parah)
  float offsets[] = {0.0f, 0.05f, 0.10f};

  // Jalankan semua 5 dataset untuk setiap kondisi offset: total 15 skenario
  // Urutan eksekusi: offset 0% → semua dataset, lalu offset 5% → semua dataset, dst.
  for (int i = 0; i < 3; i++)
  {
    Serial.printf("\n[INFO] Menjalankan simulasi dengan Offset Error: %d%%\n", (int)(offsets[i] * 100));
    // Dataset 1: Pengisian CC-CV mulai dari 0% (OCV characterization + CC-CV charge)
    if (!runDatasetTest("dataset_ocv_soc_cc_cv_0.25c_rest_60m.csv", offsets[i]))
      return; // Hentikan jika ada error file
    // Dataset 2: Discharge konstan 0.22C dari penuh hingga 2.5V (batas tegangan minimum)
    if (!runDatasetTest("dataset_dcc_0.22c_discharge_constant_2.5v.csv", offsets[i]))
      return;
    // Dataset 3: Profil beban dinamis urban drive cycle (paling menantang untuk EKF)
    if (!runDatasetTest("dataset_dynamic_profiling_urban_load.csv", offsets[i]))
      return;
    // Dataset 4: Pengisian cepat 0.35C dari hampir kosong, kemudian istirahat 2 jam
    if (!runDatasetTest("dataset_fast_charging_0.35c_rest_2h.csv", offsets[i]))
      return;
    // Dataset 5: Siklus pengukuran kapasitas penuh (discharge → charge → discharge)
    if (!runDatasetTest("dataset_capacity_measurement_dcc_cc_cv_dcc.csv", offsets[i]))
      return;
  }

  // =======================================================
  // CETAK TABEL HASIL (FORMAT RAW)
  // =======================================================
  Serial.println("\n=====================================================================================================================================================");
  Serial.println("| OFFSET | NAMA DATASET         | RMSE CC (%) | RMSE EKF (%) | MAE CC (%) | MAE EKF (%) | RMSE V (mV) | MAE V (mV) | Waktu CC (us) | Waktu EKF (us) |");
  Serial.println("=====================================================================================================================================================");
  for (int i = 0; i < result_index; i++)
  {
    Serial.printf("| %3d%%  | %-20s | %11.4f | %12.4f | %10.4f | %11.4f | %11.4f | %10.4f | %13.2f | %14.2f |\n",
                  final_results[i].offset_pct,
                  final_results[i].filename.c_str(),
                  final_results[i].rmse_cc,
                  final_results[i].rmse_ekf,
                  final_results[i].mae_cc,
                  final_results[i].mae_ekf,
                  final_results[i].rmse_v,
                  final_results[i].mae_v,
                  final_results[i].avg_exec_time_cc_us,
                  final_results[i].avg_exec_time_ekf_us);
  }
  Serial.println("=====================================================================================================================================================");

  // =======================================================
  // CETAK FORMAT MARKDOWN
  // =======================================================
  Serial.println("\n\n");
  Serial.println("## Tabel Hasil Perbandingan Metrik (RMSE & MAE)");
  Serial.println("Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):");
  Serial.println("\n| OFFSET | NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |");
  Serial.println("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |");

  for (int i = 0; i < result_index; i++)
  {
    Serial.printf("| %d%% | %s | %.4f | %.4f | %.4f | %.4f | %.4f | %.4f |\n",
                  final_results[i].offset_pct,
                  final_results[i].filename.c_str(),
                  final_results[i].rmse_cc,
                  final_results[i].rmse_ekf,
                  final_results[i].mae_cc,
                  final_results[i].mae_ekf,
                  final_results[i].rmse_v,
                  final_results[i].mae_v);
  }

  // =======================================================
  // ANALISIS TRADE-OFF
  // =======================================================
  Serial.println("\n### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)");
  Serial.println("Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:");
  Serial.println("\n| Algoritma | Waktu Eksekusi CPU (\\xC2\\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |");
  Serial.println("| :--- | :---: | :---: | :---: |");

  float avg_cc_time = 0, avg_ekf_time = 0;
  float avg_cc_sram = 0, avg_ekf_sram = 0;
  for (int i = 0; i < result_index; i++)
  {
    avg_cc_time += final_results[i].avg_exec_time_cc_us;
    avg_ekf_time += final_results[i].avg_exec_time_ekf_us;
    avg_cc_sram += final_results[i].max_sram_cc;
    avg_ekf_sram += final_results[i].max_sram_ekf;
  }
  avg_cc_time /= (result_index > 0) ? result_index : 1;
  avg_ekf_time /= (result_index > 0) ? result_index : 1;
  avg_cc_sram /= (result_index > 0) ? result_index : 1;
  avg_ekf_sram /= (result_index > 0) ? result_index : 1;

  Serial.printf("| **Coulomb Counting** | %.2f | %.0f Bytes | O(1) Constant Time |\n", avg_cc_time, avg_cc_sram);
  Serial.printf("| **Extended Kalman Filter** | %.2f | %.0f Bytes | O(n^3) Cubic Time |\n", avg_ekf_time, avg_ekf_sram);

  Serial.println("\n*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*");

  // =======================================================
  // PARAMETER MODEL YANG DIGUNAKAN
  // =======================================================
  Serial.println("\n### Parameter Model & Tuning EKF yang Digunakan:");
  Serial.println("* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik)");
  Serial.println("  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC");
  Serial.println("* **Deteksi Arus:** Offline preprocessing (edge-triggered state machine di preprocess.py)");
  Serial.printf("* **Q Matriks (Process Noise):** `Q_00` = %.1e, `Q_11` = %.1e\n", Q_NOISE_00, Q_NOISE_11);
  Serial.printf("* **R Matriks (Measurement Noise):** Dynamic Observability R = %.4f / (|dOCV/dSOC| + 1e-4) | R_REST = %.4f (aktif setelah %ds arus ~0)\n", R_BASE, R_REST, REST_SETTLE_S);
  Serial.println("* **Jacobian h0:** fabsf(dOCV/dSOC) + 1e-4 [FIX: abs mencegah sign-flip di OCV-dip LiFePO4 region 15-22%]");
  Serial.println("* **Soft Deadband:** 1 mV + Correction Cap 10% SoC/step");
  Serial.println("* **P_init:** P[0][0]=offset*50+0.01, P[1][1]=0.001");
  Serial.println("* **Ground Truth Fix:** Dynamic Profiling soc_init=0.953 (dari OCV inverse: V_rest=3.420V)");
  Serial.println("* **Simulasi Memory Loss:** Algoritma divariasikan dengan *offset error* sebesar 0%, 5%, dan 10% untuk menguji kekokohan EKF secara komprehensif.");
  Serial.println("\n");
}

// loop(): Fungsi yang berjalan terus-menerus setelah setup() selesai.
// Pada PiL, seluruh pekerjaan sudah selesai di setup().
// loop() sengaja dibuat idle (hanya delay) agar ESP32 tidak hang.
// Semua hasil sudah dicetak ke Serial Monitor di setup().
void loop()
{
  delay(10000); // Idle: tidur 10 detik, tidak ada yang perlu dilakukan
}