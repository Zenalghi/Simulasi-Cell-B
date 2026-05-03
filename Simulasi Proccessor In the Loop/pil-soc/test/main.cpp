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
};
TestResult final_results[4];
int result_index = 0;

// =========================================================
// 2. PARAMETER MODEL BATERAI (Cubic Spline 21 Titik)
// =========================================================
const float Q_AH = 20.798555;
const float Q_COULOMB = Q_AH * 3600.0;

const int LUT_OCV_SIZE = 21;
const float lut_soc_ocv[LUT_OCV_SIZE] = {
    0.00, 0.05, 0.10, 0.15, 0.20,
    0.25, 0.30, 0.35, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.65, 0.70,
    0.75, 0.80, 0.85, 0.90, 0.95, 1.00};

const float lut_ocv[LUT_OCV_SIZE] = {
    2.655, 3.050, 3.194, 3.210, 3.220,
    3.232, 3.245, 3.258, 3.270, 3.282,
    3.285, 3.287, 3.288, 3.289, 3.291,
    3.294, 3.300, 3.310, 3.331, 3.385, 3.537};

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
// 3. TUNING NOISE PARAMETER EKF (SIMULASI F)
// =========================================================
const float Q_NOISE_00 = 1e-7;
const float Q_NOISE_11 = 5e-4; // Diubah untuk Simulasi F

// R adaptif yang dipertajam:
const float R_NOISE_CHARGE = 0.06;    // Ekstra skeptis pada sensor saat saturasi Charging
const float R_NOISE_DISCHARGE = 0.005; // Ekstra tajam saat Discharge/Rest

// =========================================================
// 4. VARIABEL STATE ESTIMATION
// =========================================================
float soc_cc = 0.0;
float ekf_x[2] = {0.0, 0.0};
float ekf_P[2][2] = {{0.1, 0.0}, {0.0, 0.01}}; // Diubah untuk Simulasi F

float v_pred_last = 0.0;
float soc_true = 0.0;

double sum_sq_err_cc = 0;
double sum_sq_err_ekf_soc = 0;
double sum_sq_err_ekf_v = 0;
long total_samples = 0;

// =========================================================
// 5. FUNGSI MATEMATIKA: INTERPOLASI & EKF
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

float get_SOC_from_OCV(float ocv_val)
{
  if (ocv_val <= lut_ocv[0])
    return lut_soc_ocv[0];
  if (ocv_val >= lut_ocv[LUT_OCV_SIZE - 1])
    return lut_soc_ocv[LUT_OCV_SIZE - 1];
  for (int i = 0; i < LUT_OCV_SIZE - 1; i++)
  {
    if (ocv_val >= lut_ocv[i] && ocv_val <= lut_ocv[i + 1])
    {
      float t = (ocv_val - lut_ocv[i]) / (lut_ocv[i + 1] - lut_ocv[i]);
      return lut_soc_ocv[i] + t * (lut_soc_ocv[i + 1] - lut_soc_ocv[i]);
    }
  }
  return lut_soc_ocv[0];
}

float get_dOCV_dSOC(float soc)
{
  float delta = 0.001;
  float s_high = min(soc + delta, 1.0f);
  float s_low = max(soc - delta, 0.0f);
  float ocv_high = interpolate1D(s_high, lut_soc_ocv, lut_ocv, LUT_OCV_SIZE);
  float ocv_low = interpolate1D(s_low, lut_soc_ocv, lut_ocv, LUT_OCV_SIZE);
  float derivative = (ocv_high - ocv_low) / (s_high - s_low);
  return max(derivative, 0.05f);
}

