#!/usr/bin/env python3
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
---
module: kvm_console_screenshot
short_description: Capture a KVM virtual machine graphical console screenshot
description:
  - Captures a KVM graphical console screenshot through libvirt or VNC.
  - Saves the image as PNG at the requested path.
options:
  method:
    description: Screenshot transport to use.
    required: false
    type: str
    choices: [libvirt, vnc]
    default: libvirt
  name:
    description: Name of the KVM domain (VM).
    required: false
    type: str
    aliases: [vmname]
  path:
    description: Destination PNG path, including filename.
    required: true
    type: path
  uri:
    description: libvirt connection URI.
    required: false
    type: str
    default: qemu:///system
  screen:
    description: Graphical screen index to capture.
    required: false
    type: int
    default: 0
  host:
    description: VNC host to connect to when I(method=vnc).
    required: false
    type: str
  port:
    description: VNC TCP port to connect to when I(method=vnc).
    required: false
    type: int
  display:
    description: VNC display number to connect to when I(method=vnc). Display 0 maps to TCP port 5900.
    required: false
    type: int
  password:
    description: VNC password when authentication is required.
    required: false
    type: str
  timeout:
    description: VNC operation timeout in seconds when I(method=vnc).
    required: false
    type: float
    default: 30.0
requirements:
  - libvirt-python
  - vncdotool, when method=vnc
author:
  - Custom Module
'''

EXAMPLES = r'''
- name: Take VM console screenshot
  kvm_console_screenshot:
    name: "{{ args['vmname'] }}"
    path: "/tmp/{{ args['vmname'] }}.png"
  become: true
  delegate_to: kvm_host

- name: Take VM console screenshot from controller via VNC
  kvm_console_screenshot:
    method: vnc
    host: "{{ hostvars['kvm_host'].ansible_host }}"
    display: 0
    path: "/tmp/{{ args['vmname'] }}.png"
  delegate_to: localhost
'''

RETURN = r'''
path:
  description: PNG file written by the module.
  type: str
  returned: success
mime_type:
  description: MIME type returned by libvirt before conversion, or image/png for VNC.
  type: str
  returned: success
bytes_written:
  description: Number of PNG bytes written.
  type: int
  returned: success
