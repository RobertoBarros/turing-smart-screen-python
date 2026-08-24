# SPDX-License-Identifier: GPL-3.0-or-later
#
# Backend for Turing Smart Screen 3.5" / UsbMonitor (rev. A) on macOS.

import os
import time

import usb.core
import usb.util

from library.lcd.lcd_comm import Orientation
from library.lcd.lcd_comm_rev_a import Command, LcdCommRevA
from library.log import logger

VID = 0x1A86
PID = 0x5722
INTERFACE = 1
OUT_EP = 0x03
IN_EP = 0x82


class LcdCommRevAUsbMac(LcdCommRevA):
    def __init__(self, com_port: str = "AUTO", display_width: int = 320, display_height: int = 480,
                 update_queue=None):
        logger.debug("HW revision: A (macOS USB bulk backend)")
        self.usb_dev = None
        super().__init__(com_port, display_width, display_height, update_queue)

    def __del__(self):
        self.closeSerial()

    def openSerial(self):
        try:
            self.usb_dev = usb.core.find(idVendor=VID, idProduct=PID)
            if self.usb_dev is None:
                raise ValueError("USB display not found")
            try:
                self.usb_dev.set_configuration()
            except usb.core.USBError:
                pass
            try:
                if self.usb_dev.is_kernel_driver_active(INTERFACE):
                    self.usb_dev.detach_kernel_driver(INTERFACE)
            except Exception:
                pass
            usb.util.claim_interface(self.usb_dev, INTERFACE)
            logger.info(f"Display connected through USB bulk (EP 0x{OUT_EP:02x})")
        except Exception as error:
            logger.error(f"Unable to open display through USB bulk: {error}")
            os._exit(1)

    def closeSerial(self):
        if self.usb_dev is not None:
            try:
                usb.util.release_interface(self.usb_dev, INTERFACE)
                usb.util.dispose_resources(self.usb_dev)
            except Exception:
                pass
            self.usb_dev = None

    def serial_write(self, data: bytes):
        assert self.usb_dev is not None
        self.usb_dev.write(OUT_EP, data, timeout=10000)

    def serial_read(self, size: int) -> bytes:
        assert self.usb_dev is not None
        try:
            return bytes(self.usb_dev.read(IN_EP, size, timeout=500))
        except usb.core.USBTimeoutError:
            return b""

    def serial_flush_input(self):
        try:
            while True:
                self.usb_dev.read(IN_EP, 64, timeout=50)
        except Exception:
            pass

    def WriteLine(self, line: bytes):
        try:
            self.serial_write(line)
        except usb.core.USBError as error:
            logger.error(f"USB write failed ({error}); reconnecting once")
            self.closeSerial()
            time.sleep(1)
            self.openSerial()
            self.serial_write(line)

    def SetOrientation(self, orientation: Orientation = Orientation.PORTRAIT):
        self.orientation = orientation
        width = self.get_width()
        height = self.get_height()
        byte_buffer = bytearray(11)
        byte_buffer[5] = Command.SET_ORIENTATION
        byte_buffer[6] = orientation + 100
        byte_buffer[7] = width >> 8
        byte_buffer[8] = width & 255
        byte_buffer[9] = height >> 8
        byte_buffer[10] = height & 255
        self.WriteData(byte_buffer)

    def Reset(self):
        try:
            if self.usb_dev is not None:
                logger.info("USB bus reset (forcing re-enumeration)...")
                self.usb_dev.reset()
        except usb.core.USBError as error:
            logger.warning(f"USB bus reset failed: {error}")
        self.closeSerial()
        time.sleep(3)
        self.openSerial()

        logger.info("Resynchronizing display before RESET...")
        try:
            self.SendCommand(Command.DISPLAY_BITMAP, 0, 0, self.display_width - 1,
                             self.display_height - 1, bypass_queue=True)
            frame = bytes(self.display_width * self.display_height * 2)
            for offset in range(0, len(frame), 4096):
                self.serial_write(frame[offset:offset + 4096])
        except usb.core.USBError as error:
            logger.warning(f"Resynchronization failed ({error}). Unplug and reconnect the display USB-C cable.")
        logger.info("Display reset (USB device will re-enumerate)...")
        self.SendCommand(Command.RESET, 0, 0, 0, 0, bypass_queue=True)
        self.closeSerial()
        time.sleep(6)
        self.openSerial()
