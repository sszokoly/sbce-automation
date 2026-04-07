#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Standalone tester for the VMware console keyboard mapping.

Sends each character in CHAR_MAP to the specified VM console and then
triggers CreateScreenshot_Task() so you can visually inspect the result.
"""

from __future__ import absolute_import, division, print_function

import argparse
import datetime
import os
import sys
import time
import urllib.request

from vmware_console_keyboard_utils import (  # type: ignore
    HAS_PYVMOMI,
    CHAR_MAP,
    VMKeyboard,
    connect_vsphere,
    find_datacenter,
    find_vm,
    Disconnect,
    vim,
)

def _get_vm_datacenter(vm_obj):
    cur = vm_obj
    while cur is not None:
        if isinstance(cur, vim.Datacenter):
            return cur
        cur = getattr(cur, "parent", None)
    return None


def _parse_datastore_path(result):
    """
    Returns datastorePath string in the form: "[datastore1] vmfolder/file.png"
    """
    if result is None:
        return None
    # Some versions return a string directly
    if isinstance(result, str):
        return result
    # Some versions return an object containing the path
    for attr in ("screenshotFile", "fileName", "path"):
        if hasattr(result, attr):
            val = getattr(result, attr)
            if isinstance(val, str):
                return val
    return None


def _download_datastore_file(si, content, datacenter_obj, datastore_path, out_path, verify_tls):
    url = content.fileManager.InitiateFileTransferFromDatastore(
        datacenter=datacenter_obj,
        datastorePath=datastore_path,
    )
    # vSphere often returns URLs containing '*' as host placeholder
    url_str = str(url).replace("*", si._stub.host)  # type: ignore[attr-defined]

    headers = {}
    cookie = getattr(si._stub, "cookie", None)  # type: ignore[attr-defined]
    if cookie:
        headers["Cookie"] = cookie

    req = urllib.request.Request(url_str, headers=headers)
    ctx = None
    if not verify_tls:
        import ssl as _ssl

        ctx = _ssl._create_unverified_context()

    with urllib.request.urlopen(req, context=ctx) as resp:  # nosec - intentional
        data = resp.read()
    with open(out_path, "wb") as f:
        f.write(data)
    return url_str


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Send all CHAR_MAP characters to a VMware VM console."
    )
    p.add_argument("--host", required=True, help="vCenter or ESXi hostname/IP")
    p.add_argument("--user", required=True, help="Username")
    p.add_argument("--password", required=True, help="Password")
    p.add_argument("--port", type=int, default=443, help="HTTPS port (default 443)")
    p.add_argument(
        "--no-validate-certs",
        action="store_true",
        help="Do not validate TLS certificates",
    )
    p.add_argument("--datacenter", help="Datacenter name", default=None)
    p.add_argument(
        "--esxi-hostname",
        help="Require VM to run on this ESXi host (name or first label)",
        default=None,
    )
    p.add_argument("--vmname", required=True, help="Virtual machine name")
    p.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay between key presses (seconds, default 0.1)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print characters that would be sent, do not send any keys",
    )
    return p.parse_args(argv)


def main(argv=None):
    if not HAS_PYVMOMI:
        print("pyVmomi is required for this tester", file=sys.stderr)
        return 1

    args = parse_args(argv)

    print(
        "Connecting to {host} as {user}, vm={vm}".format(
            host=args.host, user=args.user, vm=args.vmname
        )
    )
    si = None
    try:
        si = connect_vsphere(
            host=args.host,
            user=args.user,
            password=args.password,
            port=args.port,
            validate_certs=not args.no_validate_certs,
        )
        content = si.RetrieveContent()
        vm = find_vm(
            content,
            args.vmname,
            datacenter=args.datacenter,
            esxi_hostname=args.esxi_hostname,
        )

        print("Connected. VM runtime host:", getattr(vm.runtime.host, "name", "?"))

        if args.dry_run:
            print("Dry run. Characters that would be sent:")
            for ch in sorted(CHAR_MAP.keys()):
                print(ch, end="")
            print()
            return 0

        kb = VMKeyboard(vm, delay=args.delay)
        kb.reset_caps()

        all_skipped = []
        print("Sending characters from CHAR_MAP to VM console...")
        for ch in sorted(CHAR_MAP.keys()):
            print(ch, end="", flush=True)
            skipped = kb.type(ch)
            all_skipped.extend(skipped)
            time.sleep(args.delay)

        print("\nDone sending characters.")
        if all_skipped:
            uniq = sorted(set(all_skipped))
            print(
                "WARNING: {n} character occurrences were skipped: {chars}".format(
                    n=len(all_skipped), chars=", ".join(uniq)
                )
            )

        # Take a screenshot for visual verification
        try:
            print("Requesting VM screenshot via CreateScreenshot_Task()...")
            task = vm.CreateScreenshot_Task()
            # Simple wait loop
            while task.info.state not in ("success", "error"):
                time.sleep(1.0)
            if task.info.state == "success":
                datastore_path = _parse_datastore_path(task.info.result)
                print("Screenshot task completed successfully.")
                if datastore_path:
                    # Resolve datacenter for transfer API
                    if args.datacenter:
                        dc = find_datacenter(content, args.datacenter)
                    else:
                        dc = _get_vm_datacenter(vm)
                    if dc is None:
                        print(
                            "Could not resolve datacenter for VM; cannot download screenshot. "
                            "Datastore path was: {0}".format(datastore_path),
                            file=sys.stderr,
                        )
                    else:
                        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                        out_dir = os.path.join(repo_root, "data", "screenshots")
                        os.makedirs(out_dir, exist_ok=True)
                        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                        out_file = os.path.join(out_dir, "{0}-{1}.png".format(args.vmname, ts))

                        print("Downloading screenshot to:", out_file)
                        _download_datastore_file(
                            si=si,
                            content=content,
                            datacenter_obj=dc,
                            datastore_path=datastore_path,
                            out_path=out_file,
                            verify_tls=not args.no_validate_certs,
                        )
                else:
                    print(
                        "Screenshot task succeeded but no datastore path was returned "
                        "(task.info.result={0!r})".format(task.info.result)
                    )
            else:
                print("Screenshot task failed:", task.info.error)
        except Exception as e:  # pragma: no cover - depends on vSphere backing
            print("Failed to create screenshot:", e, file=sys.stderr)

        return 0
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    finally:
        if si is not None and Disconnect is not None:
            try:
                Disconnect(si)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