'''

import os
import shutil
import struct
import subprocess
import sys
import zlib

from ansible.module_utils.basic import AnsibleModule

try:
    import libvirt
    HAS_LIBVIRT = True
except ImportError:
    HAS_LIBVIRT = False

try:
    import vncdotool  # noqa: F401
    HAS_VNCDOTOOL = True
except ImportError:
    HAS_VNCDOTOOL = False


def _png_chunk(kind, payload):
    return (
        struct.pack("!I", len(payload))
        + kind
        + payload
        + struct.pack("!I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _rgb_to_png(width, height, rgb):
    if len(rgb) != width * height * 3:
        raise ValueError("RGB data length does not match image dimensions")

    raw = bytearray()
    stride = width * 3
    for row in range(height):
        raw.append(0)  # PNG filter type 0: None
        start = row * stride
        raw.extend(rgb[start:start + stride])

    header = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _png_chunk(b"IEND", b"")
    )


def _read_ppm_token(data, offset):
    length = len(data)
    while offset < length:
        byte = data[offset]
        if byte in b" \t\r\n":
            offset += 1
            continue
        if byte == ord("#"):
            while offset < length and data[offset] not in b"\r\n":
                offset += 1
            continue
        break

    start = offset
    while offset < length and data[offset] not in b" \t\r\n":
        offset += 1

    if start == offset:
        raise ValueError("Unexpected end of PPM data")

    return data[start:offset], offset


def _scale_sample(value, maxval):
    if maxval == 255:
        return value
    return int(round((value * 255) / maxval))


def _ppm_to_png(data):
    magic, offset = _read_ppm_token(data, 0)
    width_token, offset = _read_ppm_token(data, offset)
    height_token, offset = _read_ppm_token(data, offset)
    maxval_token, offset = _read_ppm_token(data, offset)

    width = int(width_token)
    height = int(height_token)
    maxval = int(maxval_token)
    if width <= 0 or height <= 0:
        raise ValueError("PPM image dimensions must be positive")
    if maxval <= 0 or maxval > 65535:
        raise ValueError("Unsupported PPM maxval: {0}".format(maxval))

    if magic == b"P6":
        if offset >= len(data) or data[offset] not in b" \t\r\n":
            raise ValueError("Invalid binary PPM raster separator")
        offset += 1

        samples = width * height * 3
        if maxval < 256:
            raster = data[offset:offset + samples]
            if len(raster) != samples:
                raise ValueError("Truncated binary PPM raster data")
            if maxval == 255:
                rgb = raster
            else:
                rgb = bytes(_scale_sample(value, maxval) for value in raster)
        else:
            raster_len = samples * 2
            raster = data[offset:offset + raster_len]
            if len(raster) != raster_len:
                raise ValueError("Truncated 16-bit binary PPM raster data")
            rgb = bytes(
                _scale_sample((raster[i] << 8) | raster[i + 1], maxval)
                for i in range(0, raster_len, 2)
            )

    elif magic == b"P3":
        values = []
        for _ in range(width * height * 3):
            token, offset = _read_ppm_token(data, offset)
            values.append(_scale_sample(int(token), maxval))
        rgb = bytes(values)
    else:
        raise ValueError("Unsupported PPM magic: {0!r}".format(magic))

    return _rgb_to_png(width, height, rgb)


def _capture_screenshot(conn, domain, screen):
    chunks = []
    stream = conn.newStream(0)

    def sink(_stream, chunk, _opaque):
        chunks.append(chunk)
        return len(chunk)

    try:
        mime_type = domain.screenshot(stream, screen, 0)
        stream.recvAll(sink, None)
        stream.finish()
    except Exception:
        try:
            stream.abort()
        except Exception:
            pass
        raise

    return mime_type, b"".join(chunks)


def _write_libvirt_screenshot(name, path, uri, screen, module):
    if not HAS_LIBVIRT:
        module.fail_json(msg="libvirt-python is required for method=libvirt. Install with: pip install libvirt-python")

    conn = None
    try:
        conn = libvirt.open(uri)
        if conn is None:
            module.fail_json(msg="Failed to connect to libvirt at '{0}'".format(uri))

        try:
            domain = conn.lookupByName(name)
        except libvirt.libvirtError:
            module.fail_json(msg="VM '{0}' not found via '{1}'".format(name, uri))

        mime_type, image_data = _capture_screenshot(conn, domain, screen)

        if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            png_data = image_data
        elif image_data.startswith((b"P6", b"P3")):
            png_data = _ppm_to_png(image_data)
        else:
            module.fail_json(
                msg="Unsupported screenshot format returned by libvirt",
                mime_type=mime_type,
            )

        with open(path, "wb") as handle:
            handle.write(png_data)

        return "Screenshot captured for '{0}'".format(name), mime_type, len(png_data)

    except libvirt.libvirtError as e:
        module.fail_json(msg="libvirt error while capturing screenshot for '{0}': {1}".format(name, e))
    finally:
        if conn is not None:
            conn.close()


def _vnc_endpoint(host, port, display):
    if port is not None:
        return "{0}::{1}".format(host, port)
    return "{0}:{1}".format(host, display)


def _find_vncdo():
    candidates = [
        os.path.join(os.path.dirname(sys.executable), "vncdo"),
        shutil.which("vncdo"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _write_vnc_screenshot(host, port, display, password, timeout, path, module):
    if not HAS_VNCDOTOOL:
        module.fail_json(msg="vncdotool is required for method=vnc. Install with: pip install vncdotool")

    endpoint = _vnc_endpoint(host, port, display)
    vncdo = _find_vncdo()
    if vncdo is None:
        module.fail_json(msg="vncdo executable was not found for method=vnc")

    command = [vncdo, "--server", endpoint, "--timeout", str(timeout)]
    if password:
        command.extend(["--password", password])
    command.extend(["capture", path])

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout + 5,
        )
        bytes_written = os.path.getsize(path)
        return "Screenshot captured from VNC endpoint '{0}'".format(endpoint), "image/png", bytes_written
    except subprocess.TimeoutExpired as e:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            bytes_written = os.path.getsize(path)
            return (
                "Screenshot captured from VNC endpoint '{0}', but vncdo did not exit before timeout: {1}".format(
                    endpoint, e
                ),
                "image/png",
                bytes_written,
            )
        module.fail_json(msg="Timed out capturing VNC screenshot from '{0}'".format(endpoint))
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        stdout = (e.stdout or "").strip()
        details = stderr or stdout or "vncdo exited with status {0}".format(e.returncode)
        module.fail_json(msg="Failed to capture VNC screenshot from '{0}': {1}".format(endpoint, details))
    except Exception as e:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            bytes_written = os.path.getsize(path)
            return (
                "Screenshot captured from VNC endpoint '{0}', but vncdo did not return cleanly: {1}".format(
                    endpoint, e
                ),
                "image/png",
                bytes_written,
            )
        module.fail_json(msg="Failed to capture VNC screenshot from '{0}': {1}".format(endpoint, e))


def main():
    module = AnsibleModule(
        argument_spec=dict(
            method=dict(type="str", required=False, default="libvirt", choices=["libvirt", "vnc"]),
            name=dict(type="str", required=False, aliases=["vmname"]),
            path=dict(type="path", required=True),
            uri=dict(type="str", required=False, default="qemu:///system"),
            screen=dict(type="int", required=False, default=0),
            host=dict(type="str", required=False),
            port=dict(type="int", required=False),
            display=dict(type="int", required=False),
            password=dict(type="str", required=False, no_log=True),
            timeout=dict(type="float", required=False, default=30.0),
        ),
        supports_check_mode=True,
    )

    method = module.params["method"]
    name = module.params["name"]
    path = os.path.abspath(os.path.expanduser(module.params["path"]))
    uri = module.params["uri"]
    screen = module.params["screen"]
    host = module.params["host"]
    port = module.params["port"]
    display = module.params["display"]
    password = module.params["password"]
    timeout = module.params["timeout"]

    if path.endswith(os.sep) or os.path.isdir(path):
        module.fail_json(msg="path must include the PNG filename, not only a directory")
    if os.path.splitext(path)[1].lower() != ".png":
        module.fail_json(msg="path must end with .png")

    if method == "libvirt" and not name:
        module.fail_json(msg="name is required when method=libvirt")
    if method == "vnc":
        if not host:
            module.fail_json(msg="host is required when method=vnc")
        if port is None and display is None:
            module.fail_json(msg="port or display is required when method=vnc")

    if module.check_mode:
        module.exit_json(changed=False, method=method, path=path, msg="Check mode: screenshot not captured")

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    try:
        if method == "libvirt":
            msg, mime_type, bytes_written = _write_libvirt_screenshot(name, path, uri, screen, module)
        else:
            msg, mime_type, bytes_written = _write_vnc_screenshot(host, port, display, password, timeout, path, module)
    except Exception as e:
        module.fail_json(msg="Failed to capture screenshot for '{0}': {1}".format(name, e))

    module.exit_json(
        changed=True,
        msg=msg,
        method=method,
        path=path,
        mime_type=mime_type,
        bytes_written=bytes_written,
    )


if __name__ == "__main__":
    main()
