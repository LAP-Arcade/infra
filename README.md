# Le LAP Infra as Code

This is an Ansible project to manage Le LAP's machines.

Currently supported features:

- Setting up the Windows video capture machines inside the arcade cabinets
    - Fail if WinGet is not installed
    - Ensures OBS is installed
    - Ensures symlinks to the persistent drive are made for some apps

## Requirements

- Python, only tested with Python 3.10 on WSL

## Running

1. Ensure WinRM is set up and enabled on the target machines, you can use the
   provided `enable_winrm.ps1` script.
2. Create `group_vars/all/secrets.yml` file with your `ansible_user`,
   `ansible_password`, and any over override needed. See `default.yml`.
3. Install the Python dependencies, `pip install -r requirements.txt`, usage of
   a venv is recommended.
4. To run locally, use `ansible-playbook playbook.yml -i hosts_local`, to run
   against the actual machines, omit the `-i hosts_local` part.

## TODO

- [ ] Write the startup.bat script
- [ ] Write OBS configuration from a template
- [ ] Write OBS scenes and profiles from a template
- [ ] Install WinGet if not present
- [ ] Install UniGetUI
