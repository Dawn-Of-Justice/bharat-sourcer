# Synthetic MicroPython script for the code-adapt eval; not from a real project.
import dht
from machine import Pin

d = dht.DHT22(Pin(15))
d.measure()
print(d.temperature(), d.humidity())
