#!/usr/bin/env python3
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
---
module: esxi_console_screenshot
short_description: Capture an ESXi/vCenter virtual machine console screenshot
description:
  - Captures a VMware VM console screenshot using the vSphere SOAP API.
  - Downloads the generated datastore screenshot file over HTTPS using C(requests).
  - Saves the image as PNG at the requested local path.
options:
  hostname:
    description: ESXi or vCenter hostname or IP address.
    required: true
    type: str
  username:
    description: Login user.
    required: true
    type: str
  password:
    description: Login password.
    required: true
    type: str
    no_log: true
  port:
    description: HTTPS port.
    required: false
    type: int
    default: 443
  validate_certs:
    description: Verify TLS certificates.
    required: false
    type: bool
    default: true
  datacenter:
    description:
      - Datacenter name used to scope the VM search.
      - Omit to search from the root folder.
    required: false
    type: str
  esxi_hostname:
    description:
      - When set, the VM must be running on a host whose name matches exactly or by first DNS label.
    required: false
    type: str
  vmname:
    description: Name of the virtual machine.
    required: true
    type: str
    aliases: [name]
  path:
    description: Destination PNG path, including filename.
    required: true
    type: path
  timeout:
    description: Timeout in seconds for vSphere tasks and HTTP download.
    required: false
    type: int
    default: 60
  debug:
    description: Return additional debug logging in C(debug_log).
    required: false
    type: bool
    default: false
  autodelete:
    description: Delete the datastore screenshot file after a successful local download and write.
    required: false
    type: bool
    default: false
requirements:
  - pyVmomi
  - requests
notes:
  - Compatible with Python 3.9 and newer.
  - O(debug=true) returns additional module diagnostics, but never logs credentials or session cookies.
author:
  - SBCE automation
'''

EXAMPLES = r'''
- name: Take ESXi VM console screenshot
  esxi_console_screenshot:
    hostname: "{{ args.platform_address }}"
    username: "{{ args.platform_username }}"
    password: "{{ args.platform_password }}"
    validate_certs: false
    vmname: "{{ args.vmname }}"
    path: "/tmp/{{ args.vmname }}.png"
    autodelete: true
    debug: true
  delegate_to: localhost
'''

RETURN = r'''
path:
  description: PNG file written by the module.
  type: str
  returned: success
mime_type:
  description: MIME type of the written screenshot.
  type: str
  returned: success
bytes_written:
  description: Number of PNG bytes written.
  type: int
  returned: success
datastore_path:
  description: Datastore path returned by the vSphere screenshot task.
  type: str
  returned: success
deleted_remote:
  description: Whether the generated datastore screenshot file was deleted.
  type: bool
  returned: success
debug_log:
  description: Additional diagnostic messages when O(debug=true).
  type: list
  elements: str
  returned: when O(debug=true)
