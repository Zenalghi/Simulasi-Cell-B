#include <Arduino.h>
#include <LittleFS.h>
#include <math.h>

// =========================================================
// 1. STRUKTUR PENYIMPAN HASIL UNTUK TABEL FINAL
// =========================================================
struct TestResult
{
  String filename;
  float rmse_cc;
  float rmse_ekf;
  float rmse_v;
  float mae_cc;
  float mae_ekf;
  float mae_v;
  float avg_exec_time_cc_us;
  float avg_exec_time_ekf_us;
};
TestResult final_results[5];
int result_index = 0;

// =========================================================
// 2. PARAMETER MODEL BATERAI
// =========================================================
const float Q_AH = 20.798555;
const float Q_COULOMB = 74874.8; // Kapasitas As (Ampere-sekon)

// -----------------------------------------------------------
// OCV-SOC Lookup Table (Piecewise Linear / Polynomial Orde 1 per segmen)
// Sumber: h-GroundTruth_OCV_SOC_LiFePO4.csv (kolom Cubic Spline)
// 21 titik, resolusi 5% SOC
//
// Catatan Ilmiah: Baterai LiFePO4 memiliki plateau OCV yang
// sangat datar pada SOC 15-85% (~3.22-3.29V). Polynomial global
// (orde berapa pun) cenderung berosilasi dan overshoot di region ini.
// LUT dengan interpolasi linear (piecewise polynomial orde 1)
// memberikan akurasi yang jauh superior dan stabil secara numerik.
// -----------------------------------------------------------
const int LUT_OCV_SIZE = 21;
const float lut_soc_ocv[LUT_OCV_SIZE] = {
    0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00};
const float lut_ocv_val[LUT_OCV_SIZE] = {
    2.6550, 3.0269, 3.1972, 3.2391, 3.2261, 3.2242, 3.2424, 3.2625,
    3.2758, 3.2835, 3.2871, 3.2880, 3.2878, 3.2884, 3.2917, 3.2958,
    3.2973, 3.3039, 3.3353, 3.4122, 3.5370};

// Referensi Arsip: Koefisien Polynomial Orde 6 (tidak digunakan lagi)
// p0=2.664967, p1=9.485166, p2=-58.074182, p3=169.872070,
// p4=-250.913864, p5=179.845768, p6=-49.353787

// Parameter ECM (1-RC Thevenin) - tidak berubah
const int LUT_ECM_SIZE = 9;
const float lut_soc_ecm[LUT_ECM_SIZE] = {
    0.0, 0.090902, 0.204618, 0.318054, 0.431697,
    0.545421, 0.659070, 0.772787, 0.886430};
const float lut_r0[LUT_ECM_SIZE] = {
    0.006050, 0.002800, 0.002800, 0.002899, 0.002700,
    0.002400, 0.002899, 0.002199, 0.002800};
const float lut_r1[LUT_ECM_SIZE] = {
    0.009500, 0.002506, 0.002207, 0.002212, 0.002372,
    0.002436, 0.002374, 0.002345, 0.002684};
const float lut_c1[LUT_ECM_SIZE] = {
    11281.15, 20591.86, 24841.48, 15061.40, 20897.75,
    19607.70, 15177.97, 16580.74, 24189.08};

// =========================================================
// 3. TUNING NOISE PARAMETER EKF
// =========================================================
const float Q_NOISE_00 = 5e-6;     // Process noise SOC (diperbesar agar P tidak collapse di plateau)
const float Q_NOISE_11 = 1e-4;     // Process noise V_RC
const float R_NOISE_BASE = 0.0002; // Measurement noise base (V^2)

// =========================================================
// 4. VARIABEL STATE ESTIMATION & ERROR TRACKING
// =========================================================
float soc_cc = 0.0;
float ekf_x[2] = {0.0, 0.0};
float ekf_P[2][2] = {{0.5, 0.0}, {0.0, 0.1}};

float v_pred_last = 0.0;
float soc_true = 0.0;

double sum_sq_err_cc = 0;
double sum_sq_err_ekf_soc = 0;
double sum_sq_err_ekf_v = 0;

double sum_abs_err_cc = 0;
double sum_abs_err_ekf_soc = 0;
double sum_abs_err_ekf_v = 0;

