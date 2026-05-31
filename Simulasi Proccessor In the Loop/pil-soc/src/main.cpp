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
TestResult final_results[5];
int result_index = 0;

// =========================================================
// 2. PARAMETER MODEL BATERAI (Polinomial Orde 6 & ECM)
// =========================================================
const float Q_AH = 20.798555;
const float Q_COULOMB = 74874.8; // Kapasitas As (Ampere-sekon)

// Koefisien Polinomial Orde 6 (Dari Python)
const float P_COEF[7] = {
    2.664967,    // p0
    9.485166,    // p1
    -58.074182,  // p2
    169.872070,  // p3
    -250.913864, // p4
    179.845768,  // p5
    -49.353787   // p6
};

// Parameter ECM (1-RC Thevenin)
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
const float Q_NOISE_00 = 1e-6;     // Process noise SOC
const float Q_NOISE_11 = 1e-4;     // Process noise V_RC
const float R_NOISE_BASE = 0.0002; // Measurement noise sensor tegangan

// =========================================================
// 4. VARIABEL STATE ESTIMATION
// =========================================================
float soc_cc = 0.0;
float ekf_x[2] = {0.0, 0.0};
float ekf_P[2][2] = {{0.1, 0.0}, {0.0, 0.01}};

float v_pred_last = 0.0;
float soc_true = 0.0;

double sum_sq_err_cc = 0;
double sum_sq_err_ekf_soc = 0;
double sum_sq_err_ekf_v = 0;
long total_samples = 0;

// =========================================================
// 5. FUNGSI MATEMATIKA: INTERPOLASI & POLINOMIAL EKF
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

// Fungsi OCV menggunakan Polinomial Orde 6
float get_OCV_from_Polynomial(float soc)
{
  return P_COEF[0] +
         (P_COEF[1] * soc) +
         (P_COEF[2] * pow(soc, 2)) +
         (P_COEF[3] * pow(soc, 3)) +
         (P_COEF[4] * pow(soc, 4)) +
         (P_COEF[5] * pow(soc, 5)) +
         (P_COEF[6] * pow(soc, 6));
}

// Jacobian (Turunan Parsial OCV terhadap SOC) menggunakan Polinomial
float get_dOCV_dSOC_Polynomial(float soc)
{
  float derivative = P_COEF[1] +
                     (2.0f * P_COEF[2] * soc) +
                     (3.0f * P_COEF[3] * pow(soc, 2)) +
                     (4.0f * P_COEF[4] * pow(soc, 3)) +
                     (5.0f * P_COEF[5] * pow(soc, 4)) +
                     (6.0f * P_COEF[6] * pow(soc, 5));
  return max(derivative, 0.01f); // Mencegah nilai nol atau negatif
}

