#!/usr/bin/python

from __future__ import annotations

import contextlib
import io
import traceback

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import initial_sbce_web_setup as web_setup  # type: ignore


def _validate_args(module, args):
    missing = []

    def require(*names):
        for name in names:
            if getattr(args, name) is None:
                missing.append("--{0}".format(name.replace("_", "-")))

    require("host")

    if args.change_password:
        require("ucsec_password")
    elif args.install_sbce:
        require(
            "ucsec_password",
            "appname",
            "dns",
            "sig_iface",
            "sig_name",
            "sig_mask",
            "sig_gw",
            "sig_ip",
        )
    elif args.add_node:
        require("ucsec_password", "type", "name", "ip")
        if args.type not in ("ems", "sbce", "ha"):
            return "--type must be one of: ems, sbce, ha"
        if args.type == "ha" and (not args.name2 or not args.ip2):
            return "--name2 and --ip2 are required when --type is ha"

    if missing:
        return "The following arguments are required for this mode: {0}".format(
            ", ".join(missing)
        )

    return None


def _run(args):
    if args.eula:
        return web_setup.do_eula(host=args.host)

    if args.change_password:
        return web_setup.do_change_password(
            host=args.host,
            ucsec_password=args.ucsec_password,
        )

    if args.install_sbce:
        return web_setup.do_install_sbce(
            host=args.host,
            ucsec_password=args.ucsec_password,
            appname=args.appname,
            dns=args.dns,
            sig_iface=args.sig_iface,
            sig_name=args.sig_name,
            sig_mask=args.sig_mask,
            sig_gw=args.sig_gw,
            sig_ip=args.sig_ip,
            sig_pub_ip=args.sig_pub_ip,
            dns2=args.dns2,
            target_host=args.target_host,
        )

    if args.add_node:
        return web_setup.do_add_node(
            host=args.host,
            ucsec_password=args.ucsec_password,
            type=args.type,
            name=args.name,
            ip=args.ip,
            name2=args.name2,
            ip2=args.ip2,
        )

    return 1


def main():
    module = AnsibleModule(
        argument_spec=dict(
            argv=dict(type="list", elements="str", required=True, no_log=True),
        ),
        supports_check_mode=False,
    )

    argv = module.params["argv"]
    stdout = io.StringIO()
    stderr = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            args = web_setup.parse_args(argv)
    except SystemExit as e:
        rc = int(e.code) if isinstance(e.code, int) else 1
        module.fail_json(
            msg="Failed to parse sbce_web_bootstrap arguments",
            rc=rc,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        )

    validation_error = _validate_args(module, args)
    if validation_error:
        module.fail_json(
            msg=validation_error,
            rc=2,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        )

    web_setup._debug = args.debug
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = _run(args)
    except Exception as e:
        module.fail_json(
            msg=str(e),
            rc=1,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
            exception=traceback.format_exc(),
        )

    result = dict(
        changed=(rc == 0),
        rc=rc,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )

    if rc != 0:
        module.fail_json(msg="sbce_web_bootstrap failed", **result)

    module.exit_json(msg="sbce_web_bootstrap completed", **result)


if __name__ == "__main__":
    main()
