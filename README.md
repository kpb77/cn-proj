# Smart Content Delivery System
## Mini Project for Computer Networks (UE25CS243A)

### Problem Statement
* Implement multiple content servers and clients where the SDN controller dynamically selects or reroutes traffic toward suitable servers based on network conditions

### Requirements
* Implement TCP content requests
* Deploy multiple content servers
* Maintain server availability
* Monitor network conditions
* Select appropriate servers
* Dynamically modify SDN forwarding
* Simulate server/path failures
* Measure response time and throughput

### Prerequisites, Installation and Setup
* __Operating System:__ `Ubuntu 24.04 LTS` or higher
* __Test Environment:__
  * Host OS: `Windows 11`
  * Hypervisor: `Oracle VirtualBox Version 7.2.16 (Windows 11)`
  * Test Virtual Machine: `Linux Mint 22.3` (built on `Ubuntu 24.04 LTS`)
* __Installing Tools:__ Open a Terminal window and do the following steps
  * Update Package List:
    ```
    sudo apt update
    ```
  * Install Mininet:
    ```
    sudo apt install -y mininet openvswitch-switch git curl
    sudo systemctl enable --now openvswitch-switch
    ```
  * Install uv:
    ```
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.local/bin/env
    ```
  * Install Python 3.9 (Required for Ryu):
    ```
    uv python install 3.9
    ```
  * Create a Python 3.9 Virtual Environment using uv to Install and Activate it:
    ```
    uv venv --python 3.9 --seed ~/ryu
    source ~/ryu/bin/activate
    ```
  * Install Ryu in the Virtual Environment:
    ```
    pip install setuptools==67.6.1 wheel==0.43.0 pbr
    pip install --no-build-isolation ryu eventlet==0.30.2
    ```
* __Test if Everything is Working:__
  * For this, you would need 2 Terminal windows
  * In one Terminal window, activate the Ryu Virtual Environment and run the built-in script
    ```
    source ~/ryu/bin/activate
    ryu-manager ryu.app.simple_switch_13
    ```
    The Ryu controller is now listening to `Port: 6653`
  * In another Terminal window, run the simplest Mininet topology with 2 Hosts and 1 Switch between them
    ```
    sudo mn --controller remote
    ```
    Mininet defaults to `127.0.0.1` and `Port: 6653`
  * The desired output should look like this
    <img width="1918" height="1079" alt="image" src="https://github.com/user-attachments/assets/bb25ed3a-87d9-4620-ae09-472ab5703a00" />
