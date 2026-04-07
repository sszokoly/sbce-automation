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

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.vmware_console_keyboard_utils import (  # type: ignore
    HAS_PYVMOMI,
    SmartConnect,
    Disconnect,
    find_vm,
    VMKeyboard,
)


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