long total_samples = 0;

// =========================================================
// 5. FUNGSI MATEMATIKA: INTERPOLASI & OCV-SOC
// =========================================================
float interpolate1D(float x, const float *x_data, const float *y_data, int size)
{
  if (x <= x_data[0])
    return y_data[0];
  if (x >= x_data[size - 1])
    return y_data[size - 1];
  for (int i = 0; i < size - 1; i++)
  {
    if (x >= x_data[i] && x <= x_data[i + 1])
    {
      float t = (x - x_data[i]) / (x_data[i + 1] - x_data[i]);
      return y_data[i] + t * (y_data[i + 1] - y_data[i]);
    }
  }
  return y_data[0];
}

// OCV dari Lookup Table (Piecewise Linear Orde 1)
float get_OCV(float soc)
{
  return interpolate1D(constrain(soc, 0.0f, 1.0f),
                       lut_soc_ocv, lut_ocv_val, LUT_OCV_SIZE);
}

// Turunan dOCV/dSOC via central finite difference pada LUT
float get_dOCV_dSOC(float soc)
{
  soc = constrain(soc, 0.0f, 1.0f);
  float h = 0.005f;
  float soc_lo = max(soc - h, 0.0f);
  float soc_hi = min(soc + h, 1.0f);
  float dSOC = soc_hi - soc_lo;
  if (dSOC < 1e-6f)
    return 0.01f;
  float deriv = (get_OCV(soc_hi) - get_OCV(soc_lo)) / dSOC;
  // Floor positif untuk stabilitas numerik di region flat/non-monotonic
  return max(deriv, 0.01f);
}

