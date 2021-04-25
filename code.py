import time
import board
import busio
from digitalio import DigitalInOut
#import adafruit_requests as requests
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_esp32spi import adafruit_esp32spi_wifimanager
import adafruit_minimqtt.adafruit_minimqtt as MQTT

import displayio
import adafruit_st7789
import terminalio
from adafruit_display_text import label

import neopixel
from secrets import secrets
import adafruit_bmp280

# MQTT Topic to publish temp to
temp_feed = "event/temp"

# Release any resources currently in use for the displays
displayio.release_displays()
tft_cs = board.GP17
tft_dc = board.GP16
#tft_res = board.GP23
spi_mosi = board.GP19
spi_clk = board.GP18

esp32_cs = DigitalInOut(board.GP13)
esp32_ready = DigitalInOut(board.GP14)
esp32_reset = DigitalInOut(board.GP15)

DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 135
# Text along length (B to Y)
# DISPLAY_ROTATION = 270
# Text along width (X to Y)
DISPLAY_ROTATION = 90

if DISPLAY_ROTATION == 0 or DISPLAY_ROTATION == 180:
    temp = DISPLAY_WIDTH
    DISPLAY_WIDTH = DISPLAY_HEIGHT
    DISPLAY_HEIGHT = temp

spi0 = busio.SPI(spi_clk, MOSI=spi_mosi)
displayio.release_displays()
display_bus = displayio.FourWire(spi0, command=tft_dc, chip_select=tft_cs)
display = adafruit_st7789.ST7789(display_bus, width=DISPLAY_HEIGHT, height=DISPLAY_WIDTH, rowstart=40, colstart=53)
display.rotation = DISPLAY_ROTATION

# Make the display context
splash = displayio.Group(max_size=10)
display.show(splash)

# Draw a background colour
color_bitmap = displayio.Bitmap(DISPLAY_WIDTH, DISPLAY_HEIGHT, 1)
color_palette = displayio.Palette(1)
color_palette[0] = 0x00FF00  # Bright Green
bg_sprite = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
splash.append(bg_sprite)

# Create a label group
text = "Booting"
if DISPLAY_ROTATION == 90 or DISPLAY_ROTATION == 270:
    text_size = 2
else:
    text_size = 1
text_group = displayio.Group(max_size=10, scale=int(text_size), x=int(DISPLAY_WIDTH/2), y=int(DISPLAY_HEIGHT/2))
text_area = label.Label(terminalio.FONT, text=text, color=0x000000)
text_area.anchor_point = (0.5, 0.5)
text_area.anchored_position = (0, 0)
text_group.append(text_area)  # Subgroup for text scaling
splash.append(text_group)

# Create a second label group
status_text = " "
if DISPLAY_ROTATION == 90 or DISPLAY_ROTATION == 270:
    status_text_size = 2
else:
    status_text_size = 1
status_text_group = displayio.Group(max_size=10, scale=int(text_size), x=0, y=0)
status_text_area = label.Label(terminalio.FONT, text=status_text, color=0x000000)
status_text_area.anchor_point = (0.0, 0.0)
status_text_area.anchored_position = (0, 0)
status_text_group.append(status_text_area)  # Subgroup for text scaling
splash.append(status_text_group)

# Connect to Wifi
# (SCK, MOSI, MISO)
spi = busio.SPI(board.GP10, board.GP11, board.GP12)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

# Setup LED neopixel status light
wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(esp, secrets)

# Setup BMP280 temp sensor
i2c = busio.I2C(board.GP27, board.GP26)
bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=0x76)


# Define callback methods which are called when events occur
# pylint: disable=unused-argument, redefined-outer-name
def connected(client, userdata, flags, rc):
    # This function will be called when the client is connected
    # successfully to the broker.
    print("Connected to Adafruit IO! Listening for topic changes on %s" % temp_feed)
    # Subscribe to all changes on the onoff_feed.
    client.subscribe(temp_feed)
 
 
def disconnected(client, userdata, rc):
    # This method is called when the client is disconnected
    print("Disconnected from Adafruit IO!")
 
 
def message(client, topic, message):
    # This method is called when a topic the client is subscribed to
    # has a new message.
    print("New message on topic {0}: {1}".format(topic, message))

while True:
    # Connect to WiFi
    print("Connecting to WiFi...")
    text_area.text = "Connecting to WiFi"

    wifi.connect()

    print("Connected!")
    text_area.text = "Connected"
 
    # Initialize MQTT interface with the esp interface
    MQTT.set_socket(socket, esp)
 
    # Set up a MiniMQTT Client
    mqtt_client = MQTT.MQTT(
        broker=secrets["broker"],
        port=secrets["port"],
        username=secrets["mqtt_username"],
        password=secrets["mqtt_key"]
    )
 
    # Setup the callback methods above
    mqtt_client.on_connect = connected
    mqtt_client.on_disconnect = disconnected
    mqtt_client.on_message = message

    # Connect the client to the MQTT broker.
    print("Connecting to MQTT Host...")
    text_area.text = "Connecting to MQTT"
    mqtt_client.connect()

    # Increase text size for temp display
    text_area.text = " "
    text_area.scale = 2

    killed = False
    loop_count = 0
    while not killed:
        # Poll the message queue
        try:
            mqtt_client.loop()
        except Exception as e:
            print("MQTT Loop Failed, retrying\n", e)
            killed = True
            continue

        # Only publish data every 30 seconds
        if loop_count == 0 or loop_count >= 30:
            try:
                # publish new temp reading to the MQTT broker
                mqtt_client.publish(temp_feed, bmp280.temperature)
            except Exception as e:
                print("MQTT publish Failed, retrying\n", e)
                killed = True
                continue

        # Only update screen every 30 seconds
        if loop_count == 0 or loop_count >= 30:
            # Update text on display
            text_area.text = "%0.1f C" % bmp280.temperature
            display.refresh()
            loop_count = 1

        # Cycle through ".", "..", "..." text every second.
        # Used as visual indicator the sensors working.
        if len(status_text_area.text) >= 4:
            status_text_area.text = " "
        status_text_area.text += "."

        time.sleep(1)
        loop_count = loop_count + 1


