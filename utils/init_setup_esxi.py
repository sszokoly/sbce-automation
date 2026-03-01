#!/usr/bin/env python3
import os
import ssl
import time
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# ESXi 7.0.3 PutUsbScanCodes confirmed working encoding:
#   (hid_code << 16) | 0x07
#
# Confirmed NOT working:
#   - Modifier/Shift byte is completely ignored
#   - Separate shift key events are ignored
#   - AltGr combinations are ignored
#
# Workarounds:
#   - Uppercase letters  -> CapsLock toggle
#   - / * - +            -> Numpad keys (no shift needed)
#   - All other shifted symbols (! @ # $ etc.) -> NOT POSSIBLE
# ---------------------------------------------------------------------------

# Modifier flag kept for CHAR_MAP reference only — never actually sent
MOD_NONE   = 0x00
MOD_LSHIFT = 0x02

HID_CAPSLOCK = 0x39

# ---------------------------------------------------------------------------
# Special keys
# ---------------------------------------------------------------------------
SPECIAL_KEYS = {
    'ENTER':         0x28,
    'ESC':           0x29,
    'BACKSPACE':     0x2A,
    'TAB':           0x2B,
    'SPACE':         0x2C,
    'CAPSLOCK':      0x39,
    # Function keys
    'F1':            0x3A,
    'F2':            0x3B,
    'F3':            0x3C,
    'F4':            0x3D,
    'F5':            0x3E,
    'F6':            0x3F,
    'F7':            0x40,
    'F8':            0x41,
    'F9':            0x42,
    'F10':           0x43,
    'F11':           0x44,
    'F12':           0x45,
    # Navigation
    'INSERT':        0x49,
    'HOME':          0x4A,
    'PAGE_UP':       0x4B,
    'DELETE':        0x4C,
    'END':           0x4D,
    'PAGE_DOWN':     0x4E,
    'RIGHT':         0x4F,
    'LEFT':          0x50,
    'DOWN':          0x51,
    'UP':            0x52,
    # Numpad (confirmed working, no shift needed)
    'NUMPAD_SLASH':  0x54,  # /
    'NUMPAD_STAR':   0x55,  # *
    'NUMPAD_MINUS':  0x56,  # -
    'NUMPAD_PLUS':   0x57,  # +
    'NUMPAD_ENTER':  0x58,
    'NUMPAD_1':      0x59,
    'NUMPAD_2':      0x5A,
    'NUMPAD_3':      0x5B,
    'NUMPAD_4':      0x5C,
    'NUMPAD_5':      0x5D,
    'NUMPAD_6':      0x5E,
    'NUMPAD_7':      0x5F,
    'NUMPAD_8':      0x60,
    'NUMPAD_9':      0x61,
    'NUMPAD_0':      0x62,
    'NUMPAD_DOT':    0x63,  # .
}