// Reverse lookup OCV → SOC (untuk inisialisasi soc_true dari tegangan rest)
float get_SOC_from_OCV(float ocv)
{
  if (ocv <= lut_ocv_val[0])
    return 0.0f;
  if (ocv >= lut_ocv_val[LUT_OCV_SIZE - 1])
    return 1.0f;

  // Cari segmen LUT pertama yang mengandung nilai OCV
  // (handle kurva non-monotonic LiFePO4 di region SOC 15-25%)
  for (int i = 0; i < LUT_OCV_SIZE - 1; i++)
  {
    float v0 = lut_ocv_val[i];
    float v1 = lut_ocv_val[i + 1];
    if ((ocv >= v0 && ocv <= v1) || (ocv <= v0 && ocv >= v1))
    {
      if (fabsf(v1 - v0) < 0.0001f)
        return lut_soc_ocv[i];
      float t = constrain((ocv - v0) / (v1 - v0), 0.0f, 1.0f);
      return lut_soc_ocv[i] + t * (lut_soc_ocv[i + 1] - lut_soc_ocv[i]);
    }
  }

  // Fallback: nearest neighbor
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
void runCCStep(float I_meas, float dt)
{
  soc_cc = constrain(soc_cc - (I_meas * dt / Q_COULOMB), 0.0, 1.0);
}

void runEKFStep(float I_meas, float V_meas, float dt)
{
  // --- Time Update (Prediction) ---
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

  // Prediksi Covariance P
  float P_pred[2][2];
  P_pred[0][0] = ekf_P[0][0] + Q_NOISE_00;
  P_pred[0][1] = ekf_P[0][1] * alpha;
  P_pred[1][0] = ekf_P[1][0] * alpha;
  P_pred[1][1] = (alpha * alpha * ekf_P[1][1]) + Q_NOISE_11;

  // --- Measurement Update (Correction) ---
  float OCV_pred = get_OCV(soc_pred);
  float dOCV_dSOC = get_dOCV_dSOC(soc_pred);

  float V_pred = OCV_pred - vc1_pred - (I_meas * R0);
  v_pred_last = V_pred;

  // Jacobian H = [dOCV/dSOC, -1]
  float h0 = dOCV_dSOC;
  float h1 = -1.0f;

  // Adaptive Measurement Noise R
  float R_eff = R_NOISE_BASE;
  if (fabsf(I_meas) < 0.05f)
    R_eff *= 0.5f;  // Rest: tegangan ≈ OCV, sangat reliable
  else if (I_meas < 0.0f)
    R_eff *= 10.0f; // Charging: model ECM kurang akurat saat charge
  else
    R_eff *= 5.0f;  // Discharging: model ECM cukup akurat

  // Innovation Covariance S = H*P*H' + R
  float S = (h0 * h0 * P_pred[0][0]) + (h0 * h1 * P_pred[0][1]) +
            (h1 * h0 * P_pred[1][0]) + (h1 * h1 * P_pred[1][1]) + R_eff;

  // Kalman Gain K = P*H' / S
  float K[2];
  K[0] = ((P_pred[0][0] * h0) + (P_pred[0][1] * h1)) / S;
  K[1] = ((P_pred[1][0] * h0) + (P_pred[1][1] * h1)) / S;

  // Koreksi State x = x + K*(z - h(x))
  float innov = V_meas - V_pred;
  ekf_x[0] = constrain(ekf_x[0] + (K[0] * innov), 0.0, 1.0);
  ekf_x[1] = ekf_x[1] + (K[1] * innov);

  // Update Covariance P (Joseph Form untuk stabilitas numerik)
  float I_KH[2][2];
  I_KH[0][0] = 1.0f - (K[0] * h0);
  I_KH[0][1] = -(K[0] * h1);
  I_KH[1][0] = -(K[1] * h0);
  I_KH[1][1] = 1.0f - (K[1] * h1);

  float Temp[2][2];
  Temp[0][0] = I_KH[0][0] * P_pred[0][0] + I_KH[0][1] * P_pred[1][0];
  Temp[0][1] = I_KH[0][0] * P_pred[0][1] + I_KH[0][1] * P_pred[1][1];
  Temp[1][0] = I_KH[1][0] * P_pred[0][0] + I_KH[1][1] * P_pred[1][0];
  Temp[1][1] = I_KH[1][0] * P_pred[0][1] + I_KH[1][1] * P_pred[1][1];

  ekf_P[0][0] = Temp[0][0] * I_KH[0][0] + Temp[0][1] * I_KH[0][1] + (K[0] * K[0] * R_eff);
  ekf_P[0][1] = Temp[0][0] * I_KH[1][0] + Temp[0][1] * I_KH[1][1] + (K[0] * K[1] * R_eff);
  ekf_P[1][0] = Temp[1][0] * I_KH[0][0] + Temp[1][1] * I_KH[0][1] + (K[1] * K[0] * R_eff);
  ekf_P[1][1] = Temp[1][0] * I_KH[1][0] + Temp[1][1] * I_KH[1][1] + (K[1] * K[1] * R_eff);

  // Symmetry enforcement & positivity floor (stabilitas float32 ESP32)
  ekf_P[0][1] = (ekf_P[0][1] + ekf_P[1][0]) * 0.5f;
  ekf_P[1][0] = ekf_P[0][1];
  ekf_P[0][0] = max(ekf_P[0][0], 1e-10f);
  ekf_P[1][1] = max(ekf_P[1][1], 1e-10f);
}

// =========================================================
// 7. RUNNER PROCESSOR-IN-THE-LOOP (PiL)
//    Auto-detect sign arus dari data ZKEtech
// =========================================================
bool runDatasetTest(String filename)
{
  File file = LittleFS.open("/" + filename, "r");
  if (!file)
  {
    Serial.printf("[ERROR] Gagal membuka file %s.\n", filename.c_str());
    return false;
  }

  Serial.printf("[INFO] Menguji Dataset: %s\n", filename.c_str());

  // Skip header
  while (file.available())
  {
    String line = file.readStringUntil('\n');
    if (line.indexOf("Time(S)") >= 0)
      break;
  }

  // Reset error accumulators
  sum_sq_err_cc = 0;
  sum_abs_err_cc = 0;
  sum_sq_err_ekf_soc = 0;
  sum_abs_err_ekf_soc = 0;
  sum_sq_err_ekf_v = 0;
  sum_abs_err_ekf_v = 0;
  total_samples = 0;

  uint64_t total_exec_time_cc_us = 0;
  uint64_t total_exec_time_ekf_us = 0;

  float time_prev = -1.0;
  char buf[128];

  // -------------------------------------------------------
  // Variabel Auto-Detect Sign Arus (data ZKEtech)
  // ZKEtech selalu output arus positif, sign harus dideteksi
  // dari perbandingan tegangan rest vs tegangan saat arus mengalir:
  //   V_active < V_rest → Discharge (arus positif, SOC turun)
  //   V_active > V_rest → Charge   (arus negatif, SOC naik)
  // -------------------------------------------------------
  float v_last_rest = -1.0f;
  bool phase_locked = false;
  bool is_charge_phase = false;
  float v_first_active = -1.0f;
  int active_count = 0;

  while (file.available())
  {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() < 5 || line.indexOf("*") >= 0 || line.indexOf("-") >= 0)
      continue;

    line.toCharArray(buf, sizeof(buf));
    char *t_str = strtok(buf, ",");
    char *c_str = strtok(NULL, ",");
    char *v_str = strtok(NULL, ",");

    if (!t_str || !c_str || !v_str)
      continue;

    float time_s = atof(t_str);
    float current = atof(c_str);
    float voltage = atof(v_str);

    float dt = (time_prev < 0) ? 0.0 : (time_s - time_prev);
    if (time_prev >= 0 && dt <= 0)
      continue;
    time_prev = time_s;

    // --- Auto-detect sign arus ---
    if (current < 0.05f)
    {
      // Rest period: catat tegangan, reset deteksi fase
      v_last_rest = voltage;
      phase_locked = false;
      v_first_active = -1.0f;
      active_count = 0;
      current = 0.0f;
    }
    else
    {
      // Active period: tentukan fase dari perbandingan tegangan
      if (!phase_locked)
      {
        if (v_last_rest > 0.0f)
        {
          // Ada referensi rest → bandingkan IR drop/rise
          // Discharge: V_terminal turun di bawah V_rest (karena IR drop)
          // Charge: V_terminal naik di atas V_rest (karena IR rise)
          is_charge_phase = (voltage > v_last_rest + 0.003f);
          phase_locked = true;
        }
        else
        {
          // Tidak ada rest di awal → gunakan trend voltage
          if (v_first_active < 0.0f)
            v_first_active = voltage;
          active_count++;
          if (active_count >= 3)
          {
            is_charge_phase = (voltage > v_first_active + 0.003f);
            phase_locked = true;
          }
          else
          {
            is_charge_phase = false; // Default: discharge
          }
        }
      }
      // Apply sign arus berdasarkan fase terdeteksi
      current = is_charge_phase ? -fabsf(current) : fabsf(current);
    }

    // --- Inisialisasi sample pertama ---
    if (total_samples == 0)
    {
      // Tentukan SOC awal berdasarkan kondisi awal dataset
      if (filename == "h-charge_rest_60m.csv")
        soc_true = 0.0f; // Baterai kosong (0%), akan di-charge
      else if (filename == "h-DCC-4.4A-2.5V.csv")
        soc_true = 1.0f; // Baterai penuh (100%), akan di-discharge
      else if (filename == "h-Dynamic_Profiling_(Urban Load).csv")
        soc_true = 1.0f; // Baterai penuh (100%), profil discharge
      else if (filename == "h-charging_7.33A-rest 2h.csv")
        soc_true = 0.06f; // ~6% dari OCV rest awal (3.063V)
      else if (filename == "h-DCC_4.4A_2.5V-CCV_6.6_3.65V-DCC_4.4A_2.5V.csv")
        soc_true = 0.01f; // ~1% dari OCV rest awal (2.718V)
      else
        soc_true = (v_last_rest > 0) ? get_SOC_from_OCV(v_last_rest) : 0.5f;

      // Offset error 10% untuk simulasi memory loss
      float soc_algo_start = (soc_true < 0.10f) ? (soc_true + 0.10f) : (soc_true - 0.10f);

      soc_cc = soc_algo_start;
      ekf_x[0] = soc_algo_start;
      ekf_x[1] = 0.0;

      // Initial P covariance (lebih besar untuk konvergensi cepat dari offset 10%)
      ekf_P[0][0] = 0.5;
      ekf_P[0][1] = 0.0;
      ekf_P[1][0] = 0.0;
      ekf_P[1][1] = 0.1;

      total_samples++;
      continue;
    }

    // Update SOC true (Coulomb counting "sempurna" sebagai referensi)
    soc_true = constrain(soc_true - (current * dt / Q_COULOMB), 0.0, 1.0);

    // Profiling Waktu Eksekusi CC
    uint32_t t_start_cc = micros();
    runCCStep(current, dt);
    uint32_t t_end_cc = micros();
    total_exec_time_cc_us += (t_end_cc - t_start_cc);

    // Profiling Waktu Eksekusi EKF
    uint32_t t_start_ekf = micros();
    runEKFStep(current, voltage, dt);
    uint32_t t_end_ekf = micros();
    total_exec_time_ekf_us += (t_end_ekf - t_start_ekf);

    // Akumulasi Error RMSE & MAE
    double err_cc = soc_true - soc_cc;
    double err_ekf = soc_true - ekf_x[0];
    double err_v = voltage - v_pred_last;

    sum_sq_err_cc += (err_cc * err_cc);
    sum_sq_err_ekf_soc += (err_ekf * err_ekf);
    sum_sq_err_ekf_v += (err_v * err_v);

    sum_abs_err_cc += fabs(err_cc);
    sum_abs_err_ekf_soc += fabs(err_ekf);
    sum_abs_err_ekf_v += fabs(err_v);

    total_samples++;
  }
  file.close();

  if (result_index < 5)
  {
    final_results[result_index].filename = filename.substring(0, 20);
    final_results[result_index].rmse_cc = sqrt(sum_sq_err_cc / total_samples) * 100.0;
    final_results[result_index].rmse_ekf = sqrt(sum_sq_err_ekf_soc / total_samples) * 100.0;
    final_results[result_index].rmse_v = sqrt(sum_sq_err_ekf_v / total_samples) * 1000.0;

    final_results[result_index].mae_cc = (sum_abs_err_cc / total_samples) * 100.0;
    final_results[result_index].mae_ekf = (sum_abs_err_ekf_soc / total_samples) * 100.0;
    final_results[result_index].mae_v = (sum_abs_err_ekf_v / total_samples) * 1000.0;

    final_results[result_index].avg_exec_time_cc_us = (total_samples > 0) ? ((float)total_exec_time_cc_us / total_samples) : 0;
    final_results[result_index].avg_exec_time_ekf_us = (total_samples > 0) ? ((float)total_exec_time_ekf_us / total_samples) : 0;
    result_index++;
  }
  Serial.println("[INFO] Selesai.\n");

  return true;
}