'''

import os
import re
import ssl
import time
import traceback

from ansible.module_utils.basic import AnsibleModule

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from pyVim.connect import Disconnect, SmartConnect
    from pyVmomi import vim
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


SCREENSHOT_PATH_RE = re.compile(r"^\[(?P<datastore>[^\]]+)\]\s*(?P<path>.+)$")


def _debug(log, enabled, message):
    if enabled:
        log.append(message)


def _same_host(actual, expected):
    if not actual or not expected:
        return False
    actual_lower = actual.lower()
    expected_lower = expected.lower()
    return actual_lower == expected_lower or actual_lower.split(".")[0] == expected_lower.split(".")[0]


def _find_datacenter_by_name(content, name):
    view = content.viewManager.CreateContainerView(content.rootFolder, [vim.Datacenter], True)
    try:
        for datacenter in view.view:
            if datacenter.name == name:
                return datacenter
    finally:
        view.Destroy()
    return None


def _datacenter_for_object(obj):
    current = obj
    while current is not None:
        if isinstance(current, vim.Datacenter):
            return current
        current = getattr(current, "parent", None)
    return None


def _search_root(content, datacenter_name):
    if datacenter_name:
        datacenter = _find_datacenter_by_name(content, datacenter_name)
        if datacenter is None:
            raise RuntimeError("Datacenter '{0}' not found".format(datacenter_name))
        return datacenter.vmFolder, datacenter
    return content.rootFolder, None


def _find_vm(content, vmname, datacenter_name=None, esxi_hostname=None):
    root, scoped_datacenter = _search_root(content, datacenter_name)
    view = content.viewManager.CreateContainerView(root, [vim.VirtualMachine], True)
    matches = []
    try:
        for vm in view.view:
            if vm.name != vmname:
                continue
            if esxi_hostname:
                host = getattr(getattr(vm, "runtime", None), "host", None)
                host_name = getattr(host, "name", None)
                if not _same_host(host_name, esxi_hostname):
                    continue
            datacenter = scoped_datacenter or _datacenter_for_object(vm)
            matches.append((vm, datacenter))
    finally:
        view.Destroy()

    if not matches:
        message = "VM '{0}' not found".format(vmname)
        if datacenter_name:
            message += " in datacenter '{0}'".format(datacenter_name)
        if esxi_hostname:
            message += " on host '{0}'".format(esxi_hostname)
        raise RuntimeError(message)
    if len(matches) > 1:
        raise RuntimeError(
            "Multiple VMs named '{0}' matched; specify datacenter or esxi_hostname".format(vmname)
        )
    return matches[0]


def _wait_for_task(task, timeout, description):
    deadline = time.time() + timeout
    while task.info.state in (vim.TaskInfo.State.queued, vim.TaskInfo.State.running):
        if time.time() > deadline:
            raise RuntimeError("Timed out waiting for {0}".format(description))
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.success:
        return task.info.result

    error = getattr(task.info, "error", None)
    if error is not None and getattr(error, "msg", None):
        raise RuntimeError("{0} failed: {1}".format(description, error.msg))
    raise RuntimeError("{0} failed".format(description))


def _parse_datastore_path(datastore_path):
    match = SCREENSHOT_PATH_RE.match(datastore_path or "")
    if not match:
        raise ValueError("Unexpected datastore path returned by screenshot task: {0!r}".format(datastore_path))
    datastore = match.group("datastore")
    remote_path = match.group("path").lstrip("/")
    if not datastore or not remote_path:
        raise ValueError("Incomplete datastore path returned by screenshot task: {0!r}".format(datastore_path))
    return datastore, remote_path


def _build_download_url(hostname, port, datastore_path, datacenter):
    datastore, remote_path = _parse_datastore_path(datastore_path)
    datacenter_name = datacenter.name if datacenter is not None else "ha-datacenter"
    base_url = "https://{0}:{1}/folder/{2}".format(hostname, port, remote_path)
    request = requests.Request(
        "GET",
        base_url,
        params={"dcPath": datacenter_name, "dsName": datastore},
    )
    return request.prepare().url


def _soap_cookie_header(si):
    cookie = getattr(getattr(si, "_stub", None), "cookie", None)
    if not cookie:
        raise RuntimeError("Could not obtain vSphere SOAP session cookie")
    return cookie.split(";", 1)[0]


def _download_screenshot(si, url, validate_certs, timeout):
    session = requests.Session()
    session.verify = validate_certs
    session.headers.update({"Cookie": _soap_cookie_header(si)})
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def _delete_datastore_file(content, datastore_path, datacenter, timeout):
    task = content.fileManager.DeleteDatastoreFile_Task(name=datastore_path, datacenter=datacenter)
    _wait_for_task(task, timeout, "datastore screenshot delete task")


def _connect(hostname, username, password, port, validate_certs):
    if validate_certs:
        return SmartConnect(host=hostname, user=username, pwd=password, port=port)
    context = ssl._create_unverified_context()
    return SmartConnect(host=hostname, user=username, pwd=password, port=port, sslContext=context)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            hostname=dict(type="str", required=True),
            username=dict(type="str", required=True),
            password=dict(type="str", required=True, no_log=True),
            port=dict(type="int", required=False, default=443),
            validate_certs=dict(type="bool", required=False, default=True),
            datacenter=dict(type="str", required=False, default=None),
            esxi_hostname=dict(type="str", required=False, default=None),
            vmname=dict(type="str", required=True, aliases=["name"]),
            path=dict(type="path", required=True),
            timeout=dict(type="int", required=False, default=60),
            debug=dict(type="bool", required=False, default=False),
            autodelete=dict(type="bool", required=False, default=False),
        ),
        supports_check_mode=True,
    )

    if not HAS_PYVMOMI:
        module.fail_json(msg="pyVmomi is required for this module. Install with: pip install pyVmomi")
    if not HAS_REQUESTS:
        module.fail_json(msg="requests is required for this module. Install with: pip install requests")

    hostname = module.params["hostname"]
    username = module.params["username"]
    password = module.params["password"]
    port = module.params["port"]
    validate_certs = module.params["validate_certs"]
    datacenter_name = module.params["datacenter"]
    esxi_hostname = module.params["esxi_hostname"]
    vmname = module.params["vmname"]
    path = os.path.abspath(os.path.expanduser(module.params["path"]))
    timeout = module.params["timeout"]
    debug_enabled = module.params["debug"]
    autodelete = module.params["autodelete"]
    debug_log = []

    if timeout <= 0:
        module.fail_json(msg="timeout must be greater than 0")
    if path.endswith(os.sep) or os.path.isdir(path):
        module.fail_json(msg="path must include the PNG filename, not only a directory")
    if os.path.splitext(path)[1].lower() != ".png":
        module.fail_json(msg="path must end with .png")

    if module.check_mode:
        result = dict(
            changed=False,
            path=path,
            msg="Check mode: screenshot not captured",
            deleted_remote=False,
        )
        if debug_enabled:
            result["debug_log"] = ["Check mode enabled; no screenshot task started"]
        module.exit_json(**result)

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    si = None
    datastore_path = None
    deleted_remote = False
    try:
        _debug(debug_log, debug_enabled, "Connecting to ESXi/vCenter host {0}:{1}".format(hostname, port))
        si = _connect(hostname, username, password, port, validate_certs)
        _debug(debug_log, debug_enabled, "Connected successfully")

        content = si.RetrieveContent()
        _debug(debug_log, debug_enabled, "Searching for VM {0}".format(vmname))
        vm, datacenter = _find_vm(
            content,
            vmname,
            datacenter_name=datacenter_name,
            esxi_hostname=esxi_hostname,
        )
        dc_name = datacenter.name if datacenter is not None else "ha-datacenter"
        _debug(debug_log, debug_enabled, "Found VM {0} in datacenter {1}".format(vm.name, dc_name))

        _debug(debug_log, debug_enabled, "Starting CreateScreenshot_Task")
        datastore_path = _wait_for_task(vm.CreateScreenshot_Task(), timeout, "VM screenshot task")
        _debug(debug_log, debug_enabled, "Screenshot task completed")
        _debug(debug_log, debug_enabled, "Datastore path: {0}".format(datastore_path))

        download_url = _build_download_url(hostname, port, datastore_path, datacenter)
        _debug(debug_log, debug_enabled, "Downloading screenshot from datastore URL: {0}".format(download_url))
        png_data = _download_screenshot(si, download_url, validate_certs, timeout)
        if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
            failure = dict(
                msg="Downloaded screenshot is not a PNG file",
                datastore_path=datastore_path,
            )
            if debug_enabled:
                failure["debug_log"] = debug_log
            module.fail_json(**failure)

        with open(path, "wb") as handle:
            handle.write(png_data)
        bytes_written = len(png_data)
        _debug(debug_log, debug_enabled, "Wrote {0} bytes to {1}".format(bytes_written, path))

        if autodelete:
            _debug(debug_log, debug_enabled, "autodelete enabled")
            _debug(debug_log, debug_enabled, "Deleting remote screenshot {0}".format(datastore_path))
            _delete_datastore_file(content, datastore_path, datacenter, timeout)
            deleted_remote = True
            _debug(debug_log, debug_enabled, "Remote screenshot deleted")

        result = dict(
            changed=True,
            msg="Screenshot captured for '{0}'".format(vmname),
            path=path,
            mime_type="image/png",
            bytes_written=bytes_written,
            datastore_path=datastore_path,
            deleted_remote=deleted_remote,
        )
        if debug_enabled:
            result["debug_log"] = debug_log
        module.exit_json(**result)

    except Exception as e:
        failure = dict(
            msg="Failed to capture ESXi console screenshot for '{0}': {1}".format(vmname, e),
            datastore_path=datastore_path,
            deleted_remote=deleted_remote,
            exception=traceback.format_exc(),
        )
        if debug_enabled:
            failure["debug_log"] = debug_log
        module.fail_json(**failure)
    finally:
        if si is not None:
            try:
                Disconnect(si)
            except Exception:
                pass


if __name__ == "__main__":
    main()
