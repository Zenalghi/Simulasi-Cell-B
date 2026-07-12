#!/usr/bin/env python3
"""
mqtt_logger.py
==============
Subscribe data MQTT dari JK BMS (via ESP32 + ESPHome),
simpan ke file CSV baru dengan nama berbeda setiap session.

Kompatibel dengan paho-mqtt v1.x dan v2.x.

Topik yang disubscribe:
    bms_logger/raw    → data utama (V, I, T, SOC_JK, dll.)
    bms_logger/status → status koneksi BLE

Output CSV per session:
    data_logs/bms_session_YYYYMMDD_HHMMSS.csv

Kolom CSV:
    timestamp_iso, elapsed_s, voltage_V, current_A, power_W,
    soc_jk_pct, cap_remain_ah,
    temp_mos_C, temp_bat1_C, temp_bat2_C,
    cell_v1..8_V, esp_ms

Cara pakai:
    pip install paho-mqtt
    python mqtt_logger.py

    Tekan Ctrl+C untuk berhenti. File CSV otomatis ditutup dengan rapi.

Setelah selesai logging, jalankan:
    python ekf_replayer.py <nama_file_csv>
untuk menghitung SOC_EKF dan membandingkan dengan SOC_JK.
"""

import paho.mqtt.client as mqtt
import paho.mqtt

# Deteksi versi paho-mqtt (kompatibel v1.x dan v2.x)
try:
    _paho_ver_str = paho.mqtt.__version__
except AttributeError:
    try:
        import importlib.metadata
        _paho_ver_str = importlib.metadata.version("paho-mqtt")
    except Exception:
        _paho_ver_str = "1.0.0"   # fallback: assume v1
_PAHO_V2 = tuple(int(x) for x in _paho_ver_str.split(".")[:2]) >= (2, 0)
import json
import csv
import os
import time
from datetime import datetime

# ============================================================
# KONFIGURASI — Sesuaikan jika perlu
# ============================================================
BROKER_HOST  = "192.168.230.131"
BROKER_PORT  = 1883
TOPIC_RAW    = "bms_logger/raw"
TOPIC_STATUS = "bms_logger/status"

# Folder tempat menyimpan semua file CSV
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_logs")

# ============================================================
# BUAT NAMA FILE UNIK BERDASARKAN WAKTU SESSION
# ============================================================
def make_output_filename():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"bms_session_{ts}.csv")
    return filename

# ============================================================
# HEADER CSV
# ============================================================
CSV_HEADER = [
    "timestamp_iso",
    "elapsed_s",
    "voltage_V",
    "current_A",
    "power_W",
    "soc_jk_pct",       # SOC bawaan JK BMS dalam persen (0-100)
    "cap_remain_ah",
    "temp_mos_C",
    "temp_bat1_C",
    "temp_bat2_C",
    "cell_v1_V",
    "cell_v2_V",
    "cell_v3_V",
    "cell_v4_V",
    "cell_v5_V",
    "cell_v6_V",
    "cell_v7_V",
    "cell_v8_V",
    "esp_ms",
]

# ============================================================
# STATE GLOBAL
# ============================================================
session_start_time = None   # Waktu Unix saat pesan pertama diterima
csv_file_handle    = None
csv_writer         = None
output_filepath    = None
message_count      = 0


