import json
import csv
import sys
import os
import paho.mqtt.client as mqtt
from datetime import datetime

# =========================================================
# 1. KONFIGURASI MQTT BROKER UMUM
# =========================================================
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883

# =========================================================
# 2. MENU PEMILIHAN SKENARIO
# =========================================================
print("=== MENU LOGGER SIMULASI HiL ===")
print("1. Skenario 1 (Charging)")
print("2. Skenario 2 (Discharging)")
print("3. Skenario 3 (Dynamic Load)")
pilihan = input("Pilih skenario logger (1/2/3): ")

waktu_mulai = datetime.now().strftime("%Y%m%d_%H%M%S")

# Menyesuaikan konfigurasi berdasarkan pilihan
if pilihan == '1':
    TOPIC_CALC = "bms_panel/2602165/data/calc"
    FOLDER_PATH = "HIL Skenario1_Logger"
    NAMA_FILE = os.path.join(FOLDER_PATH, f"Hasil_Skenario1_HiL_{waktu_mulai}.csv")
    CLIENT_ID = "Laptop1-logger"
elif pilihan == '2':
    TOPIC_CALC = "batteryss/54673/data/calc"
    FOLDER_PATH = "HIL Skenario2_Logger"
    NAMA_FILE = os.path.join(FOLDER_PATH, f"Hasil_Skenario2_HiL_{waktu_mulai}.csv")
    CLIENT_ID = "Laptop2-logger"
elif pilihan == '3':
    # Disamakan ke /calc seperti skenario lain agar seragam untuk logger
    TOPIC_CALC = "bms_panel/2602165/data/calc"
    FOLDER_PATH = "HIL Skenario3_Logger"
    NAMA_FILE = os.path.join(FOLDER_PATH, f"Hasil_Skenario3_HiL_{waktu_mulai}.csv")
    CLIENT_ID = "Laptop3-logger"
else:
    print("Pilihan tidak valid! Program dihentikan.")
    sys.exit()

print(f"\nMempersiapkan Folder: {FOLDER_PATH}")
print(f"Mempersiapkan File  : {NAMA_FILE}")
print(f"Target Topik MQTT   : {TOPIC_CALC}")
print(f"Menggunakan ID      : {CLIENT_ID}")

# =========================================================
# 3. PERSIAPAN FILE & FOLDER CSV
# =========================================================
# Pastikan folder target ada
if not os.path.exists(FOLDER_PATH):
    os.makedirs(FOLDER_PATH)

# Buka file SEKALI saja di awal, dan biarkan terbuka selama program jalan
csv_file = open(NAMA_FILE, mode='w', newline='')
csv_writer = csv.writer(csv_file)

# Tulis Header
csv_writer.writerow(["Timestamp", "V_Meas(Avg)", "V_Pred(EKF)", "SoC_CC(%)", "SoC_EKF(%)", "dt"])
csv_file.flush() # Paksa tulis header ke harddisk

# =========================================================
# 4. CALLBACK MQTT (MENERIMA DATA)
# =========================================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"\n[INFO] Terhubung ke Broker!")
        print(f"[INFO] Mendengarkan topik: {TOPIC_CALC}")
        client.subscribe(TOPIC_CALC)
    else:
        print(f"[ERROR] Gagal terhubung, kode error: {rc}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        
        # Ekstrak data dari ESP32
        v_meas = data.get("avg_cell_v", 0.0)
        v_pred = data.get("v_pred", 0.0)
        soc_cc = data.get("soc_cc", 0.0)
        soc_ekf = data.get("soc_ekf", 0.0)
        dt = data.get("dt", 0.0)
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Simpan baris ke CSV
        csv_writer.writerow([timestamp, v_meas, v_pred, soc_cc, soc_ekf, dt])
        
        # SANGAT PENTING: Paksa OS memindahkan data dari RAM ke Harddisk saat ini juga!
        csv_file.flush()
        
        print(f"[{timestamp}] Disimpan -> Vm:{v_meas:.3f} | Vp:{v_pred:.3f} | CC:{soc_cc:.1f}% | EKF:{soc_ekf:.1f}%")

    except Exception as e:
        print(f"Gagal memparsing data: {e}")

# =========================================================
# 5. JALANKAN LOGGER
# =========================================================
client = mqtt.Client(client_id=CLIENT_ID)
client.on_connect = on_connect
client.on_message = on_message

print("\nMenyambungkan ke broker MQTT...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)

print("-" * 50)
print("Memulai Perekaman Data secara REAL-TIME.")
print("Perhatian: Jangan klik area dalam CMD agar tidak ter-pause (QuickEdit mode)!")
print("Tekan CTRL+C untuk berhenti secara aman.")
print("-" * 50)

try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\n[INFO] Sinyal CTRL+C terdeteksi. Menghentikan perekaman...")
finally:
    # Ini menjamin file CSV tertutup dengan sempurna meskipun program diclose paksa
    csv_file.close()
    print(f"[SUCCESS] File {NAMA_FILE} berhasil diamankan dan disimpan ke disk.")
    sys.exit(0)