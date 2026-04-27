#!/usr/bin/env python3

import argparse
import ipaddress
import re
import socket
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import openpyxl

try:
    from zoneinfo import available_timezones
except ImportError:  # pragma: no cover - Python >=3.9 has zoneinfo
    available_timezones = None


NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,18}[A-Za-z0-9])?$")
DOMAIN_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
SPECIAL_CHARS = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def split_list(value: Any) -> Iterable[str]:
    raw = text(value)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def require_key(data: Dict[str, Any], name: str) -> Any:
    if name not in data:
        raise ValueError(f"Missing required parameter '{name}'")
    return data[name]


def required_str(data: Dict[str, Any], name: str, max_len: Optional[int] = None) -> str:
    value = text(require_key(data, name))
    if not value:
        raise ValueError(f"'{name}' must be a non-empty string")
    if max_len is not None and len(value) > max_len:
        raise ValueError(f"'{name}' must be up to {max_len} characters")
    return value


def optional_str(data: Dict[str, Any], name: str, max_len: Optional[int] = None) -> str:
    value = text(data.get(name))
    if max_len is not None and len(value) > max_len:
        raise ValueError(f"'{name}' must be up to {max_len} characters")
    return value


def enum_value(data: Dict[str, Any], name: str, choices: Iterable[str]) -> str:
    value = required_str(data, name).upper()
    allowed = set(choices)
    if value not in allowed:
        raise ValueError(f"'{name}' must be one of: {', '.join(sorted(allowed))}")
    return value


def validate_ipv4_value(name: str, value: Any, optional: bool = False) -> None:
    if optional and is_empty(value):
        return
    raw = text(value)
    try:
        ipaddress.IPv4Address(raw)
    except ValueError:
        raise ValueError(f"'{name}' must be a valid IPv4 address")


def validate_ipv6_value(name: str, value: Any, optional: bool = False) -> None:
    if optional and is_empty(value):
        return
    raw = text(value)
    try:
        ipaddress.IPv6Address(raw)
    except ValueError:
        raise ValueError(f"'{name}' must be a valid IPv6 address")


def validate_ip_value(name: str, value: Any, optional: bool = False) -> None:
    if optional and is_empty(value):
        return
    raw = text(value)
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        raise ValueError(f"'{name}' must be a valid IPv4 or IPv6 address")


def validate_ipv4_netmask(data: Dict[str, Any], name: str) -> None:
    raw = required_str(data, name)
    try:
        mask_int = int(ipaddress.IPv4Address(raw))
    except ValueError:
        raise ValueError(f"'{name}' must be a valid IPv4 network mask")

    inverse = (~mask_int) & 0xFFFFFFFF
    if inverse & (inverse + 1) != 0:
        raise ValueError(f"'{name}' must be a contiguous IPv4 network mask")


def validate_ipv6_prefix_value(name: str, value: Any, optional: bool = False) -> None:
    if optional and is_empty(value):
        return
    try:
        prefix = int(text(value))
    except ValueError:
        raise ValueError(f"'{name}' must be an IPv6 prefix between 1 and 128")
    if prefix < 1 or prefix > 128:
        raise ValueError(f"'{name}' must be an IPv6 prefix between 1 and 128")


def validate_sig_mask(data: Dict[str, Any], name: str) -> None:
    raw = required_str(data, name)
    try:
        validate_ipv4_netmask(data, name)
        return
    except ValueError:
        pass
    validate_ipv6_prefix_value(name, raw)


def is_domain_name(value: str) -> bool:
    if len(value) > 253 or "." not in value:
        return False
    labels = value.rstrip(".").split(".")
    return all(DOMAIN_LABEL_RE.match(label) for label in labels)


def validate_domain_suffix(data: Dict[str, Any], name: str) -> None:
    value = required_str(data, name)
    if not is_domain_name(value):
        raise ValueError(f"'{name}' must be a valid domain suffix")


def is_fqdn(value: str) -> bool:
    return is_domain_name(value)


def validate_ipv4_or_fqdn_item(name: str, value: str) -> None:
    try:
        ipaddress.IPv4Address(value)
        return
    except ValueError:
        pass
    if not is_fqdn(value):
        raise ValueError(f"'{name}' must be a valid IPv4 address or FQDN")


def validate_ipv6_or_fqdn_item(name: str, value: str) -> None:
    try:
        ipaddress.IPv6Address(value)
        return
    except ValueError:
        pass
    if not is_fqdn(value):
        raise ValueError(f"'{name}' must be a valid IPv6 address or FQDN")


def validate_resolvable_ipv4_or_fqdn(data: Dict[str, Any], name: str) -> None:
    value = required_str(data, name)
    try:
        ipaddress.IPv4Address(value)
        return
    except ValueError:
        pass
    if not is_fqdn(value):
        raise ValueError(f"'{name}' must be a valid IPv4 address or resolvable FQDN")
    try:
        socket.getaddrinfo(value, None)
    except socket.gaierror:
        raise ValueError(f"'{name}' FQDN is not resolvable from the controller host")


def validate_password(data: Dict[str, Any], name: str) -> None:
    value = required_str(data, name)
    if len(value) < 8:
        raise ValueError(f"'{name}' must be at least 8 characters")
    if not any(ch.isupper() for ch in value):
        raise ValueError(f"'{name}' must contain at least 1 upper case letter")
    if not any(ch.islower() for ch in value):
        raise ValueError(f"'{name}' must contain at least 1 lower case letter")
    if not any(ch.isdigit() for ch in value):
        raise ValueError(f"'{name}' must contain at least 1 digit")
    if not any(ch in SPECIAL_CHARS for ch in value):
        raise ValueError(f"'{name}' must contain at least 1 special character")


