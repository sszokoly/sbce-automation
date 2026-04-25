#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Completes the installation of Avaya SBCE via Web UI.

import sys
import time
import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from typing import Optional

chrome_options = Options()
chrome_options.add_argument('--ignore-certificate-errors')
chrome_options.add_argument('--ignore-ssl-errors')
chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--window-size=1920,1080')

WAIT_TIMEOUT = 5

_debug = True


def _log(msg: str) -> None:
    if _debug:
        print(msg)


def wait_for(driver: WebDriver, by: str, selector: str, timeout: int = WAIT_TIMEOUT) -> WebElement:
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def wait_for_clickable(driver: WebDriver, by: str, selector: str, timeout: int = WAIT_TIMEOUT) -> WebElement:
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )


def element_exists(driver: WebDriver, by: str, selector: str, timeout: int = WAIT_TIMEOUT) -> bool:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return True
    except TimeoutException:
        return False


def get_page_error(driver: WebDriver, timeout: int = 3) -> Optional[str]:
    selectors = [
        (By.CSS_SELECTOR, "div.error-message"),
        (By.CSS_SELECTOR, ".error-message"),
        (By.CSS_SELECTOR, ".alert-danger"),
        (By.CSS_SELECTOR, ".validation-summary-errors"),
        (By.XPATH, "//*[contains(@class, 'error') and normalize-space()]")
    ]

    for by, selector in selectors:
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((by, selector))
            )
            text = element.text.strip()
            if text:
                return text
        except TimeoutException:
            continue

    return None


def has_eula(driver: WebDriver, host: str) -> bool:
    action_url = f"https://{host}/sbc/eula/"
    selector = f"form[action='{action_url}'][method='post']"
    return element_exists(driver, By.CSS_SELECTOR, selector, timeout=5)


def confirm_eula(driver: WebDriver) -> None:
    checkbox = wait_for_clickable(driver, By.ID, "confirm")
    if not checkbox.is_selected():
        checkbox.click()
    wait_for_clickable(driver, By.XPATH, "//button[text()='Proceed']").click()
    WebDriverWait(driver, WAIT_TIMEOUT).until(EC.staleness_of(checkbox))


def is_login_page(driver: WebDriver) -> bool:
    return element_exists(driver, By.ID, "username", timeout=5)


def enter_credentials(driver: WebDriver, username: str = "ucsec", password: str = "ucsec") -> None:
    username_field = wait_for_clickable(driver, By.ID, "username")
    driver.execute_script("arguments[0].removeAttribute('disabled')", username_field)
    username_field.clear()
    username_field.send_keys(username)
    wait_for_clickable(driver, By.ID, "login-submit").click()

    password_field = wait_for_clickable(driver, By.ID, "password")
    password_field.clear()
    password_field.send_keys(password)
    wait_for_clickable(driver, By.ID, "login-submit").click()


def has_login_failed(driver: WebDriver) -> bool:
    return element_exists(
        driver,
        By.XPATH,
        "//div[@class='error-message' and contains(text(), 'The supplied credentials are invalid. Please correct them and try again.')]",
        timeout=5
    )


def is_change_password(driver: WebDriver) -> bool:
    return element_exists(driver, By.ID, "new-password", timeout=5)


def change_password(driver: WebDriver, ucsec_password: str) -> None:
    wait_for_clickable(driver, By.ID, "current-password").send_keys("ucsec")
    wait_for_clickable(driver, By.ID, "new-password").send_keys(ucsec_password)
    wait_for_clickable(driver, By.ID, "repeat-password").send_keys(ucsec_password)
    wait_for_clickable(driver, By.XPATH, "//button[text()='Change Password']").click()


def has_password_changed(driver: WebDriver) -> bool:
    return element_exists(
        driver,
        By.XPATH,
        "//div[@class='error-message' and contains(text(), 'Your password has been changed')]",
        timeout=5
    )


def is_sbce_installable(driver: WebDriver, host: str) -> Optional[WebElement]:
    wait_for_clickable(driver, By.ID, "menu-device-management").click()

    iframes = WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_all_elements_located((By.TAG_NAME, "iframe"))
    )
    for i in range(len(iframes)):
        driver.switch_to.default_content()
        driver.switch_to.frame(i)
        try:
            install_link = wait_for_clickable(
                driver,
                By.XPATH,
                f"//tr[td[text()='{host}']]//a[text()='Install']",
                timeout=3
            )
            return install_link
        except TimeoutException:
            continue

    driver.switch_to.default_content()
    return None

