import os
import ssl
import time
import subprocess
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
from dotenv import load_dotenv
load_dotenv()

USER = os.getenv("USER")
PASSWD = vcenter  = os.getenv("PASSWD")


def connect_vsphere(host, user, password, insecure=True):
    ctx = ssl._create_unverified_context() if insecure else None
    si = SmartConnect(host=host, user=user, pwd=password, sslContext=ctx)
    return si


def find_obj(content, vimtype, name):
    view = content.viewManager.CreateContainerView(content.rootFolder, [vimtype], True)
    try:
        for obj in view.view:
            if obj.name == name:
                return obj
    finally:
        view.Destroy()
    raise RuntimeError(f"Not found: {vimtype.__name__} name={name}")


def wait_task(task):
    while task.info.state in (vim.TaskInfo.State.queued, vim.TaskInfo.State.running):
        pass
    if task.info.state != vim.TaskInfo.State.success:
        raise task.info.error
    return task.info.result


def add_nic_standard_pg(si, vm_name, portgroup_name, adapter="vmxnet3", connect_at_boot=True):
    content = si.RetrieveContent()
    vm = find_obj(content, vim.VirtualMachine, vm_name)
    pg = find_obj(content, vim.Network, portgroup_name)  # PortGroup shows up as vim.Network

    # Choose adapter type
    if adapter.lower() == "e1000":
        nic = vim.vm.device.VirtualE1000()
    elif adapter.lower() == "e1000e":
        nic = vim.vm.device.VirtualE1000e()
    else:
        nic = vim.vm.device.VirtualVmxnet3()

    nic.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
    nic.backing.network = pg
    nic.backing.deviceName = portgroup_name

    nic.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    nic.connectable.startConnected = connect_at_boot
    nic.connectable.allowGuestControl = True
    nic.connectable.connected = False  # becomes true when VM powers on

    # You can omit this; vCenter/ESXi will assign one if blank.
    nic.addressType = "generated"

    devspec = vim.vm.device.VirtualDeviceSpec()
    devspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    devspec.device = nic

    spec = vim.vm.ConfigSpec()
    spec.deviceChange = [devspec]

    task = vm.ReconfigVM_Task(spec=spec)
    wait_task(task)
    print(f"Added NIC to VM '{vm_name}' on standard PG '{portgroup_name}'.")

def wait_for_task(task):
    """Block until a vSphere task finishes, then raise on failure."""
    while task.info.state in (
        vim.TaskInfo.State.running,
        vim.TaskInfo.State.queued,
    ):
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.success:
        return task.info.result
    else:
        raise RuntimeError(f"Task failed: {task.info.error.msg}")

def power_on_vm(si, vm_name):
    """Power on a VM and wait for the task to complete."""
    content = si.RetrieveContent()
    vm = find_obj(content, vim.VirtualMachine, vm_name)
    if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
        print(f"VM '{vm.name}' is already powered on.")
        return

    print(f"Powering on VM '{vm.name}'...")
    task = vm.PowerOn()
    wait_for_task(task)
    print(f"VM '{vm.name}' is now powered on.")


def deploy_sbce():
    command = f'''
    ovftool \
    --acceptAllEulas \
    --noSSLVerify \
    --datastore="datastore1" \
    --name="SBCE-VM" \
    --net:"A1"="VLAN48" \
    --net:"A2"="VLAN48" \
    --net:"B1"="VLAN32" \
    --net:"B2"="VLAN32" \
    --net:"M1"="VLAN48" \
    --net:"M2"="Duplication" \
    --prop:ipmode="DUAL_STACK" \
    --prop:apptype="EMS" \
    --prop:nwpass="avaya" \
    --prop:ems_inst_type="none" \
    --prop:ip0="10.10.48.180" \
    --prop:netmask0="255.255.255.0" \
    --prop:gateway="10.10.48.254" \
    --prop:ipv6prefix0="64" \
    --prop:timezone="America/Edmonton" \
    --prop:ntpservers="10.10.48.92" \
    --prop:dns="10.10.48.92" \
    --prop:emsip="0.0.0.0" \
    --prop:rootpass="r00t10_cmb@Dm1n" \
    --prop:ipcspass="sbc10_cmb@Dm1n" \
    --prop:grubpass="r00t10_cmb@Dm1n" \
    --prop:ssh_port_number="222" \
    --prop:vmname="SBCE" \
    /root/Projects/sbce-automation/data/ova/sbce-10.2.0.0-86-24077-1.ova \
    "vi://{USER}:{PASSWD}@192.168.200.161/"'''

    completed_proc= subprocess.run(command, shell=True, check=True)
    if completed_proc.returncode == 0:
        print("SBCE deployment completed successfully.")
    else:
        print("SBCE deployment failed with return code: ", completed_proc.returncode)
        print("With error message: ", completed_proc.stderr)

    si = connect_vsphere("192.168.200.161", "root", "cmb@Dm1n", insecure=True)
    try:
        add_nic_standard_pg(si, vm_name="SBCE-VM", portgroup_name="Duplication", adapter="vmxnet3")
        power_on_vm(si, vm_name="SBCE-VM")
    finally:
        Disconnect(si)
    

if __name__ == "__main__":
    deploy_sbce()