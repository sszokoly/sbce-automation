#!/usr/bin/env python3
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
---
module: kvm_guest_sendkey
short_description: Send keys to a KVM virtual machine console
description:
    - Sends a string or individual keys to a KVM VM console via libvirt.
    - Supports full keyboard including uppercase, shifted symbols, and special keys.
    - Optionally sleeps after sending keys.
options:
    name:
        description: Name of the KVM domain (VM).
        required: true
        type: str
    uri:
        description: libvirt connection URI.
        required: false
        type: str
        default: qemu:///system
    string_send:
        description: String to type into the console followed by ENTER.
        required: false
        type: str
    keys_send:
        description: List of special key names to send (e.g. ENTER, TAB, F2).
        required: false
        type: list
        elements: str
    sleep_time:
        description: Seconds to sleep after sending keys (float supported).
        required: false
        type: float
        default: 0
requirements:
    - libvirt-python
author:
    - Custom Module
'''

EXAMPLES = r'''
# Send a string followed by ENTER
- name: Send IP address
  kvm_guest_sendkey:
    name: SBCE-VM
    string_send: "192.168.1.100"
    sleep_time: 2

# Just press ENTER
- name: Press ENTER
  kvm_guest_sendkey:
    name: SBCE-VM
    keys_send:
      - ENTER

# Send a string without ENTER then sleep
- name: Send hostname
  kvm_guest_sendkey:
    name: SBCE-VM
    string_send: "Sbce-Node-01"
    sleep_time: 1

# Send special keys
- name: Send TAB then F2
  kvm_guest_sendkey:
    name: SBCE-VM
    keys_send:
      - TAB
      - F2
    sleep_time: 0.5

# Send password with symbols
- name: Send password
  kvm_guest_sendkey:
    name: SBCE-VM
    string_send: "Admin@1234!"
    sleep_time: 2

# Send string without ENTER (keys_send not specified, no_enter: true)
- name: Send string no enter
  kvm_guest_sendkey:
    name: SBCE-VM
    string_send: "sometext"
    no_enter: true
'''

RETURN = r'''
msg:
    description: Status message.
    type: str
    returned: always
keys_sent:
    description: List of key codes that were sent.
    type: list
    returned: always