def has_add_button(driver: WebDriver) -> Optional[WebElement]:
    wait_for_clickable(driver, By.ID, "menu-device-management").click()

    iframes = WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_all_elements_located((By.TAG_NAME, "iframe"))
    )
    for i in range(len(iframes)):
        driver.switch_to.default_content()
        driver.switch_to.frame(i)
        try:
            # <input type="button" value="Add" onclick="addDevice()">
            return wait_for_clickable(
                driver,
                By.XPATH,
                "//input[@type='button' and @value='Add' and @onclick='addDevice()']",
                timeout=3
            )
        except TimeoutException:
            continue

    driver.switch_to.default_content()
    return None

def install_sbce(
    install_link: WebElement,
    driver: WebDriver,
    appname: str,
    dns: str,
    sig_iface: str,
    sig_name: str,
    sig_mask: str,
    sig_gw: str,
    sig_ip: str,
    sig_pub_ip: Optional[str] = None,
    dns2: Optional[str] = None,
) -> bool:
    original_window = driver.current_window_handle
    install_link.click()

    WebDriverWait(driver, WAIT_TIMEOUT).until(lambda d: len(d.window_handles) > 1)
    for handle in driver.window_handles:
        if handle != original_window:
            driver.switch_to.window(handle)
            break

    wait_for_clickable(driver, By.ID, "txtApplianceName").send_keys(appname)

    primary_dns = wait_for_clickable(driver, By.ID, "primary-dns")
    primary_dns.clear()
    primary_dns.send_keys(dns)

    if dns2:
        secondary_dns = wait_for_clickable(driver, By.ID, "secondary-dns")
        secondary_dns.clear()
        secondary_dns.send_keys(dns2)

    sig_name_input = wait_for_clickable(driver, By.NAME, "txtName")
    sig_name_input.clear()
    sig_name_input.send_keys(sig_name)

    gw_input = wait_for_clickable(driver, By.NAME, "txtDefaultGateway")
    gw_input.clear()
    gw_input.send_keys(sig_gw)

    mask_input = wait_for_clickable(driver, By.NAME, "txtSubnetMask")
    mask_input.clear()
    mask_input.send_keys(sig_mask)

    select_element = wait_for_clickable(driver, By.NAME, "selInterface")
    Select(select_element).select_by_visible_text(sig_iface)

    sig_ip_input = wait_for_clickable(driver, By.NAME, "txtIP_1")
    sig_ip_input.clear()
    sig_ip_input.send_keys(sig_ip)

    if sig_pub_ip:
        pub_ip_input = wait_for_clickable(driver, By.NAME, "txtPublicIP_1")
        pub_ip_input.clear()
        pub_ip_input.send_keys(sig_pub_ip)

    finish_button = wait_for_clickable(driver, By.ID, "slideForward")
    finish_button.click()

    page_error = get_page_error(driver, timeout=3)
    if page_error:
        raise RuntimeError(f"Install failed: {page_error}")

    driver.close()
    driver.switch_to.window(original_window)

    commissioned = False
    deadline = time.time() + 60

    while time.time() < deadline:
        try:
            wait_for_clickable(driver, By.ID, "menu-device-management").click()
            driver.switch_to.default_content()
            driver.switch_to.frame("page-frame")

            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, f"//tr[@data-name='{appname}']"))
            )

            status_elements = driver.find_elements(
                By.XPATH,
                f"//tr[@data-name='{appname}']//span[@class='status-commissioned']"
            )

            if status_elements:
                text = driver.execute_script(
                    "return arguments[0].innerText", status_elements[0]
                ).strip()
                if "Commissioned" in text:
                    commissioned = True
                    break

        except (NoSuchElementException, TimeoutException):
            pass
        finally:
            driver.switch_to.default_content()

        time.sleep(3)

    if not commissioned:
        raise RuntimeError(f"'{appname}' did not reach Commissioned state within 60 seconds.")

    return commissioned

