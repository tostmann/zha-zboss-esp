"""Constants for the ESP32-C6 ZBOSS ZHA adapter custom component."""

DOMAIN = "esp_zboss_zha"
NAME = "ESP32-C6 ZBOSS adapter for ZHA"

# Human-visible description shown in ZHA's "select radio type" UI step.
# Format mirrors zha's other RadioType descriptions:
#     "<PRETTY_NAME> = <vendor + product family>: <typical devices>"
RADIO_DESCRIPTION = (
    "ZBOSS = ZBOSS NCP Serial Protocol: ESP32-C6 esp-coordinator firmware "
    "(busware.de / tostmann), Nordic nRF52840 with ZBOSS NCP host"
)