void runEKFStep(float I_meas, float V_meas, float dt)
{
  // 1. Coulomb Counting (Tanpa Feedback)
  soc_cc = constrain(soc_cc - (I_meas * dt / Q_COULOMB), 0.0, 1.0);

  // 2. EKF: Time Update (Prediction)
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

  // 3. EKF: Measurement Update (Correction)
  float OCV_pred = get_OCV_from_Polynomial(soc_pred);
  float dOCV_dSOC = get_dOCV_dSOC_Polynomial(soc_pred);

  float V_pred = OCV_pred - vc1_pred - (I_meas * R0);
  v_pred_last = V_pred;

  // Jacobian Matrix H
  float h0 = dOCV_dSOC;
  float h1 = -1.0f;

  float R_eff = R_NOISE_BASE;
  if (I_meas < 0.0f)
    R_eff *= 50.0f; // Lebih skeptis saat tegangan saturasi charge
  else if (I_meas > 0.01f)
    R_eff *= 10.0f;

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
bool runDatasetTest(String filename, String mode)
{
  File file = LittleFS.open("/" + filename, "r");
  if (!file)
  {
    Serial.printf("[ERROR] Gagal membuka file %s.\n", filename.c_str());
    return false;
  }

  Serial.printf("[INFO] Menguji Dataset: %s\n", filename.c_str());

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
      current = -abs(current);
    else if (mode == "discharge")
      current = abs(current);
    else if (mode == "mixed")
    {
      if (voltage <= 2.65)
        is_charging_phase = true;
      if (current > 0.01)
        current = is_charging_phase ? -abs(current) : abs(current);
      else
        current = 0.0;
    }

    float dt = (time_prev < 0) ? 0.0 : (time_s - time_prev);

    // PENYESUAIAN 1: Lewati baris jika waktu tidak maju (duplikasi detik ke-0 dari ZKETECH)
    if (time_prev >= 0 && dt <= 0)
    {
      continue;
    }

    time_prev = time_s;

    // === PERBAIKAN INISIALISASI STARTING SOC ===
    if (total_samples == 0)
    {
      if (filename == "h-charge_rest_60m.csv")
        soc_true = 0.0;
      else if (filename == "h-DCC-4.4A-2.5V.csv")
        soc_true = 1.0;
      else if (filename == "h-Dynamic_Profiling_(Urban Load).csv")
        soc_true = 1.0;
      else if (filename == "h-charging_7.33A-rest 2h.csv")
        soc_true = 0.05; // 3.06V
      else if (filename == "h-DCC_4.4A_2.5V-CCV_6.6_3.65V-DCC_4.4A_2.5V.csv")
        soc_true = 0.0; // 2.71V

      // Simulasi "Memory Loss" 10%
      float soc_algo_start = (soc_true < 0.10) ? (soc_true + 0.10) : (soc_true - 0.10);

      soc_cc = soc_algo_start;
      ekf_x[0] = soc_algo_start;
      ekf_x[1] = 0.0;

      ekf_P[0][0] = 0.1;
      ekf_P[0][1] = 0.0;
      ekf_P[1][0] = 0.0;
      ekf_P[1][1] = 0.01;

      // Karena ini sampel pertama (dt=0), kita hanya inisialisasi dan lewati integral
      total_samples++;
      continue;
    }
    // Integritas data sebenarnya
    soc_true = constrain(soc_true - (current * dt / Q_COULOMB), 0.0, 1.0);

    // Eksekusi State Estimation
    runEKFStep(current, voltage, dt);

    double err_cc = soc_cc - soc_true;
    double err_ekf = ekf_x[0] - soc_true;
    double err_v = voltage - v_pred_last;

    sum_sq_err_cc += (err_cc * err_cc);
    sum_sq_err_ekf_soc += (err_ekf * err_ekf);
    sum_sq_err_ekf_v += (err_v * err_v);

    total_samples++;
  }
  file.close();

  if (result_index < 5)
  {
    final_results[result_index].filename = filename.substring(0, 20);
    final_results[result_index].rmse_cc = sqrt(sum_sq_err_cc / total_samples) * 100.0;
    final_results[result_index].rmse_ekf = sqrt(sum_sq_err_ekf_soc / total_samples) * 100.0;
    final_results[result_index].rmse_v = sqrt(sum_sq_err_ekf_v / total_samples) * 1000.0;
    result_index++;
  }
  Serial.println("[INFO] Selesai.\n");

  return true;
}

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

  if (!runDatasetTest("h-charge_rest_60m.csv", "charge"))
    return;
  if (!runDatasetTest("h-DCC-4.4A-2.5V.csv", "discharge"))
    return;
  if (!runDatasetTest("h-Dynamic_Profiling_(Urban Load).csv", "discharge"))
    return;
  if (!runDatasetTest("h-charging_7.33A-rest 2h.csv", "mixed"))
    return;
  if (!runDatasetTest("h-DCC_4.4A_2.5V-CCV_6.6_3.65V-DCC_4.4A_2.5V.csv", "mixed"))
    return;

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
  // =======================================================
  // CETAK FORMAT MARKDOWN
  // =======================================================
  Serial.println("\n\n<!-- COPY MULAI DARI BAWAH INI -->");
  Serial.println("## Tabel Hasil Perhitungan RMSE (PiL ESP32) dengan Polinomial Orde 6");
  Serial.println("Berikut adalah perbandingan tingkat error (RMSE) antara metode Coulomb Counting (CC) dan Extended Kalman Filter (EKF) menggunakan pemodelan fungsi OCV berbasis polinomial orde 6:");
  Serial.println("\n| NAMA DATASET | RMSE SoC (CC) | RMSE SoC (EKF) | RMSE Tegangan (EKF) |");
  Serial.println("| :--- | :---: | :---: | :---: |");

  for (int i = 0; i < result_index; i++)
  {
    Serial.printf("| %s | %.4f%% | %.4f%% | %.4f mV |\n",
                  final_results[i].filename.c_str(),
                  final_results[i].rmse_cc,
                  final_results[i].rmse_ekf,
                  final_results[i].rmse_v);
  }

  Serial.println("\n### Parameter Model & Tuning EKF yang Digunakan:");
  Serial.println("* **Polinomial Orde 6 (OCV-SoC):**");
  Serial.printf("  * `p0` = %f, `p1` = %f, `p2` = %f, `p3` = %f, `p4` = %f, `p5` = %f, `p6` = %f\n",
                P_COEF[0], P_COEF[1], P_COEF[2], P_COEF[3], P_COEF[4], P_COEF[5], P_COEF[6]);
  Serial.println("* **Q Matriks (Process Noise):**");
  Serial.printf("  * `Q_00` (Noise Arus) : %e\n", Q_NOISE_00);
  Serial.printf("  * `Q_11` (Noise Polarisasi) : %e\n", Q_NOISE_11);
  Serial.println("* **R Matriks (Measurement Noise Base):**");
  Serial.printf("  * `R_NOISE_BASE` : %f\n", R_NOISE_BASE);
  Serial.println("* **P_init (Initial Error Covariance):** `P[0][0]` = 0.1, `P[1][1]` = 0.01");
  Serial.println("* **Simulasi Memory Loss:** Algoritma dimulai dengan *offset error* sebesar 10% untuk menguji kekokohan EKF.");
  Serial.println("<!-- COPY SAMPAI SINI -->\n");
}

void loop()
{
  delay(10000);
}