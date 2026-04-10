import pandas as pd
import json
import time
import paho.mqtt.client as mqtt

# =========================================================
# 1. KONFIGURASI MQTT
# =========================================================
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883
TOPIC_JIKONG = "bms_panel/260216/data/main"

# Inisialisasi MQTT Client (Format paho-mqtt versi 1.x)
client = mqtt.Client(client_id="Laptop_Injector")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

# =========================================================
# 2. LOAD DATASET (AUTO-DETEKSI BARIS HEADER)
# =========================================================
print("⏳ Membaca file CSV...")

def load_zke_data(filepath):
    skip_rows = 0
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            if "Time(S)" in line or "Vol(V)" in line:
                skip_rows = i
                break
                
    df = pd.read_csv(filepath, skiprows=skip_rows)
    df.columns = [col.strip() for col in df.columns]
    return df

df = load_zke_data("Dynamic Profiling (Urban Load).csv")

print(f"✅ Berhasil membaca {len(df)} baris data!")
print("🚀 Mulai mengirim data ke ESP32 (HIL Simulation)...")
time.sleep(2) 

# =========================================================
# 3. LOOPING INJEKSI DATA KE ESP32
# =========================================================
for index, row in df.iterrows():
    try:
        volt = float(row['Vol(V)'])
        curr = float(row['Cur(A)']) 
        
        cell_v = volt / 8.0 
        
        payload = {
            "voltage": volt,
            "current": curr,
            "power": volt * curr,
            "bat_temp1": 28.5,
            "mos_temp": 30.0,
            "cells_v": [cell_v]*8,
            "wire_res": [0.3]*8
        }
        
        client.publish(TOPIC_JIKONG, json.dumps(payload))
        
        print(f"[Iterasi {index}] Mengirim -> Volt: {volt:.3f}V | Amp: {curr:.2f}A")
        
        # Jeda pengiriman
        time.sleep(0.05) 
        
    except KeyError as e:
        print(f"❌ Error nama kolom tidak cocok: {e}")
        break
    except Exception as e:
        print(f"❌ Error tak terduga: {e}")
        break

print("✅ Simulasi Selesai!")
client.disconnect()