void runEKFStep(float I_meas, float V_meas, float dt)
{
  soc_cc = constrain(soc_cc - (I_meas * dt / Q_COULOMB), 0.0, 1.0);

  float soc_prev = constrain(ekf_x[0], 0.0, 1.0);
  float vc1_prev = ekf_x[1];

  float R0 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_r0, LUT_ECM_SIZE), 0.0001f);
  float R1 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_r1, LUT_ECM_SIZE), 0.0001f);
  float C1 = max(interpolate1D(soc_prev, lut_soc_ecm, lut_c1, LUT_ECM_SIZE), 1.0f);
  float tau = max(R1 * C1, 0.000001f);

  float soc_pred = constrain(soc_prev - (I_meas * dt / Q_COULOMB), 0.0, 1.0);
  float alpha = (dt > 0) ? exp(-dt / tau) : 1.0f;
  float vc1_pred = (alpha * vc1_prev) + (R1 * (1.0f - alpha) * I_meas);

  ekf_x[0] = soc_pred;
  ekf_x[1] = vc1_pred;

  float P_pred[2][2];
  P_pred[0][0] = ekf_P[0][0] + Q_NOISE_00;
  P_pred[0][1] = ekf_P[0][1] * alpha;
  P_pred[1][0] = ekf_P[1][0] * alpha;
  P_pred[1][1] = (alpha * alpha * ekf_P[1][1]) + Q_NOISE_11;

  float OCV_pred = interpolate1D(soc_pred, lut_soc_ocv, lut_ocv, LUT_OCV_SIZE);
  float dOCV_dSOC = get_dOCV_dSOC(soc_pred);

  float V_pred = OCV_pred - vc1_pred - (I_meas * R0);
  v_pred_last = V_pred;

  float h0 = dOCV_dSOC;
  float h1 = -1.0f;

  // Gunakan R_NOISE adaptif
  float R_eff = (I_meas < 0.0f) ? R_NOISE_CHARGE : R_NOISE_DISCHARGE;

  float S = (h0 * h0 * P_pred[0][0]) + (h0 * h1 * P_pred[0][1]) +
            (h1 * h0 * P_pred[1][0]) + (h1 * h1 * P_pred[1][1]) + R_eff;

  float K[2];
  K[0] = ((P_pred[0][0] * h0) + (P_pred[0][1] * h1)) / S;
  K[1] = ((P_pred[1][0] * h0) + (P_pred[1][1] * h1)) / S;

  float error = V_meas - V_pred;
  ekf_x[0] = constrain(ekf_x[0] + (K[0] * error), 0.0, 1.0);
  ekf_x[1] = ekf_x[1] + (K[1] * error);

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
}

// =========================================================
// 6. RUNNER PROCESSOR-IN-THE-LOOP (PiL)
// =========================================================
void runDatasetTest(String filename, String mode)
{
  File file = LittleFS.open("/" + filename, "r");
  if (!file)
  {
    Serial.printf("[ERROR] Gagal membuka file %s\n", filename.c_str());
    return;
  }

  Serial.printf("[INFO] Menguji Dataset: %s (Mode: %s)\n", filename.c_str(), mode.c_str());

  while (file.available())
  {
    String line = file.readStringUntil('\n');
    if (line.indexOf("Time(S)") >= 0)
      break;
  }

  sum_sq_err_cc = 0;
  sum_sq_err_ekf_soc = 0;
  sum_sq_err_ekf_v = 0;
  total_samples = 0;

  float time_prev = -1.0;
  bool is_charging_phase = false;
  char buf[128];

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

    if (mode == "charge")
    {
      current = -abs(current);
    }
    else if (mode == "discharge")
    {
      current = abs(current);
    }
    else if (mode == "mixed")
    {
      if (voltage <= 2.65)
        is_charging_phase = true;
      if (current > 0.01)
      {
        current = is_charging_phase ? -abs(current) : abs(current);
      }
      else
      {
        current = 0.0;
      }
    }

    float dt = (time_prev < 0) ? 1.0 : (time_s - time_prev);
    if (dt <= 0)
      dt = 1.0;
    time_prev = time_s;

    if (total_samples == 0)
    {
      soc_true = get_SOC_from_OCV(voltage);
      float soc_algo_start = soc_true - 0.10;
      if (soc_algo_start < 0)
        soc_algo_start = 0.05;

      soc_cc = soc_algo_start;
      ekf_x[0] = soc_algo_start;
      ekf_x[1] = 0.0;

      // Inisialisasi P_init sesuai Simulasi F
      ekf_P[0][0] = 0.1;
      ekf_P[0][1] = 0.0;
      ekf_P[1][0] = 0.0;
      ekf_P[1][1] = 0.01;
    }

    soc_true = constrain(soc_true - (current * dt / Q_COULOMB), 0.0, 1.0);
    runEKFStep(current, voltage, dt);

    double err_cc = soc_cc - soc_true;
    double err_ekf = ekf_x[0] - soc_true;
    double err_v = voltage - v_pred_last;

    sum_sq_err_cc += (err_cc * err_cc);
    sum_sq_err_ekf_soc += (err_ekf * err_ekf);
    sum_sq_err_ekf_v += (err_v * err_v);

    total_samples++;

    if (total_samples % 3000 == 0)
    {
      Serial.printf("       -> Progres EKF: Baris ke-%ld diproses...\n", total_samples);
    }
  }
  file.close();

  if (result_index < 4)
  {
    final_results[result_index].filename = filename.substring(0, 20);
    final_results[result_index].rmse_cc = sqrt(sum_sq_err_cc / total_samples) * 100.0;
    final_results[result_index].rmse_ekf = sqrt(sum_sq_err_ekf_soc / total_samples) * 100.0;
    final_results[result_index].rmse_v = sqrt(sum_sq_err_ekf_v / total_samples) * 1000.0;
    result_index++;
  }
  Serial.println("[INFO] Eksekusi Selesai.\n");
}

