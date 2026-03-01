import subprocess

import ssl
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
from utils.deploy_sbce_esxi_ova import deploy_sbce
from utils.init_setup_esxi import init_setup
import time

def main():
    deploy_sbce()
    time.sleep(160)  # Wait for the VM to be fully deployed and powered on
    init_setup()

if __name__ == "__main__":
    main()