'''

import time
from ansible.module_utils.basic import AnsibleModule

try:
    import libvirt
    HAS_LIBVIRT = True
except ImportError:
    HAS_LIBVIRT = False

# ---------------------------------------------------------------------------
# Key map: character -> list of Linux key codes
# ---------------------------------------------------------------------------

# Linux input key codes
K = {
    'KEY_A': 30,  'KEY_B': 48,  'KEY_C': 46,  'KEY_D': 32,  'KEY_E': 18,
    'KEY_F': 33,  'KEY_G': 34,  'KEY_H': 35,  'KEY_I': 23,  'KEY_J': 36,
    'KEY_K': 37,  'KEY_L': 38,  'KEY_M': 50,  'KEY_N': 49,  'KEY_O': 24,
    'KEY_P': 25,  'KEY_Q': 16,  'KEY_R': 19,  'KEY_S': 31,  'KEY_T': 20,
    'KEY_U': 22,  'KEY_V': 47,  'KEY_W': 17,  'KEY_X': 45,  'KEY_Y': 21,
    'KEY_Z': 44,
    'KEY_0': 11,  'KEY_1': 2,   'KEY_2': 3,   'KEY_3': 4,   'KEY_4': 5,
    'KEY_5': 6,   'KEY_6': 7,   'KEY_7': 8,   'KEY_8': 9,   'KEY_9': 10,
    'KEY_ENTER':      28,
    'KEY_ESC':        1,
    'KEY_BACKSPACE':  14,
    'KEY_TAB':        15,
    'KEY_SPACE':      57,
    'KEY_MINUS':      12,
    'KEY_EQUAL':      13,
    'KEY_LEFTBRACE':  26,
    'KEY_RIGHTBRACE': 27,
    'KEY_BACKSLASH':  43,
    'KEY_SEMICOLON':  39,
    'KEY_APOSTROPHE': 40,
    'KEY_GRAVE':      41,
    'KEY_COMMA':      51,
    'KEY_DOT':        52,
    'KEY_SLASH':      53,
    'KEY_CAPSLOCK':   58,
    'KEY_LEFTSHIFT':  42,
    'KEY_RIGHTSHIFT': 54,
    'KEY_LEFTCTRL':   29,
    'KEY_RIGHTCTRL':  97,
    'KEY_LEFTALT':    56,
    'KEY_RIGHTALT':   100,
    'KEY_F1':         59,  'KEY_F2':  60,  'KEY_F3':  61,  'KEY_F4':  62,
    'KEY_F5':         63,  'KEY_F6':  64,  'KEY_F7':  65,  'KEY_F8':  66,
    'KEY_F9':         67,  'KEY_F10': 68,  'KEY_F11': 87,  'KEY_F12': 88,
    'KEY_INSERT':     110, 'KEY_DELETE': 111,
    'KEY_HOME':       102, 'KEY_END':    107,
    'KEY_PAGEUP':     104, 'KEY_PAGEDOWN': 109,
    'KEY_UP':         103, 'KEY_DOWN':  108,
    'KEY_LEFT':       105, 'KEY_RIGHT': 106,
}

LSHIFT = K['KEY_LEFTSHIFT']

# Character -> list of key codes to send simultaneously
CHAR_MAP = {
    # Digits
    '0': [K['KEY_0']], '1': [K['KEY_1']], '2': [K['KEY_2']],
    '3': [K['KEY_3']], '4': [K['KEY_4']], '5': [K['KEY_5']],
    '6': [K['KEY_6']], '7': [K['KEY_7']], '8': [K['KEY_8']],
    '9': [K['KEY_9']],
    # Lowercase letters
    'a': [K['KEY_A']], 'b': [K['KEY_B']], 'c': [K['KEY_C']],
    'd': [K['KEY_D']], 'e': [K['KEY_E']], 'f': [K['KEY_F']],
    'g': [K['KEY_G']], 'h': [K['KEY_H']], 'i': [K['KEY_I']],
    'j': [K['KEY_J']], 'k': [K['KEY_K']], 'l': [K['KEY_L']],
    'm': [K['KEY_M']], 'n': [K['KEY_N']], 'o': [K['KEY_O']],
    'p': [K['KEY_P']], 'q': [K['KEY_Q']], 'r': [K['KEY_R']],
    's': [K['KEY_S']], 't': [K['KEY_T']], 'u': [K['KEY_U']],
    'v': [K['KEY_V']], 'w': [K['KEY_W']], 'x': [K['KEY_X']],
    'y': [K['KEY_Y']], 'z': [K['KEY_Z']],
    # Uppercase letters
    'A': [LSHIFT, K['KEY_A']], 'B': [LSHIFT, K['KEY_B']],
    'C': [LSHIFT, K['KEY_C']], 'D': [LSHIFT, K['KEY_D']],
    'E': [LSHIFT, K['KEY_E']], 'F': [LSHIFT, K['KEY_F']],
    'G': [LSHIFT, K['KEY_G']], 'H': [LSHIFT, K['KEY_H']],
    'I': [LSHIFT, K['KEY_I']], 'J': [LSHIFT, K['KEY_J']],
    'K': [LSHIFT, K['KEY_K']], 'L': [LSHIFT, K['KEY_L']],
    'M': [LSHIFT, K['KEY_M']], 'N': [LSHIFT, K['KEY_N']],
    'O': [LSHIFT, K['KEY_O']], 'P': [LSHIFT, K['KEY_P']],
    'Q': [LSHIFT, K['KEY_Q']], 'R': [LSHIFT, K['KEY_R']],
    'S': [LSHIFT, K['KEY_S']], 'T': [LSHIFT, K['KEY_T']],
    'U': [LSHIFT, K['KEY_U']], 'V': [LSHIFT, K['KEY_V']],
    'W': [LSHIFT, K['KEY_W']], 'X': [LSHIFT, K['KEY_X']],
    'Y': [LSHIFT, K['KEY_Y']], 'Z': [LSHIFT, K['KEY_Z']],
    # Unshifted symbols
    ' ':  [K['KEY_SPACE']],
    '\n': [K['KEY_ENTER']],
    '\t': [K['KEY_TAB']],
    '\b': [K['KEY_BACKSPACE']],
    '-':  [K['KEY_MINUS']],
    '=':  [K['KEY_EQUAL']],
    '[':  [K['KEY_LEFTBRACE']],
    ']':  [K['KEY_RIGHTBRACE']],
    '\\': [K['KEY_BACKSLASH']],
    ';':  [K['KEY_SEMICOLON']],
    "'":  [K['KEY_APOSTROPHE']],
    '`':  [K['KEY_GRAVE']],
    ',':  [K['KEY_COMMA']],
    '.':  [K['KEY_DOT']],
    '/':  [K['KEY_SLASH']],
    # Shifted symbols
    '!': [LSHIFT, K['KEY_1']], '@': [LSHIFT, K['KEY_2']],
    '#': [LSHIFT, K['KEY_3']], '$': [LSHIFT, K['KEY_4']],
    '%': [LSHIFT, K['KEY_5']], '^': [LSHIFT, K['KEY_6']],
    '&': [LSHIFT, K['KEY_7']], '*': [LSHIFT, K['KEY_8']],
    '(': [LSHIFT, K['KEY_9']], ')': [LSHIFT, K['KEY_0']],
    '_': [LSHIFT, K['KEY_MINUS']], '+': [LSHIFT, K['KEY_EQUAL']],
    '{': [LSHIFT, K['KEY_LEFTBRACE']], '}': [LSHIFT, K['KEY_RIGHTBRACE']],
    '|': [LSHIFT, K['KEY_BACKSLASH']], ':': [LSHIFT, K['KEY_SEMICOLON']],
    '"': [LSHIFT, K['KEY_APOSTROPHE']], '~': [LSHIFT, K['KEY_GRAVE']],
    '<': [LSHIFT, K['KEY_COMMA']], '>': [LSHIFT, K['KEY_DOT']],
    '?': [LSHIFT, K['KEY_SLASH']],
}

# Special key name -> key code (for keys_send argument)
SPECIAL_KEYS = {
    'ENTER':      K['KEY_ENTER'],
    'ESC':        K['KEY_ESC'],
    'BACKSPACE':  K['KEY_BACKSPACE'],
    'TAB':        K['KEY_TAB'],
    'SPACE':      K['KEY_SPACE'],
    'CAPSLOCK':   K['KEY_CAPSLOCK'],
    'F1':         K['KEY_F1'],  'F2':  K['KEY_F2'],
    'F3':         K['KEY_F3'],  'F4':  K['KEY_F4'],
    'F5':         K['KEY_F5'],  'F6':  K['KEY_F6'],
    'F7':         K['KEY_F7'],  'F8':  K['KEY_F8'],
    'F9':         K['KEY_F9'],  'F10': K['KEY_F10'],
    'F11':        K['KEY_F11'], 'F12': K['KEY_F12'],
    'INSERT':     K['KEY_INSERT'],
    'DELETE':     K['KEY_DELETE'],
    'HOME':       K['KEY_HOME'],
    'END':        K['KEY_END'],
    'PAGE_UP':    K['KEY_PAGEUP'],
    'PAGE_DOWN':  K['KEY_PAGEDOWN'],
    'UP':         K['KEY_UP'],
    'DOWN':       K['KEY_DOWN'],
    'LEFT':       K['KEY_LEFT'],
    'RIGHT':      K['KEY_RIGHT'],
}

# ---------------------------------------------------------------------------
# Core sender
# ---------------------------------------------------------------------------

def send_keys_to_domain(domain, key_codes):
    """Send a list of key codes simultaneously to the domain."""
    domain.sendKey(libvirt.VIR_KEYCODE_SET_LINUX, 0, key_codes, len(key_codes), 0)


def string_to_key_events(text):
    """
    Convert a string to a list of key code groups.
    Each group is sent as one simultaneous keypress.
    Returns (events, skipped) where events is list of lists.
    """
    events = []
    skipped = []
    for ch in text:
        if ch in CHAR_MAP:
            events.append(CHAR_MAP[ch])
        else:
            skipped.append(repr(ch))
    return events, skipped


# ---------------------------------------------------------------------------
# Ansible module
# ---------------------------------------------------------------------------

def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type='str', required=True),
            uri=dict(type='str', required=False, default='qemu:///system'),
            string_send=dict(type='str', required=False, default=None),
            keys_send=dict(type='list', elements='str', required=False, default=None),
            no_enter=dict(type='bool', required=False, default=False),
            sleep_time=dict(type='float', required=False, default=0),
        ),
        supports_check_mode=False,
    )

    if not HAS_LIBVIRT:
        module.fail_json(msg="libvirt-python is required. "
                            "Install with: pip install libvirt-python")

    name       = module.params['name']
    uri        = module.params['uri']
    string_send = module.params['string_send']
    keys_send  = module.params['keys_send']
    no_enter   = module.params['no_enter']
    sleep_time = module.params['sleep_time']

    # Connect to libvirt
    try:
        conn = libvirt.open(uri)
        if conn is None:
            module.fail_json(msg=f"Failed to connect to libvirt at '{uri}'")
    except libvirt.libvirtError as e:
        module.fail_json(msg=f"libvirt connection error: {e}")

    # Find domain
    try:
        domain = conn.lookupByName(name)
    except libvirt.libvirtError:
        conn.close()
        module.fail_json(msg=f"VM '{name}' not found via '{uri}'")

    all_keys_sent = []
    skipped_chars = []

    try:
        # Send string
        if string_send is not None:
            events, skipped = string_to_key_events(string_send)
            skipped_chars.extend(skipped)
            for codes in events:
                send_keys_to_domain(domain, codes)
                all_keys_sent.extend(codes)
                time.sleep(0.05)

            # Send ENTER after string unless no_enter is True
            if not no_enter:
                send_keys_to_domain(domain, [K['KEY_ENTER']])
                all_keys_sent.append(K['KEY_ENTER'])

        # Send special keys
        if keys_send:
            for key_name in keys_send:
                key_upper = key_name.upper()
                if key_upper not in SPECIAL_KEYS:
                    conn.close()
                    module.fail_json(
                        msg=f"Unknown key: '{key_name}'. "
                            f"Available: {sorted(SPECIAL_KEYS.keys())}"
                    )
                code = SPECIAL_KEYS[key_upper]
                send_keys_to_domain(domain, [code])
                all_keys_sent.append(code)
                time.sleep(0.05)

        # Sleep after sending
        if sleep_time > 0:
            time.sleep(sleep_time)

    except libvirt.libvirtError as e:
        conn.close()
        module.fail_json(msg=f"Error sending keys to '{name}': {e}")

    conn.close()

    msg = f"Keys sent to '{name}' successfully."
    if skipped_chars:
        msg += f" Skipped unmapped characters: {', '.join(skipped_chars)}"

    module.exit_json(
        changed=True,
        msg=msg,
        keys_sent=all_keys_sent,
        skipped=skipped_chars,
    )


if __name__ == '__main__':
    main()