void setup()
{
  Serial.begin(115200);
  delay(2000);

  Serial.println("\n\n===========================================================================");
  Serial.println("           MEMULAI PENGUJIAN PROCESSOR-IN-THE-LOOP (PiL) ESP32             ");
  Serial.println("===========================================================================\n");

  if (!LittleFS.begin(true))
  {
    Serial.println("[FATAL] Gagal Mount LittleFS!");
    return;
  }

  result_index = 0;

  runDatasetTest("h-charge_rest_60m.csv", "charge");
  runDatasetTest("h-DCC-4.4A-2.5V.csv", "discharge");
  runDatasetTest("h-Dynamic_Profiling_(Urban Load).csv", "discharge");
  runDatasetTest("h-charging_7.33A-rest 2h.csv", "mixed");

  // =======================================================
  // CETAK TABEL REKAPITULASI FINAL YANG SUDAH DIRAPIKAN
  // =======================================================
  Serial.println("\n===========================================================================");
  Serial.println("| NAMA DATASET         | RMSE SoC (CC)  | RMSE SoC (EKF) | RMSE TEGANGAN  |");
  Serial.println("===========================================================================");

  for (int i = 0; i < result_index; i++)
  {
    Serial.printf("| %-20s | %10.4f %%   | %10.4f %%   | %9.4f mV   |\n",
                  final_results[i].filename.c_str(),
                  final_results[i].rmse_cc,
                  final_results[i].rmse_ekf,
                  final_results[i].rmse_v);
  }

  Serial.println("===========================================================================");
  Serial.println("Pengujian PiL Selesai dengan Sukses!");

  // =======================================================
  // CETAK PARAMETER EKF UNTUK LOG PENGUJIAN
  // =======================================================
  Serial.println("\n===========================================================================");
  Serial.println("               PARAMETER MODEL & NOISE EKF YANG DIGUNAKAN                  ");
  Serial.println("===========================================================================");
  Serial.printf(" - Q_NOISE_00 (Arus) : %e\n", Q_NOISE_00);
  Serial.printf(" - Q_NOISE_11 (Pola) : %e\n", Q_NOISE_11);
  Serial.printf(" - R_CHARGE (CV)     : %f\n", R_NOISE_CHARGE);
  Serial.printf(" - R_DISCHARGE       : %f\n", R_NOISE_DISCHARGE);
  Serial.println(" - P_init (Awal)     : [[0.1, 0.0], [0.0, 0.01]]");
  Serial.println("===========================================================================\n");

  // =======================================================
  // CETAK FORMAT MARKDOWN UNTUK COPY-PASTE DOKUMENTASI
  // =======================================================
  Serial.println("\n\n<!-- COPY MULAI DARI BAWAH INI -->");
  Serial.println("## Tabel Hasil Perhitungan RMSE Simulasi-F (PiL ESP32)");
  Serial.println("Berdasarkan simulasi Processor-in-the-Loop (PiL) di ESP32, sistem algoritma diberikan nilai start awal yang sedikit *meleset* dari State of Charge sebenarnya (mensimulasikan *memory loss* di ESP32). Berikut adalah perbandingan tingkat error (RMSE) antara metode Coulomb Counting (CC) dan Extended Kalman Filter (EKF):");
  Serial.println("\n| Skenario Pengujian | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) |");
  Serial.println("| :--- | :---: | :---: | :---: |");

  // Format array nama file agar sesuai markdown awal
  String display_names[4] = {
      "Pengujian Charging (C-CV)",
      "Pengujian Discharging (D-CC)",
      "Pengujian Pembebanan Dinamis (Urban Load)",
      "Pengujian Mixed (D-CC & C-CV 7.33A)"};

  for (int i = 0; i < result_index; i++)
  {
    Serial.printf("| %s | %.4f%% | %.4f%% | %.4f mV |\n",
                  display_names[i].c_str(),
                  final_results[i].rmse_cc,
                  final_results[i].rmse_ekf,
                  final_results[i].rmse_v);
  }

  Serial.println("\n### Parameter Tuning EKF yang Digunakan (Simulasi F - Optimasi Final)");
  Serial.println("* **Q Matriks (Process Noise):**");
  Serial.printf("  * `Q_00` (Noise Arus) : %e\n", Q_NOISE_00);
  Serial.printf("  * `Q_11` (Noise Polarisasi) : %e\n", Q_NOISE_11);
  Serial.println("* **R Matriks (Measurement Noise - Adaptive):**");
  Serial.printf("  * `R_CHARGE` (Skeptis saat CV) : %f\n", R_NOISE_CHARGE);
  Serial.printf("  * `R_DISCHARGE` (Tajam saat kuras) : %f\n", R_NOISE_DISCHARGE);
  Serial.println("* **P_init (Initial Error Covariance):** `P[0][0]` = 0.1, `P[1][1]` = 0.01");
  Serial.println("<!-- COPY SAMPAI SINI -->\n");
}

void loop()
{
  delay(10000);
}