def add_node(
    add_button: WebElement,
    driver: WebDriver,
    type: str,
    name: str,
    ip: str,
    name2: Optional[str] = None,
    ip2: Optional[str] = None,
) -> None:

    add_button.click()
    driver.switch_to.default_content()

    if type == "sbce":
        wait_for_clickable(driver, By.ID, "node-type-sbce-single").click()
    elif type == "ems":
        wait_for_clickable(driver, By.ID, "node-type-ems-secondary").click()
    else:
        wait_for_clickable(driver, By.ID, "node-type-sbce-ha").click()

    name_input = wait_for_clickable(driver, By.NAME, "txtAppName")
    name_input.clear()
    name_input.send_keys(name)

    ip_input = wait_for_clickable(driver, By.NAME, "txtMgmtIp")
    ip_input.clear()
    ip_input.send_keys(ip)

    if type == "ha" and name2 and ip2:
        name2_input = wait_for_clickable(driver, By.NAME, "txtSecAppName")
        name2_input.clear()
        name2_input.send_keys(name2)

        ip2_input = wait_for_clickable(driver, By.NAME, "txtSecMgmtIp")
        ip2_input.clear()
        ip2_input.send_keys(ip2)

    finish_button = wait_for_clickable(driver, By.ID, "slideForward")
    finish_button.click()

    page_error = get_page_error(driver, timeout=3)
    if page_error:
        raise RuntimeError(f"Add failed: {page_error}")

    WebDriverWait(driver, WAIT_TIMEOUT).until(EC.staleness_of(finish_button))


def do_eula(host: str) -> int:
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(f"https://{host}/sbc/")
        if has_eula(driver, host):
            confirm_eula(driver)
            _log("EULA accepted.")
        else:
            _log("No EULA page found.")
        return 0
    except Exception as e:
        _log(f"EULA failed: {e}")
    finally:
        driver.quit()
    return 1


def do_change_password(host: str, ucsec_password: str) -> int:
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(f"https://{host}/sbc/")
        if has_eula(driver, host):
            confirm_eula(driver)
        if is_login_page(driver):
            enter_credentials(driver)
            if has_login_failed(driver):
                _log("Login failed with default credentials.")
                return 1
            if is_change_password(driver):
                change_password(driver, ucsec_password)
                if not has_password_changed(driver):
                    _log("Password change failed.")
                    return 1
                _log("Password changed successfully.")
            else:
                _log("No change-password prompt found.")
        return 0
    except Exception as e:
        _log(f"Password change failed: {e}")
        return 1
    finally:
        driver.quit()


def do_install_sbce(
    host: str,
    ucsec_password: str,
    appname: str,
    dns: str,
    sig_iface: str,
    sig_name: str,
    sig_mask: str,
    sig_gw: str,
    sig_ip: str,
    sig_pub_ip: Optional[str] = None,
    dns2: Optional[str] = None,
    target_host: Optional[str] = None,
) -> int:
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(f"https://{host}/sbc/")
        if is_login_page(driver):
            enter_credentials(driver, password=ucsec_password)
            if has_login_failed(driver):
                _log("Login failed with the provided credentials.")
                return 1
        install_link = is_sbce_installable(driver, target_host or host)
        if install_link is not None:
            install_sbce(
                install_link, driver, appname, dns,
                sig_iface, sig_name, sig_mask, sig_gw, sig_ip,
                sig_pub_ip=sig_pub_ip, dns2=dns2,
            )
            _log(f"SBCE '{appname}' installed and commissioned.")
        else:
            _log("No installable SBCE found.")
        return 0
    except Exception as e:
        msg = str(e)
        _log(msg if msg.startswith("Install failed:") else f"Install failed: {msg}")
        return 1
    finally:
        driver.quit()


