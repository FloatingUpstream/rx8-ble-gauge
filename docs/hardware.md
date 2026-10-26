# Hardware

Primary target: **Waveshare ESP32-S3-Touch-LCD-1.85B**.
Tested OBD bridge: **Veepeak OBDCheck BLE+**, using BLE rather than Classic SPP.
The first real RX-8 test returned coolant and MAF; compatibility with other
adapters, vehicles or operating conditions is not established.

## Board resources

- ESP32-S3R8, 8 MB PSRAM, 16 MB external flash.
- 1.85-inch 360 × 360 TFT LCD, ST77916 controller, QSPI.
- CST816S capacitive touch and QMI8658 six-axis IMU.
- BQ27220 battery gauge, 3.7 V battery connector and charging support.
- PCF85063 RTC, audio hardware and microSD.
- Native USB-C flashing/logging; hardware-controlled PWR button.

This TFT needs a backlight: black pixels do not provide AMOLED-style power
savings. Battery capacity, gauge calibration, runtime and charging behavior
require measurement. Presence of the IMU does not establish a working
deep-sleep motion-wake path or calibrated acceleration measurements.

## Pin reference

Vendor-documented mapping; verify against your board revision and schematic
before wiring or modifying hardware.

| Function | Pins / address |
| --- | --- |
| LCD QSPI | CS 21, CLK 40, D0 46, D1 45, D2 42, D3 41 |
| LCD reset / backlight | RST 3, BL 5 (PWM) |
| Shared I2C | SCL 10, SDA 11 |
| Touch | 0x15, RST 1, INT 4 |
| IMU | 0x6B |
| Battery gauge | 0x55 |
| RTC | 0x51, INT 6 |
| Native USB | D− 19, D+ 20 |
| UART0 | TX 43, RX 44 |
| BOOT | GPIO0 (strapping pin) |

Native USB commonly enumerates as Espressif USB JTAG/serial, VID:PID
`303a:1001`. Identify your own port; enumeration alone proves neither firmware
health nor board revision.

## Mechanical and safety limits

See [mechanical design](mechanical-design.md) for the proposed enclosure/mount.
Mount retention, heat exposure, visibility, battery runtime and in-car charging
are unverified. Keep prototypes clear of airbags, pedals and controls.
This gauge is read-only diagnostic instrumentation, not a safety device or a
replacement for factory warnings.

## Vendor references

- [Board documentation](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.85B)
- [Resources and schematics](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.85B/Resources-And-Documents)
- [ESP-IDF guide](https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.85B/ESP-IDF)
- [Vendor repository](https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.85B)

Do not reuse drivers or pin/power assumptions from similarly named AMOLED boards.
