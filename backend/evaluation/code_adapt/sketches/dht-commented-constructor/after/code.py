# Synthetic CircuitPython script for the code-adapt eval; not from a real project.
import adafruit_dht
import board

sensor = adafruit_dht.DHT11(board.D4)
# spare = adafruit_dht.DHT22(board.D5)
print(sensor.humidity)
