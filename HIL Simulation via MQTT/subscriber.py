import paho.mqtt.client as mqtt

# Konfigurasi
MQTT_BROKER = "broker.mqtt.cool"
MQTT_PORT = 1883
TOPIC_JIKONG = "bms_panel/260216/data/main"

# Callback saat terkoneksi
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to MQTT Broker")
        client.subscribe(TOPIC_JIKONG)
        print(f"📡 Subscribed to topic: {TOPIC_JIKONG}")
    else:
        print(f"❌ Failed to connect, return code {rc}")

# Callback saat menerima pesan
def on_message(client, userdata, msg):
    print(f"📩 Message received:")
    print(f"Topic: {msg.topic}")
    print(f"Payload: {msg.payload.decode()}")

# Setup client
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Connect ke broker
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Loop terus untuk listen message
client.loop_forever()