# ---------------------------------------------------------------------------
# CHAR_MAP
# Only characters confirmed working on ESXi 7.0.3.
#
# SUPPORTED:
#   a-z         direct HID
#   A-Z         CapsLock trick
#   0-9         direct HID
#   - = [ ] \ ; ' ` , . /    unshifted symbols
#   (space) (enter) (tab) (backspace)
#
# NOT SUPPORTED (shift ignored by ESXi 7.0.3):
#   ! @ # $ % ^ & * ( ) _ + { } | : " ~ < > ?
#   Use a VMKeyboard.special('NUMPAD_STAR') for * if needed.
# ---------------------------------------------------------------------------
CHAR_MAP = {
    # Digits
    '1': (0x1E, MOD_NONE),
    '2': (0x1F, MOD_NONE),
    '3': (0x20, MOD_NONE),
    '4': (0x21, MOD_NONE),
    '5': (0x22, MOD_NONE),
    '6': (0x23, MOD_NONE),
    '7': (0x24, MOD_NONE),
    '8': (0x25, MOD_NONE),
    '9': (0x26, MOD_NONE),
    '0': (0x27, MOD_NONE),
    # Lowercase
    'a': (0x04, MOD_NONE),
    'b': (0x05, MOD_NONE),
    'c': (0x06, MOD_NONE),
    'd': (0x07, MOD_NONE),
    'e': (0x08, MOD_NONE),
    'f': (0x09, MOD_NONE),
    'g': (0x0A, MOD_NONE),
    'h': (0x0B, MOD_NONE),
    'i': (0x0C, MOD_NONE),
    'j': (0x0D, MOD_NONE),
    'k': (0x0E, MOD_NONE),
    'l': (0x0F, MOD_NONE),
    'm': (0x10, MOD_NONE),
    'n': (0x11, MOD_NONE),
    'o': (0x12, MOD_NONE),
    'p': (0x13, MOD_NONE),
    'q': (0x14, MOD_NONE),
    'r': (0x15, MOD_NONE),
    's': (0x16, MOD_NONE),
    't': (0x17, MOD_NONE),
    'u': (0x18, MOD_NONE),
    'v': (0x19, MOD_NONE),
    'w': (0x1A, MOD_NONE),
    'x': (0x1B, MOD_NONE),
    'y': (0x1C, MOD_NONE),
    'z': (0x1D, MOD_NONE),
    # Uppercase (same HID as lowercase, CapsLock used to toggle)
    'A': (0x04, MOD_LSHIFT),
    'B': (0x05, MOD_LSHIFT),
    'C': (0x06, MOD_LSHIFT),
    'D': (0x07, MOD_LSHIFT),
    'E': (0x08, MOD_LSHIFT),
    'F': (0x09, MOD_LSHIFT),
    'G': (0x0A, MOD_LSHIFT),
    'H': (0x0B, MOD_LSHIFT),
    'I': (0x0C, MOD_LSHIFT),
    'J': (0x0D, MOD_LSHIFT),
    'K': (0x0E, MOD_LSHIFT),
    'L': (0x0F, MOD_LSHIFT),
    'M': (0x10, MOD_LSHIFT),
    'N': (0x11, MOD_LSHIFT),
    'O': (0x12, MOD_LSHIFT),
    'P': (0x13, MOD_LSHIFT),
    'Q': (0x14, MOD_LSHIFT),
    'R': (0x15, MOD_LSHIFT),
    'S': (0x16, MOD_LSHIFT),
    'T': (0x17, MOD_LSHIFT),
    'U': (0x18, MOD_LSHIFT),
    'V': (0x19, MOD_LSHIFT),
    'W': (0x1A, MOD_LSHIFT),
    'X': (0x1B, MOD_LSHIFT),
    'Y': (0x1C, MOD_LSHIFT),
    'Z': (0x1D, MOD_LSHIFT),
    # Unshifted symbols (all confirmed working)
    ' ':  (0x2C, MOD_NONE),  # Space
    '\n': (0x28, MOD_NONE),  # Enter
    '\t': (0x2B, MOD_NONE),  # Tab
    '\b': (0x2A, MOD_NONE),  # Backspace
    '-':  (0x2D, MOD_NONE),  # Minus
    '=':  (0x2E, MOD_NONE),  # Equals
    '[':  (0x2F, MOD_NONE),  # Left bracket
    ']':  (0x30, MOD_NONE),  # Right bracket
    '\\': (0x31, MOD_NONE),  # Backslash
    ';':  (0x33, MOD_NONE),  # Semicolon
    "'":  (0x34, MOD_NONE),  # Single quote
    '`':  (0x35, MOD_NONE),  # Backtick
    ',':  (0x36, MOD_NONE),  # Comma
    '.':  (0x37, MOD_NONE),  # Period
    '/':  (0x38, MOD_NONE),  # Forward slash
}

# ---------------------------------------------------------------------------
# VMware helpers
# ---------------------------------------------------------------------------

def find_vm(content, name):
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.VirtualMachine], True
    )
    try:
        for vm in container.view:
            if vm.name == name:
                return vm
    finally:
        container.Destroy()
    raise RuntimeError(f"VM not found: {name}")

# ---------------------------------------------------------------------------
# Low level sender
# ---------------------------------------------------------------------------

