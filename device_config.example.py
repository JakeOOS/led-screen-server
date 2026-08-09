# Device credentials — copy to device_config.py, fill in, flash to the device.
#
# device_config.py is gitignored and must stay that way. device_app.py is a
# public file and is served unauthenticated-adjacent over OTA, so none of these
# values can live in it.

DEVICE_SECRET = ""      # must match DEVICE_SECRET in the Render environment
WIFI_SSID = ""
WIFI_PASSWORD = ""
SERVER_URL = "https://led-screen-server.onrender.com"
DEVICE_ID = ""          # e.g. "screen-01"; identifies this unit to the server