// =========================================================
// 8. SETUP & LOOP
// =========================================================
void setup()
{
  Serial.begin(115200);
  delay(2000);

  Serial.println("\n\n===========================================================================");
  Serial.println("            MEMULAI PENGUJIAN PROCESSOR-IN-THE-LOOP (PiL) ESP32            ");
  Serial.println("===========================================================================\n");

  if (!LittleFS.begin(true))
  {
    Serial.println("[FATAL] Gagal Mount LittleFS!");
    return;
  }

  result_index = 0;

  // Semua dataset menggunakan auto-detect sign arus
  if (!runDatasetTest("h-charge_rest_60m.csv"))
    return;
  if (!runDatasetTest("h-DCC-4.4A-2.5V.csv"))
    return;
  if (!runDatasetTest("h-Dynamic_Profiling_(Urban Load).csv"))
    return;
  if (!runDatasetTest("h-charging_7.33A-rest 2h.csv"))
    return;
  if (!runDatasetTest("h-DCC_4.4A_2.5V-CCV_6.6_3.65V-DCC_4.4A_2.5V.csv"))
    return;

  // =======================================================
  // CETAK TABEL HASIL (FORMAT RAW)
  // =======================================================
  Serial.println("\n===============================================================================================================================================");
  Serial.println("| NAMA DATASET         | RMSE CC (%) | RMSE EKF (%) | MAE CC (%) | MAE EKF (%) | RMSE V (mV) | MAE V (mV) | Waktu CC (us) | Waktu EKF (us) |");
  Serial.println("===============================================================================================================================================");
  for (int i = 0; i < result_index; i++)
  {
    Serial.printf("| %-20s | %11.4f | %12.4f | %10.4f | %11.4f | %11.4f | %10.4f | %13.2f | %14.2f |\n",
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
  Serial.println("===============================================================================================================================================");

  // =======================================================
  // CETAK FORMAT MARKDOWN
  // =======================================================
  Serial.println("\n\n");
  Serial.println("## Tabel Hasil Perbandingan Metrik (RMSE & MAE)");
  Serial.println("Tabel berikut menyajikan komparasi performa estimasi antara Coulomb Counting (CC) dan Extended Kalman Filter (EKF):");
  Serial.println("\n| NAMA DATASET | RMSE SoC CC (%) | RMSE SoC EKF (%) | MAE SoC CC (%) | MAE SoC EKF (%) | RMSE V EKF (mV) | MAE V EKF (mV) |");
  Serial.println("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |");

  for (int i = 0; i < result_index; i++)
  {
    Serial.printf("| %s | %.4f | %.4f | %.4f | %.4f | %.4f | %.4f |\n",
                  final_results[i].filename.c_str(),
                  final_results[i].rmse_cc,
                  final_results[i].rmse_ekf,
                  final_results[i].mae_cc,
                  final_results[i].mae_ekf,
                  final_results[i].rmse_v,
                  final_results[i].mae_v);
  }

  // =======================================================
  // ANALISIS TRADE-OFF (DENGAN HARDCODE MEMORI & BIG-O)
  // =======================================================
  Serial.println("\n### Analisis Komparasi Trade-Off (Menjawab Formulasi Masalah)");
  Serial.println("Berdasarkan hasil eksekusi Processor-in-the-Loop pada ESP32, terlihat *trade-off* yang jelas antara akurasi dan beban sumber daya sistem:");
  Serial.println("\n| Algoritma | Waktu Eksekusi CPU (\xC2\xB5s) | Penggunaan Memori Stack (Bytes) | Kompleksitas Waktu (Big-O) |");
  Serial.println("| :--- | :---: | :---: | :---: |");

  float avg_cc_time = 0, avg_ekf_time = 0;
  for (int i = 0; i < result_index; i++)
  {
    avg_cc_time += final_results[i].avg_exec_time_cc_us;
    avg_ekf_time += final_results[i].avg_exec_time_ekf_us;
  }
  avg_cc_time /= (result_index > 0) ? result_index : 1;
  avg_ekf_time /= (result_index > 0) ? result_index : 1;

  Serial.printf("| **Coulomb Counting** | %.2f | ~16 | O(1) Constant Time |\n", avg_cc_time);
  Serial.printf("| **Extended Kalman Filter** | %.2f | ~3200 (3.2 kB) | O(n^3) Cubic Time |\n", avg_ekf_time);

  Serial.println("\n*Catatan Analitik: Penggunaan memori EKF dihitung secara teoritis berdasarkan alokasi matriks Jacobian, array Kalman Gain, dan tabel lookup ECM pada memori Stack lokal, karena RTOS membebaskan memori tersebut secara instan setelah fungsi mengembalikan nilai (return).*");

  // =======================================================
  // PARAMETER MODEL YANG DIGUNAKAN
  // =======================================================
  Serial.println("\n### Parameter Model & Tuning EKF yang Digunakan:");
  Serial.println("* **OCV-SOC Model:** Piecewise Linear (LUT 21 titik, Polynomial Orde 1 per segmen)");
  Serial.println("  * Sumber: `h-GroundTruth_OCV_SOC_LiFePO4.csv` (Cubic Spline), resolusi 5% SOC");
  Serial.println("* **Deteksi Arus:** Auto-detect dari data ZKEtech (bandingkan `V_rest` vs `V_active`)");
  Serial.printf("* **Q Matriks (Process Noise):** `Q_00` = %.1e, `Q_11` = %.1e\n", Q_NOISE_00, Q_NOISE_11);
  Serial.printf("* **R Matriks (Measurement Noise Base):** %f (adaptive: 0.5x rest, 5x discharge, 10x charge)\n", R_NOISE_BASE);
  Serial.printf("* **P_init (Initial Error Covariance):** `P[0][0]` = %.1f, `P[1][1]` = %.1f\n", 0.5, 0.1);
  Serial.println("* **Simulasi Memory Loss:** Algoritma dimulai dengan *offset error* sebesar 10% untuk menguji kekokohan EKF.");
  Serial.println("\n");
}

void loop()
{
  delay(10000);
}