def validate_timezone(data: Dict[str, Any], name: str) -> None:
    value = required_str(data, name)
    if available_timezones is None or value not in available_timezones():
        raise ValueError(f"'{name}' must be a valid timezone")


def validate_appname(data: Dict[str, Any], apptype: str) -> None:
    appname = required_str(data, "appname", max_len=20)
    if not NAME_RE.match(appname):
        raise ValueError("'appname' cannot begin or end with hyphen and can only contain letters, numbers and hyphen")
    if apptype != "EMS" and appname in (text(data.get("vmname")), text(data.get("hostname"))):
        raise ValueError("'appname' cannot be the same as 'vmname' or 'hostname'")


def validate_sheet(data: Dict[str, Any]) -> None:
    platform_type = enum_value(data, "platform_type", ("ESXI", "KVM"))
    validate_resolvable_ipv4_or_fqdn(data, "platform_address")
    required_str(data, "platform_username")
    required_str(data, "platform_password")
    if platform_type == "ESXI":
        required_str(data, "datastore")
    required_str(data, "ovf")
    required_str(data, "vmname", max_len=20)
    enum_value(data, "ipmode", ("DUAL_STACK", "IPV4"))
    required_str(data, "hostname", max_len=20)
    apptype = enum_value(data, "apptype", ("EMS+SBCE", "EMS", "SBCE"))
    validate_appname(data, apptype)

    if apptype != "EMS+SBCE":
        required_str(data, "nwpass")

    if apptype == "EMS":
        enum_value(data, "ems_inst_type", ("PRIMARY", "SECONDARY"))

    validate_ipv4_value("ip0", require_key(data, "ip0"))
    validate_ipv4_netmask(data, "netmask0")
    validate_ipv4_value("gateway", require_key(data, "gateway"))
    validate_ipv6_value("ipv6address0", data.get("ipv6address0"), optional=True)
    validate_ipv6_prefix_value("ipv6prefix0", data.get("ipv6prefix0"), optional=True)
    validate_ipv6_value("ipv6gateway", data.get("ipv6gateway"), optional=True)
    validate_domain_suffix(data, "domain_suffix")

    if apptype != "SBCE":
        required_str(data, "first_last_name")
        required_str(data, "organizational_unit")
        required_str(data, "organization")
        required_str(data, "locality")
        required_str(data, "state_province")
        country = required_str(data, "country")
        if len(country) != 2:
            raise ValueError("'country' must be exactly 2 characters")

    validate_timezone(data, "timezone")

    for item in split_list(data.get("ntpservers")):
        validate_ipv4_or_fqdn_item("ntpservers", item)
    for item in split_list(data.get("ntpipv6")):
        validate_ipv6_or_fqdn_item("ntpipv6", item)
    for item in split_list(require_key(data, "dns")):
        validate_ip_value("dns", item)
    if not list(split_list(data.get("dns"))):
        raise ValueError("'dns' must be a valid IPv4 or IPv6 address")

    if apptype == "SBCE":
        validate_ipv4_value("emsip", require_key(data, "emsip"))
        validate_ipv6_value("emsip_v6", data.get("emsip_v6"), optional=True)

    validate_password(data, "rootpass")
    validate_password(data, "ipcspass")
    validate_password(data, "grubpass")
    if apptype != "SBCE":
        validate_password(data, "ucsecpass")

    for name in ("M1", "M2"):
        required_str(data, name)

    if apptype != "EMS":
        for name in ("A1", "A2", "B1", "B2"):
            required_str(data, name)

    if apptype == "SBCE":
        optional_str(data, "ha_peer_node", max_len=20)
        validate_ip_value("ha_peer_ip", data.get("ha_peer_ip"), optional=True)
        enum_value(data, "sig_iface", ("A1", "A2", "B1", "B2"))
        required_str(data, "sig_name", max_len=20)
        validate_sig_mask(data, "sig_mask")
        validate_ip_value("sig_gw", require_key(data, "sig_gw"))
        validate_ip_value("sig_ip", require_key(data, "sig_ip"))
        validate_ip_value("sig_pub_ip", data.get("sig_pub_ip"), optional=True)

    elif apptype == "EMS+SBCE":
        enum_value(data, "sig_iface", ("A1", "A2", "B1", "B2"))
        required_str(data, "sig_name", max_len=20)
        validate_sig_mask(data, "sig_mask")
        validate_ip_value("sig_gw", require_key(data, "sig_gw"))
        validate_ip_value("sig_ip", require_key(data, "sig_ip"))
        validate_ip_value("sig_pub_ip", data.get("sig_pub_ip"), optional=True)


def load_sheet(ws: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for row in ws.iter_rows(values_only=True):
        key = text(row[0] if row else None)
        if key:
            data[key] = row[1] if len(row) > 1 else None
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate SBCE XLSX configuration.")
    parser.add_argument("path", help="Path to sbce_config.xlsx")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        workbook = openpyxl.load_workbook(Path(args.path), data_only=True)
    except Exception as e:
        print(str(ValueError(str(e))), file=sys.stderr)
        return 1

    for index, sheet in enumerate(workbook.worksheets, start=1):
        try:
            validate_sheet(load_sheet(sheet))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return index

    return 0


if __name__ == "__main__":
    sys.exit(main())
