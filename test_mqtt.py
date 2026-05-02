import paho.mqtt.client as mqtt

def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected")

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    print("Disconnected")

def on_message(client, userdata, message):
    print("Message")

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    print("Success")
except Exception as e:
    print("Error:", e)