def _press(vm, hid_code):
    """
    Send one key press + release.
    Confirmed working encoding on ESXi 7.0.3: (hid << 16) | 0x07
    """
    spec = vim.vm.UsbScanCodeSpec()
    down = vim.vm.UsbScanCodeSpec.KeyEvent()
    down.usbHidCode = (hid_code << 16) | 0x07
    up = vim.vm.UsbScanCodeSpec.KeyEvent()
    up.usbHidCode = 0
    spec.keyEvents = [down, up]
    return vm.PutUsbScanCodes(spec)


# ---------------------------------------------------------------------------
# VMKeyboard
# ---------------------------------------------------------------------------

class VMKeyboard:
    """
    Keyboard sender for ESXi 7.0.3 via PutUsbScanCodes.

    Supported characters:
        a-z, A-Z, 0-9
        - = [ ] \\ ; ' ` , . /
        space, enter (\\n), tab (\\t), backspace (\\b)

    Unsupported due to ESXi 7.0.3 shift key limitation:
        ! @ # $ % ^ & * ( ) _ + { } | : " ~ < > ?
        Use passwords/inputs that avoid these characters.
        Exception: * is available via kb.special('NUMPAD_STAR')

    Always call kb.reset_caps() before first use.

    Example:
        kb = VMKeyboard(vm)
        kb.reset_caps()
        kb.type("Hello World")
        kb.special("ENTER")
        kb.type("password123.")
        kb.special("ENTER")
    """

    def __init__(self, vm, delay=0.05):
        self.vm      = vm
        self.delay   = delay
        self.caps_on = False

    def _set_caps(self, wanted: bool):
        if self.caps_on != wanted:
            _press(self.vm, HID_CAPSLOCK)
            time.sleep(0.1)
            self.caps_on = wanted

    def reset_caps(self):
        """
        Press CapsLock twice to guarantee known OFF state.
        Always call this before typing anything.
        """
        _press(self.vm, HID_CAPSLOCK)
        time.sleep(0.1)
        _press(self.vm, HID_CAPSLOCK)
        time.sleep(0.1)
        self.caps_on = False

    def special(self, key_name):
        """
        Send a special key by name.

        Examples:
            kb.special('ENTER')
            kb.special('TAB')
            kb.special('ESC')
            kb.special('F2')
            kb.special('UP')
            kb.special('NUMPAD_STAR')   # types *
            kb.special('NUMPAD_SLASH')  # types /
            kb.special('NUMPAD_MINUS')  # types -
            kb.special('NUMPAD_PLUS')   # types +
        """
        key_name = key_name.upper()
        if key_name not in SPECIAL_KEYS:
            raise ValueError(
                f"Unknown special key: '{key_name}'.\n"
                f"Available: {sorted(SPECIAL_KEYS.keys())}"
            )
        _press(self.vm, SPECIAL_KEYS[key_name])
        time.sleep(self.delay)

    def type(self, text):
        """
        Type a string into the VM console.
        Unsupported characters are skipped with a warning.
        """
        skipped = []

        for ch in text:
            if ch not in CHAR_MAP:
                skipped.append(repr(ch))
                continue

            hid, mod = CHAR_MAP[ch]

            if mod == MOD_LSHIFT and ch.isalpha():
                # Uppercase letter — use CapsLock
                self._set_caps(True)
                _press(self.vm, hid)
                time.sleep(self.delay)
            elif mod == MOD_LSHIFT:
                # Shifted symbol — not supported on ESXi 7.0.3
                skipped.append(repr(ch))
            else:
                # Normal unshifted character
                self._set_caps(False)
                _press(self.vm, hid)
                time.sleep(self.delay)

        # Always leave CapsLock OFF
        self._set_caps(False)

        if skipped:
            print(
                f"\nWARNING: {len(skipped)} character(s) could not be typed "
                f"(shift key not supported on ESXi 7.0.3):\n"
                f"  {', '.join(skipped)}\n"
                f"Tip: avoid ! @ # $ % ^ & * ( ) _ + especially in passwords.\n"
                f"     Use letters, digits, and: - = [ ] \\ ; ' ` , . /\n"
                f"     Use kb.special('NUMPAD_STAR') for *"
            )

    def type_line(self, text):
        """Type a string and press Enter."""
        self.type(text)
        self.special('ENTER')

    def pause(self, seconds):
        """Wait between wizard screens."""
        time.sleep(seconds)


