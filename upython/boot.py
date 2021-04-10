import time
from umqttsimple import MQTTClient
import ubinascii
import machine
import micropython
import network
import esp
esp.osdebug(None)
import gc
gc.collect()

if machine.reset_cause() == machine.DEEPSLEEP_RESET:
    print('woke from a deep sleep')

with open("stem", "rb") as f:
  stem = f.read().splitlines()

MQTT_SERVER = '10.0.0.115'
MQTT_USER = stem[0] 
MQTT_PASSWORD = stem[1] 
#MQTT_SUB_TOPIC1 = b'espJoystick/motion/all'
#MQTT_PUB_TOPIC1 = b'espJoystick/motion/XY'
MQTT_SUB_TOPIC1 = b'esp/rotenc/all'
MQTT_PUB_TOPIC1 = b'esp/rotenc'
MQTT_CLIENT_ID = ubinascii.hexlify(machine.unique_id())
WIFI_SSID = stem[2]
WIFI_PASSWORD = stem[3]

station = network.WLAN(network.STA_IF)

station.active(True)
station.connect(WIFI_SSID, WIFI_PASSWORD)

while station.isconnected() == False:
  pass

print('Connection successful')
print(station.ifconfig())