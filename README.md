# sbce-automation
Automation of SBCE deployment

## Playbooks

- ESXi: `playbooks/esxi/deploy_sbce.yml`
- KVM: `playbooks/kvm/deploy_sbce.yml`

## Optional System Dependencies

- `tesseract`: recommended on the Ansible controller for faster VM boot readiness detection.

The playbooks auto-detect `tesseract`. When available, console screenshots are OCR-scanned for the setup prompt. When unavailable, the playbooks fall back to a fixed wait controlled by `sbce_boot_wait`, which is slower but still supported.

Install examples:

- RHEL/Rocky/Alma: `sudo dnf install tesseract`
- Debian/Ubuntu: `sudo apt install tesseract-ocr`

## Call Tree

```text
playbooks/<platform>/deploy_sbce.yml
├── command: scripts/validate.py
│   └── builds/validates topology JSON
└── includes/process_group.yml
    └── loop: topology.groups as current_group
        ├── includes/preflight_group.yml
        │   └── includes/preflight_node.yml
        │       └── loop: primary + secondary_ems + all sbce_unit.nodes
        ├── includes/deploy_node.yml
        │   └── deploys current_group.primary
        ├── includes/webui_bootstrap_ems.yml
        │   └── bootstraps primary EMS Web UI
        ├── includes/webui_install_unit.yml
        │   └── only for coresident EMS+SBCE
        ├── includes/process_sbce_unit.yml
        │   └── loop: current_group.sbce_units -> includes/deploy_node.yml
        ├── includes/webui_add_unit.yml
        │   └── loop: current_group.sbce_units, adds SBCE/HA units
        ├── includes/wait_and_install_unit.yml
        │   └── loop: current_group.sbce_units
        │       ├── includes/wait_and_install_unit_attempt.yml
        │       │   └── loop: sbce_installable_deploy_attempts
        │       │       ├── includes/check_sbce_state.yml
        │       │       ├── includes/redeploy_uninstallable_sbce_nodes.yml
        │       │       └── includes/cleanup_unit.yml
        │       └── includes/webui_install_unit.yml
        ├── includes/deploy_node.yml
        │   └── loop: current_group.secondary_ems
        ├── includes/webui_add_unit.yml
        │   └── loop: current_group.secondary_ems, adds secondary EMS nodes
        ├── rescue: includes/cleanup_group.yml
        │   └── includes/cleanup_node.yml
        │       └── loop: primary + secondary_ems + all sbce_unit.nodes
        └── always: report EMS group result

includes/deploy_node.yml
├── initializes retry state
├── loop: vm_deploy_retries -> includes/deploy_node_retry.yml
│   ├── includes/deploy_node_attempt.yml
│   │   ├── platform-specific VM/image deployment
│   │   ├── includes/wait_for_console_prompt.yml
│   │   │   └── includes/wait_for_console_prompt_attempt.yml
│   │   │       └── loop: OCR console prompt attempts
│   │   ├── includes/console_bootstrap.yml
│   │   ├── includes/post_bootstrap_configuration.yml
│   │   ├── includes/cleanup_node.yml
│   │   │   └── only when deployment attempt failed
│   │   └── records deployment attempt result
│   └── rescue: records hard attempt failure and runs cleanup_node.yml
└── fails only after deployment retries are exhausted
```
