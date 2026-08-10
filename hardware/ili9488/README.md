# ILI9488 IPS 480×320 driver files

This directory contains the project-specific Raspberry Pi 5 DRM setup for the
3.5-inch ILI9488 IPS SPI display and its XPT2046/ADS7846-compatible resistive
touch controller.

- `ili9488-ips.txt`: panel initialisation commands
- `ili9488-ips.bin`: generated `panel-mipi-dbi` firmware
- `dahamkke-ili9488-overlay.dts`: RGB666 DRM overlay source
- `dahamkke-ili9488.dtbo`: compiled Device Tree overlay
- `config.txt.fragment`: boot configuration installed by the setup procedure

The LCD is on SPI0 CE0. Touch is on SPI0 CE1 with PENIRQ on GPIO17. LCD reset
is GPIO25 and D/C is GPIO24. The backlight is wired directly to 3.3 V and is
therefore not controlled by the overlay.
