#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Send text to a VMware VM console via PutUsbScanCodes (USB HID)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: vmware_console_keyboard
short_description: Type strings into a VMware VM virtual console using USB HID scan codes
description:
  - Connects to vCenter or ESXi and sends keystrokes to a virtual machine using C(vm.PutUsbScanCodes).
  - Uses the same HID encoding validated on ESXi 7.0.3 (see notes).
  - Intended for C(community.vmware.vmware_deploy_ovf)-style credentials and C(delegate_to localhost).
options:
  hostname:
    description: vCenter or ESXi hostname or IP.
    type: str
    required: true
  username:
    description: Login user.
    type: str
    required: true
  password:
    description: Login password.
    type: str
    required: true
    no_log: true
  port:
    description: HTTPS port.
    type: int
    default: 443
  validate_certs:
    description: Verify TLS certificates.
    type: bool
    default: true
  datacenter:
    description:
      - Datacenter name used to scope the VM search to that datacenter's VM folder.
      - Omit to search from the root folder (broader search).
    type: str
    required: false
  esxi_hostname:
    description:
      - When set, the VM must be running on a host whose name matches (exact or same first DNS label).
    type: str
    required: false
  vmname:
    description: Name of the virtual machine.
    type: str
    required: true
    aliases: [name]
  char_delay:
    description: Seconds to wait after each key event (float).
    type: float
    default: 0.05
  command_delay:
    description:
      - Default pause in seconds after each command when the command entry does not specify a per-command delay.
    type: float
    default: 2.0
  commands:
    description:
      - List of commands. Each entry is a string, or a two-element list C([string, pause_seconds]).
      - C(pause_seconds) overrides O(command_delay) for that step only.
    type: list
    elements: raw
    required: true
  send_enter:
    description:
      - If true, after typing each command string, send Enter (as in a line of input).
      - If false, only type the string (use embedded newlines in the string where supported, or multiple commands).
    type: bool
    default: true
notes:
  - Requires pyVmomi on the Ansible controller.
  - VMware write API restrictions apply (same class of limitation as other community.vmware modules).
  - On ESXi 7.0.3, shift modifiers are not applied; uppercase uses CapsLock. Many shifted symbols cannot be typed.
  - All VMware object names are case-sensitive.
author:
  - SBCE automation
"""

EXAMPLES = r"""
- name: Post-deploy console input
  vmware_console_keyboard:
    hostname: "{{ vcenter_hostname }}"
    username: "{{ vcenter_username }}"
    password: "{{ vcenter_password }}"
    validate_certs: false
    datacenter: Datacenter1
    esxi_hostname: test-server
    vmname: sbce
    char_delay: 0.2
    command_delay: 2
    commands:
      - ["1", 5]
      - ["primary"]
      - ["10.0.0.5"]
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: Whether keystrokes were sent (true when not check mode and tasks succeeded).
  type: bool
  returned: always
commands_executed:
  description: Number of command entries processed.
  type: int
  returned: success
skipped_characters:
  description: Characters that could not be typed (repr strings), aggregated in order.
  type: list
  returned: success