def open_csv():
    """Buka file CSV baru dan tulis header."""
    global csv_file_handle, csv_writer, output_filepath
    output_filepath = make_output_filename()
    csv_file_handle = open(output_filepath, "w", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(csv_file_handle, fieldnames=CSV_HEADER)
    csv_writer.writeheader()
    csv_file_handle.flush()
    print(f"[Logger] File CSV dibuat: {output_filepath}")


def close_csv():
    """Tutup file CSV dengan aman."""
    global csv_file_handle
    if csv_file_handle and not csv_file_handle.closed:
        csv_file_handle.flush()
        csv_file_handle.close()
        print(f"\n[Logger] File CSV ditutup: {output_filepath}")
        print(f"[Logger] Total baris data  : {message_count}")


# ============================================================
# CALLBACK MQTT
# ============================================================
# Callback on_connect — signature berbeda antara paho v1 dan v2
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[MQTT] Terhubung ke broker {BROKER_HOST}:{BROKER_PORT}")
        client.subscribe(TOPIC_RAW,    qos=1)
        client.subscribe(TOPIC_STATUS, qos=0)
        print(f"[MQTT] Subscribe: {TOPIC_RAW}")
        print(f"[MQTT] Subscribe: {TOPIC_STATUS}")
        print("[Logger] Menunggu data dari JK BMS... (Ctrl+C untuk berhenti)\n")
    else:
        print(f"[MQTT] Gagal konek, kode error: {rc}")


def on_disconnect(client, userdata, rc, *args):
    # *args agar kompatibel dengan v1 (3 arg) maupun v2 (5 arg)
    print(f"[MQTT] Terputus dari broker (rc={rc}). Mencoba reconnect...")


def on_message(client, userdata, msg):
    global session_start_time, message_count

    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[WARN] Payload tidak valid JSON: {e}")
        return

    # --- Handle topik status ---
    if msg.topic == TOPIC_STATUS:
        ble_ok = payload.get("ble_connected", False)
        status_str = "ONLINE" if ble_ok else "OFFLINE"
        print(f"\r[BMS] Status BLE: {status_str}   ", end="", flush=True)
        return

    # --- Handle topik data utama ---
    if msg.topic != TOPIC_RAW:
        return

    now_unix = time.time()
    now_iso  = datetime.fromtimestamp(now_unix).isoformat(timespec="milliseconds")

    # Hitung elapsed sejak pesan pertama (t=0)
    if session_start_time is None:
        session_start_time = now_unix
        print(f"[Logger] Pesan pertama diterima pukul {now_iso}")
        print(f"[Logger] Session t=0 dimulai\n")
    elapsed_s = round(now_unix - session_start_time, 3)

    # Ambil nilai cell voltage
    cell_v = payload.get("cell_v", [0.0] * 8)
    # Pastikan array cukup panjang
    while len(cell_v) < 8:
        cell_v.append(0.0)

    row = {
        "timestamp_iso": now_iso,
        "elapsed_s"    : elapsed_s,
        "voltage_V"    : payload.get("voltage", 0.0),
        "current_A"    : payload.get("current", 0.0),
        "power_W"      : payload.get("power",   0.0),
        "soc_jk_pct"   : payload.get("soc_jk", -1.0),   # -1 = tidak valid
        "cap_remain_ah": payload.get("cap_remain_ah", 0.0),
        "temp_mos_C"   : payload.get("temp_mos",  0.0),
        "temp_bat1_C"  : payload.get("temp_bat1", 0.0),
        "temp_bat2_C"  : payload.get("temp_bat2", 0.0),
        "cell_v1_V"    : cell_v[0],
        "cell_v2_V"    : cell_v[1],
        "cell_v3_V"    : cell_v[2],
        "cell_v4_V"    : cell_v[3],
        "cell_v5_V"    : cell_v[4],
        "cell_v6_V"    : cell_v[5],
        "cell_v7_V"    : cell_v[6],
        "cell_v8_V"    : cell_v[7],
        "esp_ms"       : payload.get("esp_ms", 0),
    }

    csv_writer.writerow(row)
    message_count += 1

    # Flush setiap 10 baris agar data tidak hilang jika crash
    if message_count % 10 == 0:
        csv_file_handle.flush()

    # Tampilkan progres di terminal
    soc_display = f"{row['soc_jk_pct']:.1f}%" if row['soc_jk_pct'] >= 0 else "N/A"
    print(
        f"\r[{elapsed_s:8.1f}s] "
        f"V={row['voltage_V']:.3f}V  "
        f"I={row['current_A']:+.3f}A  "
        f"SOC_JK={soc_display:>6}  "
        f"T={row['temp_bat1_C']:.1f}°C  "
        f"#{message_count}",
        end="", flush=True
    )


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("  JK BMS MQTT Logger — Eksperimen Akurasi SOC")
    print("=" * 60)
    print(f"  Broker  : {BROKER_HOST}:{BROKER_PORT}")
    print(f"  Output  : {OUTPUT_DIR}")
    print("=" * 60)
    print()

    # Buka file CSV sebelum connect
    open_csv()

    # Setup MQTT client — kompatibel paho-mqtt v1.x dan v2.x
    if _PAHO_V2:
        # paho-mqtt >= 2.0: wajib pakai CallbackAPIVersion
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,   # pakai V1 agar signature callback sama
            client_id=f"bms_logger_{int(time.time())}",
            clean_session=True,
        )
    else:
        # paho-mqtt 1.x: API lama
        client = mqtt.Client(
            client_id=f"bms_logger_{int(time.time())}",
            clean_session=True,
        )
    print(f"[MQTT] paho-mqtt versi {_paho_ver_str}")
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\n[Logger] Ctrl+C diterima. Menghentikan logger...")
    except ConnectionRefusedError:
        print(f"\n[ERROR] Koneksi ditolak! Pastikan broker MQTT berjalan di {BROKER_HOST}:{BROKER_PORT}")
        print("        Jalankan: mosquitto -v  (atau broker lain)")
    except Exception as e:
        print(f"\n[ERROR] {e}")
    finally:
        client.disconnect()
        close_csv()
        if output_filepath and message_count > 0:
            print(f"\n[✓] Data tersimpan di: {output_filepath}")
            print(f"[→] Langkah selanjutnya: python ekf_replayer.py \"{output_filepath}\"")


if __name__ == "__main__":
    main()
