#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

WAIT_TIMEOUT = 10


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


def has_eula(driver: WebDriver, host: str) -> bool:
    action_url = f"https://{host}/sbc/eula/"
    selector = f"form[action='{action_url}'][method='post']"
    return element_exists(driver, By.CSS_SELECTOR, selector, timeout=5)


def confirm_eula(driver: WebDriver) -> None:
    checkbox = wait_for_clickable(driver, By.ID, "confirm")
    if not checkbox.is_selected():
        checkbox.click()
    wait_for_clickable(driver, By.XPATH, "//button[text()='Proceed']").click()


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


def install_sbce(
    install_link: WebElement,
    driver: WebDriver,
    appname: str,
    dns: str,
    sig_iface: str,
    sig_name: str,
    sig_mask: str,
    sig_gw: str,
    sip_ip: str,
    sig_pub_ip: Optional[str] = None,
    dns2: Optional[str] = None,
) -> bool:
    original_window = driver.current_window_handle
    install_link.click()

    # Wait for the install popup window and switch to it
    WebDriverWait(driver, WAIT_TIMEOUT).until(lambda d: len(d.window_handles) > 1)
    for handle in driver.window_handles:
        if handle != original_window:
            driver.switch_to.window(handle)
            break

    # Fill in appliance name
    wait_for_clickable(driver, By.ID, "txtApplianceName").send_keys(appname)

    # Fill in primary DNS
    primary_dns = wait_for_clickable(driver, By.ID, "primary-dns")
    primary_dns.clear()
    primary_dns.send_keys(dns)

    # Fill in secondary DNS if provided
    if dns2:
        secondary_dns = wait_for_clickable(driver, By.ID, "secondary-dns")
        secondary_dns.clear()
        secondary_dns.send_keys(dns2)

    # Fill in signaling interface fields
    sig_name_input = wait_for_clickable(driver, By.NAME, "txtName")
    sig_name_input.clear()
    sig_name_input.send_keys(sig_name)

    gw_input = wait_for_clickable(driver, By.NAME, "txtDefaultGateway")
    gw_input.clear()
    gw_input.send_keys(sig_gw)

    mask_input = wait_for_clickable(driver, By.NAME, "txtSubnetMask")
    mask_input.clear()
    mask_input.send_keys(sig_mask)

    # Select interface from dropdown
    select_element = wait_for_clickable(driver, By.NAME, "selInterface")
    Select(select_element).select_by_visible_text(sig_iface)

    # Fill in SIP IP
    sip_ip_input = wait_for_clickable(driver, By.NAME, "txtIP_1")
    sip_ip_input.clear()
    sip_ip_input.send_keys(sip_ip)

    # Fill in public IP if provided
    if sig_pub_ip:
        pub_ip_input = wait_for_clickable(driver, By.NAME, "txtPublicIP_1")
        pub_ip_input.clear()
        pub_ip_input.send_keys(sig_pub_ip)

    # Submit the form
    wait_for_clickable(driver, By.ID, "slideForward").click()

    # Close popup and return to main window
    driver.close()
    driver.switch_to.window(original_window)

    # Poll for Commissioned status every 3s for up to 60s
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


def initial_sbce_web_setup(
    host: str,
    ucsec_password: str,
    appname: str,
    dns: str,
    sig_iface: str,
    sig_name: str,
    sig_mask: str,
    sig_gw: str,
    sip_ip: str,
    sig_pub_ip: Optional[str] = None,
    dns2: Optional[str] = None,
) -> int:
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(f"https://{host}/sbc/")

        # EULA
        if has_eula(driver, host):
            confirm_eula(driver)

        # Login
        if is_login_page(driver):
            enter_credentials(driver, password=ucsec_password)

            if has_login_failed(driver):
                enter_credentials(driver)

                if has_login_failed(driver):
                    raise RuntimeError("Login failed with both provided and default credentials.")

                if is_change_password(driver):
                    change_password(driver, ucsec_password)

                    if not has_password_changed(driver):
                        raise RuntimeError("Password change failed.")

                    if is_login_page(driver):
                        enter_credentials(driver, password=ucsec_password)

        # Install
        install_link = is_sbce_installable(driver, host)
        if install_link is not None:
            install_sbce(
                install_link,
                driver,
                appname,
                dns,
                sig_iface,
                sig_name,
                sig_mask,
                sig_gw,
                sip_ip,
                sig_pub_ip=sig_pub_ip,
                dns2=dns2,
            )

        return 0

    except Exception as e:
        print(f"Setup failed: {e}", file=sys.stderr)
        raise
    finally:
        driver.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated initial setup of Avaya SBCE via web interface."
    )
    parser.add_argument("--host",           required=True,  help="IP or hostname of the SBCE (e.g. 192.168.122.10)")
    parser.add_argument("--ucsec-password", required=True,  help="Target ucsec account password")
    parser.add_argument("--appname",        required=True,  help="Appliance name (e.g. sbce-vm)")
    parser.add_argument("--dns",            required=True,  help="Primary DNS server IP")
    parser.add_argument("--sig-iface",      required=True,  help="Signaling interface (e.g. A1)")
    parser.add_argument("--sig-name",       required=True,  help="Signaling interface name (e.g. A1_internal)")
    parser.add_argument("--sig-mask",       required=True,  help="Signaling interface subnet mask")
    parser.add_argument("--sig-gw",         required=True,  help="Signaling interface default gateway")
    parser.add_argument("--sip-ip",         required=True,  help="SIP signaling IP address")
    parser.add_argument("--sig-pub-ip",     required=False, help="Public IP for signaling interface (optional)")
    parser.add_argument("--dns2",           required=False, help="Secondary DNS server IP (optional)")
    return parser.parse_args()


if __name__ == "__main__":
    sys.argv += [
        "--host",           "192.168.122.10",
        "--ucsec-password", "cmb@Dm1n",
        "--appname",        "sbce-vm",
        "--dns",            "192.168.122.1",
        "--sig-iface",      "A1",
        "--sig-name",       "A1_internal",
        "--sig-mask",       "255.255.255.0",
        "--sig-gw",         "192.168.122.1",
        "--sip-ip",         "192.168.122.11",
        "--sig-pub-ip",     "142.219.32.2",
    ]
    args = parse_args()
    rv = initial_sbce_web_setup(
        host=args.host,
        ucsec_password=args.ucsec_password,
        appname=args.appname,
        dns=args.dns,
        sig_iface=args.sig_iface,
        sig_name=args.sig_name,
        sig_mask=args.sig_mask,
        sig_gw=args.sig_gw,
        sip_ip=args.sip_ip,
        sig_pub_ip=args.sig_pub_ip,
        dns2=args.dns2,
    )
    sys.exit(rv)
