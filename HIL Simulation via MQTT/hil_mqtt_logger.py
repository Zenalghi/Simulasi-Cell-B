import json
import csv
import paho.mqtt.client as mqtt
from datetime import datetime

# =========================================================
# 1. KONFIGURASI MQTT & FILE
# =========================================================
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883
TOPIC_CALC = "bms_panel/2602165/data/calc"

# Nama file output (otomatis dengan timestamp)
waktu_mulai = datetime.now().strftime("%Y%m%d_%H%M%S")
NAMA_FILE = f"Hasil_Simulasi_HiL_{waktu_mulai}.csv"

# Buat file CSV dan tulis header
with open(NAMA_FILE, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Timestamp", "V_Meas(Avg)", "V_Pred(EKF)", "SoC_CC(%)", "SoC_EKF(%)", "dt"])

# =========================================================
# 2. CALLBACK MQTT (MENERIMA DATA)
# =========================================================
def on_connect(client, userdata, flags, rc):
    print(f"Terhubung ke Broker dengan kode hasil: {rc}")
    print(f"Mendengarkan topik: {TOPIC_CALC}")
    client.subscribe(TOPIC_CALC)

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
        
        # Simpan ke CSV
        with open(NAMA_FILE, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([timestamp, v_meas, v_pred, soc_cc, soc_ekf, dt])
            
        print(f"[{timestamp}] Disimpan -> Vm:{v_meas:.3f} | Vp:{v_pred:.3f} | CC:{soc_cc:.1f}% | EKF:{soc_ekf:.1f}%")

    except Exception as e:
        print(f"Gagal memparsing data: {e}")

# =========================================================
# 3. JALANKAN LOGGER
# =========================================================
client = mqtt.Client(client_id="Laptop_Logger")
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, 60)

print(f"Memulai Perekaman Data ke file: {NAMA_FILE}")
print("Tekan CTRL+C untuk berhenti.")
try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\nPerekaman dihentikan oleh pengguna.")