def do_add_node(
    host: str,
    ucsec_password: str,
    type: str,
    name: str,
    ip: str,
    name2: Optional[str] = None,
    ip2: Optional[str] = None,
) -> int:
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(f"https://{host}/sbc/")
        if is_login_page(driver):
            enter_credentials(driver, password=ucsec_password)
            if has_login_failed(driver):
                _log("Login failed with the provided credentials.")
                return 1
        add_button = has_add_button(driver)
        if add_button is not None:
            add_node(add_button, driver, type, name, ip, name2, ip2)
            if type == "ha":
                _log(f"Node '{name}' and Node '{name2} added.")
            else:
                _log(f"Node '{name}' added.")
        else:
            _log("Add button not available.")
        return 0
    except Exception as e:
        try:
            error_div = driver.find_element(By.CSS_SELECTOR, "div.error-message")
            page_error = error_div.text.strip()
        except NoSuchElementException:
            page_error = None
        if page_error:
            msg = f"Add failed: {page_error}"
        else:
            msg = f"Add failed: {e}"
        _log(msg)
    finally:
        driver.quit()
    return 1


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated initial setup of Avaya SBCE via web interface."
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--eula",            action="store_true", help="Accept the EULA")
    mode.add_argument("--change-password", action="store_true", help="Change the ucsec password from default")
    mode.add_argument("--install-sbce",    action="store_true", help="Login and install the SBCE appliance")
    mode.add_argument("--add-node",        action="store_true", help="Add SBCE or EMS node(s)")

    common = parser.add_argument_group("common arguments")
    common.add_argument("--host",           help="IP or hostname of the EMS (e.g. 192.168.122.10)")
    common.add_argument("--ucsec-password", help="ucsec account password")
    common.add_argument("--debug",          action="store_true", help="Enable debug output")

    install = parser.add_argument_group("--install-sbce arguments")
    install.add_argument("--appname",    help="Appliance name")
    install.add_argument("--dns",        help="Primary DNS server IP")
    install.add_argument("--dns2",       help="Secondary DNS server IP")
    install.add_argument("--sig-iface",  help="Signaling interface (e.g. A1)")
    install.add_argument("--sig-name",   help="Signaling interface name (e.g. A1_internal)")
    install.add_argument("--sig-mask",   help="Signaling interface subnet mask")
    install.add_argument("--sig-gw",     help="Signaling interface default gateway")
    install.add_argument("--sig-ip",     help="SIP signaling IP address")
    install.add_argument("--sig-pub-ip", help="Public IP for signaling interface")
    install.add_argument("--target-host", help="Installable SBCE management IP or hostname when different from EMS host")

    add = parser.add_argument_group("--add-node arguments")
    add.add_argument("--type",  help="Node type: sbce, ems, or ha")
    add.add_argument("--name",  help="Primary node name")
    add.add_argument("--ip",    help="Primary node management IP")
    add.add_argument("--name2", help="Secondary node name (HA only)")
    add.add_argument("--ip2",   help="Secondary node management IP (HA only)")

    return parser.parse_args(argv)


def _require(args: argparse.Namespace, *names: str) -> None:
    missing = [f"--{n.replace('_', '-')}" for n in names if getattr(args, n) is None]
    if missing:
        print(f"error: the following arguments are required for this mode: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    #sys.argv += ["--eula", "--host", "192.168.122.20", "--debug"]
    #sys.argv += ["--change-password", "--host", "192.168.122.20", "--ucsec-password", "cmb@Dm1n", "--debug"]
    # sys.argv += [
    #     "--install-sbce",
    #     "--host",           "192.168.122.10",
    #     "--ucsec-password", "cmb@Dm1n",
    #     "--appname",        "sbce-vm",
    #     "--dns",            "192.168.122.1",
    #     "--sig-iface",      "A1",
    #     "--sig-name",       "A1_internal",
    #     "--sig-mask",       "255.255.255.0",
    #     "--sig-gw",         "192.168.122.1",
    #     "--sig-ip",         "192.168.122.11",
    #     "--sig-pub-ip",     "142.219.32.2",
    #     "--debug"
    # ]

    # sys.argv += [
    #     "--add-node",
    #     "--host",           "192.168.122.20",
    #     "--ucsec-password", "cmb@Dm1n",
    #     "--type",           "ha",
    #     "--name",           "sbce1",
    #     "--ip",             "192.168.122.21",
    #     "--name2",          "sbce2",
    #     "--ip2",            "192.168.122.22",
    #     "--debug"
    # ]

    args = parse_args()
    _debug = args.debug
    _require(args, "host")

    if args.eula:
        rv = do_eula(host=args.host)

    elif args.change_password:
        _require(args, "ucsec_password")
        rv = do_change_password(host=args.host, ucsec_password=args.ucsec_password)

    elif args.install_sbce:
        _require(args, "ucsec_password", "appname", "dns",
                 "sig_iface", "sig_name", "sig_mask", "sig_gw", "sig_ip")
        rv = do_install_sbce(
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

    elif args.add_node:
        _require(args, "ucsec_password", "type", "name", "ip")
        rv = do_add_node(
            host=args.host,
            ucsec_password=args.ucsec_password,
            type=args.type,
            name=args.name,
            ip=args.ip,
            name2=args.name2,
            ip2=args.ip2,  
        )

    sys.exit(rv)
