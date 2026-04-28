#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from module_utils import initial_sbce_web_setup as web_setup  # noqa: E402
from selenium.common.exceptions import TimeoutException  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402


def envelope(status: str, **data: object) -> dict[str, object]:
    return {"ok": True, "status": status, "data": data, "errors": []}


def error(message: str) -> dict[str, object]:
    return {"ok": False, "status": "error", "data": {}, "errors": [message]}


def login(driver, host: str, password: str) -> bool:
    driver.get(f"https://{host}/sbc/")
    if web_setup.has_eula(driver, host):
        return False
    if web_setup.is_login_page(driver):
        web_setup.enter_credentials(driver, password=password)
        return not web_setup.has_login_failed(driver)
    return True


def collect_device_text(driver) -> str:
    try:
        web_setup.wait_for_clickable(driver, By.ID, "menu-device-management").click()
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        texts = []
        for index in range(len(iframes)):
            driver.switch_to.default_content()
            driver.switch_to.frame(index)
            texts.append(driver.execute_script("return document.body ? document.body.innerText : ''") or "")
        driver.switch_to.default_content()
        return "\n".join(texts)
    except TimeoutException:
        driver.switch_to.default_content()
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only SBCE Web UI query shim for kvm_test playbooks")
    parser.add_argument("--host", required=True)
    parser.add_argument("--ucsec-password", required=True)
    parser.add_argument("--check-login", action="store_true")
    parser.add_argument("--check-node", action="store_true")
    parser.add_argument("--check-installable", action="store_true")
    parser.add_argument("--name")
    parser.add_argument("--ip")
    parser.add_argument("--name2")
    parser.add_argument("--ip2")
    args = parser.parse_args()

    driver = web_setup.webdriver.Chrome(options=web_setup.chrome_options)
    try:
        login_ok = login(driver, args.host, args.ucsec_password)
        if args.check_login:
            result = envelope("login_ok" if login_ok else "login_failed", login_ok=login_ok, raw_status="login_ok" if login_ok else "login_failed")
        elif not login_ok:
            result = envelope("login_failed", login_ok=False, raw_status="login_failed")
        elif args.check_node:
            raw_status = collect_device_text(driver)
            identifiers = [value for value in (args.name, args.ip) if value]
            node_present = any(identifier in raw_status for identifier in identifiers)
            result = envelope("present" if node_present else "absent", node_present=node_present, raw_status=raw_status, name=args.name, ip=args.ip)
        elif args.check_installable:
            identifiers = [value for value in (args.name, args.ip, args.name2, args.ip2) if value]
            install_link = web_setup.is_sbce_installable(driver, identifiers)
            raw_status = collect_device_text(driver)
            commissioned = "Commissioned" in raw_status and any(identifier in raw_status for identifier in identifiers)
            result = envelope(
                "installable" if install_link is not None else ("commissioned" if commissioned else "not_installable"),
                installable=install_link is not None,
                commissioned=commissioned,
                raw_status=raw_status,
                name=args.name,
                ip=args.ip,
                name2=args.name2,
                ip2=args.ip2,
            )
        else:
            result = error("no query mode selected")
            print(json.dumps(result))
            return 2
    except Exception as exc:
        result = error(str(exc))
        print(json.dumps(result))
        return 1
    finally:
        driver.quit()

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
