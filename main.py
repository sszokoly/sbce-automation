#!/usr/bin/env python3

from utils.deploy_sbce_esxi_ova import deploy_sbce
from utils.init_setup_esxi import init_setup
import time

def main():
    deploy_sbce()
    print("Waiting for the VM to be fully deployed and powered on...")
    time.sleep(160)
    init_setup()

if __name__ == "__main__":
    main()
