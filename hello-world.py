import time

from library.lcd.lcd_comm_rev_a_usbmac import LcdCommRevAUsbMac


lcd = LcdCommRevAUsbMac()
lcd.InitializeComm()
lcd.Clear()

try:
    while True:
        for dots in range(4):
            lcd.DisplayText(
                f"Hello, World!{'.' * dots}",
                width=lcd.get_width(),
                height=lcd.get_height(),
                font_color=(255, 255, 255),
                background_color=(0, 0, 0),
                align="center",
                anchor="mm",
            )
            time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    lcd.closeSerial()
