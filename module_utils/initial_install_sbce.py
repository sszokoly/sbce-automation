
from re import DEBUG
import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

chrome_options = Options()
chrome_options.add_argument('--ignore-certificate-errors')
chrome_options.add_argument('--ignore-ssl-errors')


def login(host, ucsec_password, appname, debug=False):
    # Initialize WebDriver (e.g., Chrome)

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(f"https://{host}/sbc/login/")


    # Wait for the username field to be enabled and interactable
    username_field = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "username"))
    )
    username_field.send_keys("ucsec")
    login_button = driver.find_element(By.ID, "login-submit")
    login_button.click()

    # Wait for the password field to be enabled and interactable
    password_field = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "password"))
    )
    password_field.send_keys(ucsec_password)

    # Click the login button
    login_button = driver.find_element(By.ID, "login-submit")
    login_button.click()

    element = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "menu-device-management"))
    )
    element.click()

    # Store the original window handle before clicking
    original_window = driver.current_window_handle

    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for i, iframe in enumerate(iframes):
        driver.switch_to.default_content()
        driver.switch_to.frame(i)
        try:
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, f"//a[contains(@onclick, 'installSystem(2') and contains(@onclick, '{appname}')]"))
            )
            element.click()
            break
        except:
            continue

    # Wait for the new window to appear and switch to it
    WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
    for window_handle in driver.window_handles:
        if window_handle != original_window:
            driver.switch_to.window(window_handle)
            break

    appliance_name_input = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "txtApplianceName"))
    )
    #appliance_name_input.clear()
    #driver.execute_script("arguments[0].value = arguments[1];", appliance_name_input, appname)
    appliance_name_input.send_keys(appname)


    appliance_name_input = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "primary-dns"))
    )
    appliance_name_input.clear()
    appliance_name_input.send_keys("192.168.122.1")

    appliance_name_input = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "secondary-dns"))
    )
    appliance_name_input.clear()
    appliance_name_input.send_keys("1.1.1.1")

    appliance_name_input = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.NAME, "txtName"))
    )
    appliance_name_input.clear()
    appliance_name_input.send_keys("Internal")

    appliance_name_input = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.NAME, "txtDefaultGateway"))
    )
    appliance_name_input.clear()
    appliance_name_input.send_keys("192.168.122.1")


    appliance_name_input = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.NAME, "txtSubnetMask"))
    )
    appliance_name_input.clear()
    appliance_name_input.send_keys("255.255.255.0")


    select_element = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.NAME, "selInterface"))
    )

    dropdown = Select(select_element)
    dropdown.select_by_visible_text("A1")

    ip_input = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.NAME, "txtIP_1"))
    )
    ip_input.clear()
    ip_input.send_keys("192.168.122.11")


    finish_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "slideForward"))
    )
    finish_button.click()

    # Close the new window
    driver.close()

    # Switch back to the original window
    driver.switch_to.window(original_window)

    time.sleep(20)

    element = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, "menu-device-management"))
    )
    element.click()

    driver.switch_to.default_content()
    driver.switch_to.frame("page-frame")

    try:
        WebDriverWait(driver, 5).until(
            EC.text_to_be_present_in_element(
                (By.XPATH, f"//tr[@data-name='{appname}']//span[@class='status-commissioned']"),
                "Commissioned"
            )
        )
        result = True
    except TimeoutException:
        result = False

    driver.switch_to.default_content()
    driver.quit()
    return 0 if result else 1


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.122.10"
    ucsec_password = sys.argv[2] if len(sys.argv) > 2 else "cmb@Dm1n"
    appname = sys.argv[3] if len(sys.argv) > 3 else "sbce-vm"
    if len(appname) > 20:
        print("Warning: App name must be 20 characters or fewer.")
    sys.exit(login(host, ucsec_password, appname, debug=DEBUG))