"""

import ssl
import time
import traceback

try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
except ImportError:
    HAS_PYVMOMI = False
else:
    HAS_PYVMOMI = True

from ansible.module_utils.basic import AnsibleModule

# ---------------------------------------------------------------------------
# ESXi 7.0.3 PutUsbScanCodes: (hid_code << 16) | 0x07
# ---------------------------------------------------------------------------

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
    "2": (0x1F, MOD_NONE),
    "3": (0x20, MOD_NONE),
    "4": (0x21, MOD_NONE),
    "5": (0x22, MOD_NONE),
    "6": (0x23, MOD_NONE),
    "7": (0x24, MOD_NONE),
    "8": (0x25, MOD_NONE),
    "9": (0x26, MOD_NONE),
    "0": (0x27, MOD_NONE),
    "a": (0x04, MOD_NONE),
    "b": (0x05, MOD_NONE),
    "c": (0x06, MOD_NONE),
    "d": (0x07, MOD_NONE),
    "e": (0x08, MOD_NONE),
    "f": (0x09, MOD_NONE),
    "g": (0x0A, MOD_NONE),
    "h": (0x0B, MOD_NONE),
    "i": (0x0C, MOD_NONE),
    "j": (0x0D, MOD_NONE),
    "k": (0x0E, MOD_NONE),
    "l": (0x0F, MOD_NONE),
    "m": (0x10, MOD_NONE),
    "n": (0x11, MOD_NONE),
    "o": (0x12, MOD_NONE),
    "p": (0x13, MOD_NONE),
    "q": (0x14, MOD_NONE),
    "r": (0x15, MOD_NONE),
    "s": (0x16, MOD_NONE),
    "t": (0x17, MOD_NONE),
    "u": (0x18, MOD_NONE),
    "v": (0x19, MOD_NONE),
    "w": (0x1A, MOD_NONE),
    "x": (0x1B, MOD_NONE),
    "y": (0x1C, MOD_NONE),
    "z": (0x1D, MOD_NONE),
    "A": (0x04, MOD_LSHIFT),
    "B": (0x05, MOD_LSHIFT),
    "C": (0x06, MOD_LSHIFT),
    "D": (0x07, MOD_LSHIFT),
    "E": (0x08, MOD_LSHIFT),
    "F": (0x09, MOD_LSHIFT),
    "G": (0x0A, MOD_LSHIFT),
    "H": (0x0B, MOD_LSHIFT),
    "I": (0x0C, MOD_LSHIFT),
    "J": (0x0D, MOD_LSHIFT),
    "K": (0x0E, MOD_LSHIFT),
    "L": (0x0F, MOD_LSHIFT),
    "M": (0x10, MOD_LSHIFT),
    "N": (0x11, MOD_LSHIFT),
    "O": (0x12, MOD_LSHIFT),
    "P": (0x13, MOD_LSHIFT),
    "Q": (0x14, MOD_LSHIFT),
    "R": (0x15, MOD_LSHIFT),
    "S": (0x16, MOD_LSHIFT),
    "T": (0x17, MOD_LSHIFT),
    "U": (0x18, MOD_LSHIFT),
    "V": (0x19, MOD_LSHIFT),
    "W": (0x1A, MOD_LSHIFT),
    "X": (0x1B, MOD_LSHIFT),
    "Y": (0x1C, MOD_LSHIFT),
    "Z": (0x1D, MOD_LSHIFT),
    " ": (0x2C, MOD_NONE),
    "\n": (0x28, MOD_NONE),
    "\t": (0x2B, MOD_NONE),
    "\b": (0x2A, MOD_NONE),
    "-": (0x2D, MOD_NONE),
    "=": (0x2E, MOD_NONE),
    "[": (0x2F, MOD_NONE),
    "]": (0x30, MOD_NONE),
    "\\": (0x31, MOD_NONE),
    ";": (0x33, MOD_NONE),
    "'": (0x34, MOD_NONE),
    "`": (0x35, MOD_NONE),
    ",": (0x36, MOD_NONE),
    ".": (0x37, MOD_NONE),
    "/": (0x38, MOD_NONE),
}


def _host_name_matches(actual, wanted):
    if not actual or not wanted:
        return False
    a, w = actual.lower(), wanted.lower()
    if a == w:
        return True
    return a.split(".")[0] == w.split(".")[0]


def _find_datacenter(content, name):
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
        dc = _find_datacenter(content, datacenter)
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
                if not _host_name_matches(host.name, esxi_hostname):
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


def _press(vm, hid_code):
    spec = vim.vm.UsbScanCodeSpec()
    down = vim.vm.UsbScanCodeSpec.KeyEvent()
    down.usbHidCode = (hid_code << 16) | 0x07
    up = vim.vm.UsbScanCodeSpec.KeyEvent()
    up.usbHidCode = 0
    spec.keyEvents = [down, up]
    return vm.PutUsbScanCodes(spec)


class VMKeyboard(object):
    def __init__(self, vm, delay=0.05):
        self.vm = vm
        self.delay = delay
        self.caps_on = False

    def _set_caps(self, wanted):
        if self.caps_on != wanted:
            _press(self.vm, HID_CAPSLOCK)
            time.sleep(0.1)
            self.caps_on = wanted

    def reset_caps(self):
        _press(self.vm, HID_CAPSLOCK)
        time.sleep(0.1)
        _press(self.vm, HID_CAPSLOCK)
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
        _press(self.vm, SPECIAL_KEYS[key_name])
        time.sleep(self.delay)

    def type(self, text):
        skipped = []
        for ch in text:
            if ch not in CHAR_MAP:
                skipped.append(repr(ch))
                continue
            hid, mod = CHAR_MAP[ch]
            if mod == MOD_LSHIFT and ch.isalpha():
                self._set_caps(True)
                _press(self.vm, hid)
                time.sleep(self.delay)
            elif mod == MOD_LSHIFT:
                skipped.append(repr(ch))
            else:
                self._set_caps(False)
                _press(self.vm, hid)
                time.sleep(self.delay)
        self._set_caps(False)
        return skipped

    def type_line(self, text):
        skipped = self.type(text)
        self.special("ENTER")
        return skipped


def _parse_command_entry(raw, default_pause, module):
    if isinstance(raw, list):
        if len(raw) == 1:
            return str(raw[0]), float(default_pause)
        if len(raw) == 2:
            return str(raw[0]), float(raw[1])
        module.fail_json(
            msg="Each commands entry must be a string or [string] or [string, pause_seconds]. Got: {0!r}".format(
                raw
            )
        )
    if isinstance(raw, (str, bytes, type(None))):
        return str(raw), float(default_pause)
    module.fail_json(
        msg="Invalid commands entry type: {0!r}".format(raw)
    )


def main():
    module = AnsibleModule(
        argument_spec=dict(
            hostname=dict(type="str", required=True),
            username=dict(type="str", required=True),
            password=dict(type="str", required=True, no_log=True),
            port=dict(type="int", default=443),
            validate_certs=dict(type="bool", default=True),
            datacenter=dict(type="str", required=False, default=None),
            esxi_hostname=dict(type="str", required=False, default=None),
            vmname=dict(type="str", required=True, aliases=["name"]),
            char_delay=dict(type="float", default=0.05),
            command_delay=dict(type="float", default=2.0),
            commands=dict(type="list", required=True),
            send_enter=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    if not HAS_PYVMOMI:
        module.fail_json(msg="pyVmomi is required for this module.")

    hostname = module.params["hostname"]
    username = module.params["username"]
    password = module.params["password"]
    port = module.params["port"]
    validate_certs = module.params["validate_certs"]
    datacenter = module.params["datacenter"]
    esxi_hostname = module.params["esxi_hostname"]
    vmname = module.params["vmname"]
    char_delay = module.params["char_delay"]
    command_delay = module.params["command_delay"]
    commands_in = module.params["commands"]
    send_enter = module.params["send_enter"]

    si = None
    try:
        if validate_certs:
            si = SmartConnect(
                host=hostname,
                user=username,
                pwd=password,
                port=port,
            )
        else:
            ctx = ssl._create_unverified_context()
            si = SmartConnect(
                host=hostname,
                user=username,
                pwd=password,
                port=port,
                sslContext=ctx,
            )
    except Exception as e:
        module.fail_json(
            msg="Failed to connect to {0}: {1}".format(hostname, e),
            exception=traceback.format_exc(),
        )

    all_skipped = []
    try:
        content = si.RetrieveContent()
        try:
            vm = find_vm(content, vmname, datacenter=datacenter, esxi_hostname=esxi_hostname)
        except RuntimeError as e:
            module.fail_json(msg=str(e), changed=False)

        if module.check_mode:
            module.exit_json(
                changed=False,
                commands_executed=len(commands_in),
                skipped_characters=[],
                check_mode=True,
            )

        kb = VMKeyboard(vm, delay=char_delay)
        kb.reset_caps()

        for entry in commands_in:
            text, pause = _parse_command_entry(entry, command_delay, module)
            if send_enter:
                skipped = kb.type_line(text)
            else:
                skipped = kb.type(text)
            all_skipped.extend(skipped)
            time.sleep(pause)

        if all_skipped:
            module.warn(
                "Skipped {0} character(s) (cannot type on this ESXi HID path): {1}".format(
                    len(all_skipped), ", ".join(all_skipped)
                )
            )

        module.exit_json(
            changed=True,
            commands_executed=len(commands_in),
            skipped_characters=all_skipped,
        )
    finally:
        if si is not None:
            try:
                Disconnect(si)
            except Exception:
                pass


if __name__ == "__main__":
    main()
