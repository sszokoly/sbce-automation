#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Shared VMware console keyboard utilities for Ansible modules and standalone tools.
"""

import ssl
import time

try:
    from pyVim.connect import SmartConnect, Disconnect  # type: ignore
    from pyVmomi import vim  # type: ignore

    HAS_PYVMOMI = True
except Exception:  # pragma: no cover - import-time capability flag
    SmartConnect = None  # type: ignore
    Disconnect = None  # type: ignore
    vim = None  # type: ignore
    HAS_PYVMOMI = False


MOD_NONE = 0x00
MOD_LSHIFT = 0x02
HID_CAPSLOCK = 0x39


SPECIAL_KEYS = {
    "ENTER": 0x28,
    "ESC": 0x29,
    "BACKSPACE": 0x2A,
    "TAB": 0x2B,
    "SPACE": 0x2C,
    "CAPSLOCK": 0x39,
    "F1": 0x3A,
    "F2": 0x3B,
    "F3": 0x3C,
    "F4": 0x3D,
    "F5": 0x3E,
    "F6": 0x3F,
    "F7": 0x40,
    "F8": 0x41,
    "F9": 0x42,
    "F10": 0x43,
    "F11": 0x44,
    "F12": 0x45,
    "INSERT": 0x49,
    "HOME": 0x4A,
    "PAGE_UP": 0x4B,
    "DELETE": 0x4C,
    "END": 0x4D,
    "PAGE_DOWN": 0x4E,
    "RIGHT": 0x4F,
    "LEFT": 0x50,
    "DOWN": 0x51,
    "UP": 0x52,
    "NUMPAD_SLASH": 0x54,
    "NUMPAD_STAR": 0x55,
    "NUMPAD_MINUS": 0x56,
    "NUMPAD_PLUS": 0x57,
    "NUMPAD_ENTER": 0x58,
    "NUMPAD_1": 0x59,
    "NUMPAD_2": 0x5A,
    "NUMPAD_3": 0x5B,
    "NUMPAD_4": 0x5C,
    "NUMPAD_5": 0x5D,
    "NUMPAD_6": 0x5E,
    "NUMPAD_7": 0x5F,
    "NUMPAD_8": 0x60,
    "NUMPAD_9": 0x61,
    "NUMPAD_0": 0x62,
    "NUMPAD_DOT": 0x63,
}


CHAR_MAP = {
    "1": (0x1E, MOD_NONE),
    "!": (0x1E, MOD_LSHIFT),
    "2": (0x1F, MOD_NONE),
    "@": (0x1F, MOD_LSHIFT),
    "3": (0x20, MOD_NONE),
    "#": (0x20, MOD_LSHIFT),
    "4": (0x21, MOD_NONE),
    "$": (0x21, MOD_LSHIFT),
    "5": (0x22, MOD_NONE),
    "%": (0x22, MOD_LSHIFT),
    "6": (0x23, MOD_NONE),
    "^": (0x23, MOD_LSHIFT),
    "7": (0x24, MOD_NONE),
    "&": (0x24, MOD_LSHIFT),
    "8": (0x25, MOD_NONE),
    "*": (0x25, MOD_LSHIFT),
    "9": (0x26, MOD_NONE),
    "(": (0x26, MOD_LSHIFT),
    "0": (0x27, MOD_NONE),
    ")": (0x27, MOD_LSHIFT),
    "a": (0x04, MOD_NONE),
    "A": (0x04, MOD_LSHIFT),
    "b": (0x05, MOD_NONE),
    "B": (0x05, MOD_LSHIFT),
    "c": (0x06, MOD_NONE),
    "C": (0x06, MOD_LSHIFT),
    "d": (0x07, MOD_NONE),
    "D": (0x07, MOD_LSHIFT),
    "e": (0x08, MOD_NONE),
    "E": (0x08, MOD_LSHIFT),
    "f": (0x09, MOD_NONE),
    "F": (0x09, MOD_LSHIFT),
    "g": (0x0A, MOD_NONE),
    "G": (0x0A, MOD_LSHIFT),
    "h": (0x0B, MOD_NONE),
    "H": (0x0B, MOD_LSHIFT),
    "i": (0x0C, MOD_NONE),
    "I": (0x0C, MOD_LSHIFT),
    "j": (0x0D, MOD_NONE),
    "J": (0x0D, MOD_LSHIFT),
    "k": (0x0E, MOD_NONE),
    "K": (0x0E, MOD_LSHIFT),
    "l": (0x0F, MOD_NONE),
    "L": (0x0F, MOD_LSHIFT),
    "m": (0x10, MOD_NONE),
    "M": (0x10, MOD_LSHIFT),
    "n": (0x11, MOD_NONE),
    "N": (0x11, MOD_LSHIFT),
    "o": (0x12, MOD_NONE),
    "O": (0x12, MOD_LSHIFT),
    "p": (0x13, MOD_NONE),
    "P": (0x13, MOD_LSHIFT),
    "q": (0x14, MOD_NONE),
    "Q": (0x14, MOD_LSHIFT),
    "r": (0x15, MOD_NONE),
    "R": (0x15, MOD_LSHIFT),
    "s": (0x16, MOD_NONE),
    "S": (0x16, MOD_LSHIFT),
    "t": (0x17, MOD_NONE),
    "T": (0x17, MOD_LSHIFT),
    "u": (0x18, MOD_NONE),
    "U": (0x18, MOD_LSHIFT),
    "v": (0x19, MOD_NONE),
    "V": (0x19, MOD_LSHIFT),
    "w": (0x1A, MOD_NONE),
    "W": (0x1A, MOD_LSHIFT),
    "x": (0x1B, MOD_NONE),
    "X": (0x1B, MOD_LSHIFT),
    "y": (0x1C, MOD_NONE),
    "Y": (0x1C, MOD_LSHIFT),
    "z": (0x1D, MOD_NONE),
    "Z": (0x1D, MOD_LSHIFT),
    " ": (0x2C, MOD_NONE),
    "\n": (0x28, MOD_NONE),
    "\t": (0x2B, MOD_NONE),
    "-": (0x2D, MOD_NONE),
    "_": (0x2D, MOD_LSHIFT),
    "=": (0x2E, MOD_NONE),
    "+": (0x2E, MOD_LSHIFT),
    "[": (0x2F, MOD_NONE),
    "{": (0x2F, MOD_LSHIFT),
    "]": (0x30, MOD_NONE),
    "}": (0x30, MOD_LSHIFT),
    "\\": (0x31, MOD_NONE),
    "|": (0x31, MOD_LSHIFT),
    ";": (0x33, MOD_NONE),
    ":": (0x33, MOD_LSHIFT),
    "'": (0x34, MOD_NONE),
    '"': (0x34, MOD_LSHIFT),
    "`": (0x35, MOD_NONE),
    "~": (0x35, MOD_LSHIFT),
    ",": (0x36, MOD_NONE),
    "<": (0x36, MOD_LSHIFT),
    ".": (0x37, MOD_NONE),
    ">": (0x37, MOD_LSHIFT),
    "/": (0x38, MOD_NONE),
    "?": (0x38, MOD_LSHIFT),
}


def host_name_matches(actual, wanted):
    if not actual or not wanted:
        return False
    a, w = actual.lower(), wanted.lower()
    if a == w:
        return True
    return a.split(".")[0] == w.split(".")[0]


def find_datacenter(content, name):
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.Datacenter], True
    )
    try:
        for dc in container.view:
            if dc.name == name:
                return dc
    finally:
        container.Destroy()
    raise RuntimeError("Datacenter not found: {0!r}".format(name))


def find_vm(content, vmname, datacenter=None, esxi_hostname=None):
    if datacenter:
        dc = find_datacenter(content, datacenter)
        root = dc.vmFolder
    else:
        root = content.rootFolder

    container = content.viewManager.CreateContainerView(
        root, [vim.VirtualMachine], True
    )
    matches = []
    try:
        for vm in container.view:
            if vm.name != vmname:
                continue
            if esxi_hostname:
                host = vm.runtime.host
                if host is None:
                    continue
                if not host_name_matches(host.name, esxi_hostname):
                    continue
            matches.append(vm)
    finally:
        container.Destroy()

    if not matches:
        msg = "VM not found: {0!r}".format(vmname)
        if datacenter:
            msg += " (datacenter={0!r})".format(datacenter)
        if esxi_hostname:
            msg += " (esxi_hostname={0!r})".format(esxi_hostname)
        raise RuntimeError(msg)
    if len(matches) > 1:
        hosts = []
        for vm in matches:
            h = vm.runtime.host
            hosts.append(h.name if h else "?")
        raise RuntimeError(
            "Multiple VMs named {0!r} after filtering: hosts {1!r}".format(
                vmname, hosts
            )
        )
    return matches[0]


def press_key(vm, hid_code):
    spec = vim.vm.UsbScanCodeSpec()
    down = vim.vm.UsbScanCodeSpec.KeyEvent()
    down.usbHidCode = (hid_code << 16) | 0x07
    up = vim.vm.UsbScanCodeSpec.KeyEvent()
    up.usbHidCode = 0
    spec.keyEvents = [down, up]
    return vm.PutUsbScanCodes(spec)


class VMKeyboard(object):
    """
    Simple keyboard sender using PutUsbScanCodes.

    By default, emulates the ESXi 7.0.3-safe behavior:
      - Uppercase letters via CapsLock toggling.
      - Shifted punctuation (e.g. !, @, +, ?, etc.) are treated as unsupported
        and reported as skipped, because ESXi ignored modifier bytes in tests.
    """

    def __init__(self, vm, delay=0.05):
        self.vm = vm
        self.delay = delay
        self.caps_on = False

    def _set_caps(self, wanted):
        if self.caps_on != wanted:
            press_key(self.vm, HID_CAPSLOCK)
            time.sleep(0.1)
            self.caps_on = wanted

    def reset_caps(self):
        press_key(self.vm, HID_CAPSLOCK)
        time.sleep(0.1)
        press_key(self.vm, HID_CAPSLOCK)
        time.sleep(0.1)
        self.caps_on = False

    def special(self, key_name):
        key_name = key_name.upper()
        if key_name not in SPECIAL_KEYS:
            raise ValueError(
                "Unknown special key: {0!r}. Valid: {1}".format(
                    key_name, sorted(SPECIAL_KEYS.keys())
                )
            )
        press_key(self.vm, SPECIAL_KEYS[key_name])
        time.sleep(self.delay)

    def type(self, text):
        skipped = []
        for ch in text:
            if ch not in CHAR_MAP:
                skipped.append(repr(ch))
                continue
            hid, mod = CHAR_MAP[ch]
            if mod == MOD_LSHIFT and ch.isalpha():
                # ESXi-safe path: uppercase via CapsLock
                self._set_caps(True)
                press_key(self.vm, hid)
                time.sleep(self.delay)
            elif mod == MOD_LSHIFT:
                # Shift-modified punctuation/symbols are not reliably supported.
                # Workaround: use numpad keys for a small subset that ESXi accepts.
                if ch == "*":
                    self._set_caps(False)
                    press_key(self.vm, SPECIAL_KEYS["NUMPAD_STAR"])
                    time.sleep(self.delay)
                elif ch == "+":
                    self._set_caps(False)
                    press_key(self.vm, SPECIAL_KEYS["NUMPAD_PLUS"])
                    time.sleep(self.delay)
                else:
                    skipped.append(repr(ch))
            else:
                self._set_caps(False)
                press_key(self.vm, hid)
                time.sleep(self.delay)
        self._set_caps(False)
        return skipped

    def type_line(self, text):
        skipped = self.type(text)
        self.special("ENTER")
        return skipped


def connect_vsphere(host, user, password, port=443, validate_certs=True):
    if not HAS_PYVMOMI:
        raise RuntimeError("pyVmomi is required")
    if validate_certs:
        si = SmartConnect(host=host, user=user, pwd=password, port=port)
    else:
        ctx = ssl._create_unverified_context()
        si = SmartConnect(host=host, user=user, pwd=password, port=port, sslContext=ctx)
    return si