# ---------------------------------------------------------------------------
# Main — example SBCE first boot wizard automation
# ---------------------------------------------------------------------------

def init_setup():
    vcenter  = "192.168.200.161"
    user     = os.getenv("USER", "root")
    password = os.getenv("PASSWD", "root01")
    vm_name  = "SBCE-VM"

    ctx = ssl._create_unverified_context()
    si = SmartConnect(host=vcenter, user=user, pwd=password, sslContext=ctx)

    try:
        content = si.RetrieveContent()
        vm = find_vm(content, vm_name)
        kb = VMKeyboard(vm, delay=0.1)
        kb.reset_caps()  # always call first

        # --- SBCE first boot wizard example ---
        # Adjust timing and inputs to match your wizard screens

        print("Setting first boot parameters via VM keyboard automation...")
        # Choice 1
        kb.type_line("1")
        time.sleep(6)
        
        # DUAL_STACK
        kb.type_line("")
        time.sleep(2)
        
        # EMS
        kb.type_line("EMS")
        time.sleep(2)
    
        # Network passphrase
        kb.type_line("")
        time.sleep(2)
        
        # Appliance name
        kb.type_line("EMS")
        time.sleep(2)

        # Installation type
        kb.type_line("primary")
        time.sleep(2)
        
        # Management IP address
        kb.type_line("10.10.48.180")
        time.sleep(2)
        
        # Management subnet mask
        kb.type_line("255.255.255.0")
        time.sleep(2)
        
        # Management gateway address
        kb.type_line("10.10.48.254")
        time.sleep(2)
        
        # Management IPv6 address
        kb.type_line("")
        time.sleep(2)
        
        # Management subnet network prefix
        kb.type_line("")
        time.sleep(2)
        
        # Management gateway IPv6 address
        kb.type_line("")
        time.sleep(2)
        
        # NTP server IP address (ipv4)
        kb.type_line("10.10.48.92")
        time.sleep(2)
        
        # NTP server IP address (ipv6)
        kb.type_line("")
        time.sleep(2)
        
        # List of DNS servers (comma-separated)
        kb.type_line("10.10.48.92,10.10.32.92")
        time.sleep(2)
        
        # Domain suffix
        kb.type_line("lab.local")
        time.sleep(2)
        
        # Enter 'Y' if the above information is correct
        kb.type_line("Y")
        time.sleep(3)
        
        # First and last name
        kb.type_line("sbce.lab.local")
        time.sleep(2)
        
        # Organization Unit
        kb.type_line("it")
        time.sleep(2)

        # Organization
        kb.type_line("Avaya")
        time.sleep(2)
        
        # City or Locality
        kb.type_line("Calgary")
        time.sleep(2)
        
        # State or Province
        kb.type_line("AB")
        time.sleep(2)

        # Country code (2 letters)
        kb.type_line("CA")
        time.sleep(2)

        # Enter 'Y' if the above information is correct
        kb.type_line("Y")
        time.sleep(5)

        # Select continent or ocean
        kb.type_line("2")
        time.sleep(2)
        
        # Select country
        kb.type_line("10")
        time.sleep(2)
        
        # Select time zone
        kb.type_line("15")
        time.sleep(2)
        
        # Is the above information OK?
        kb.type_line("1")
        time.sleep(20)
        
        # Proceed further keeping same NTP IP
        kb.type_line("3")
        time.sleep(2)
        
        # Root password
        kb.type_line("r00t10-SBCE")
        time.sleep(2)
        kb.type_line("r00t10-SBCE")
        time.sleep(2)
        
        # ipcs password
        kb.type_line("sbc10-SBCE")
        time.sleep(2)
        kb.type_line("sbc10-SBCE")
        time.sleep(2)
        
        # grub password
        kb.type_line("r00t10-SBCE")
        time.sleep(2)
        kb.type_line("r00t10-SBCE")
        print("Done.")

    finally:
        Disconnect(si)

if __name__ == "__main__":
    init_setup()