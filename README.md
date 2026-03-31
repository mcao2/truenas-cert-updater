# TrueNAS Certificate AutoUpdate

This repo contains scripts that automate TrueNAS certificate update. Currently
it only supports UI certificate and app certificates updates.

This is useful if you do not have a publicly available domain e.g. [tailscale cert](https://tailscale.com/kb/1153/enabling-https/).

## Assumptions

- You have a running TrueNAS instance with UI certificate enabled
- You already have a script or cronjob that routinely refresh the cert and save to disk

## Usage

1. `git clone git@github.com:mcao2/truenas-cert-updater.git`

2. Create a config file `.config.json`, add the following configurations to match your setup:

- `API_BASE_URL`
  - This is your TrueNAS API end point, e.g. if your UI url is `https://192.168.1.179:443`, then the API base url is `https://192.168.1.179:443/api/v2.0`
- `API_KEY`
  - This is the credential needed for authorization, you can find this under upper right corner user avatar (settings) -> API Keys
- `CERT_FILE_PATH`
  - Latest cert file path
- `CERT_KEY_PATH`
  - Latest cert key path
- `CERT_NAME_PREFIX` (Optional)
  - The prefix of the new cert, by default it is `cert`
  - The new cert name format is prefix + current date e.g. `cert_20230601`

3. Add a cronjob that periodically executes `update_cert.py`

### Combined with `tailscale cert`

Create a script with the following content and configure it to run monthly:

```bash
#!/bin/bash

set -x
set -u
set -o pipefail

export NAMESPACE=ix-tailscale
export CONTAINER_NAME=$(k3s kubectl get pods -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')

if [[ -z "$CONTAINER_NAME" ]]; then
   echo "Cannot find tailscale container"
   exit 1
fi

# Get the modification time of the file before performing an action
# CHANGE `cert_file` to meet your need
cert_file="/<path to cert>.crt"
previous_mtime=$(stat -c "%Y" "$cert_file")

echo "Fetching certs..."
# CHANGE `cert-file` AND `key-file` AND your domain name to meet your need
k3s kubectl -n $NAMESPACE exec  $CONTAINER_NAME -- sh -c 'tailscale cert --cert-file /<path to cert>.crt --key-file /<path to key>.key <domain>'

# Get the modification time of the file after performing the action
current_mtime=$(stat -c "%Y" "$cert_file")

# Compare the modification times
if [[ $previous_mtime -lt $current_mtime ]]; then
  echo "Cert file has changed, refreshing UI and app certs"
  python3 /path/to/update_cert.py
else
  echo "Cert file has not changed."
fi

echo "Done!"
```

The script does two things:
1. Refresh the cert via `tailscale cert` command
2. Execute `update_cert.py` to refresh the cert used in TrueNAS

Note that you need to change the file paths to match your setup.

## TrueNAS Scale 24.10 and later

Note that if you're running TrueNAS Scale 24.10 or later, then `k3s` has been replaced with `docker`.  Change the following lines:

```bash
export CONTAINER_NAME=$(docker ps -qf name=$NAMESPACE)

echo "Fetching certs..."
# CHANGE `cert-file` AND `key-file` AND your domain name to meet your need
docker exec $CONTAINER_NAME sh -c 'tailscale cert --cert-file /<path to cert>.crt --key-file /<path to key>.key <domain>'
```

## Renew and Apply a Tailscale Certificate to TrueNAS

`renew_update_cert.py` automates the process of generating a new Tailscale certificate and applying it to the TrueNAS UI.

### What it does

The script will:

1. Read configuration values from a YAML file.
2. Find the running Tailscale container on the host.
3. Run `tailscale cert` inside that container to generate a fresh certificate and private key.
4. Import the new certificate into TrueNAS.
5. Set the new certificate as the TrueNAS UI certificate.
6. Restart the TrueNAS UI to apply the change.
7. Delete the previously active UI certificate after the restart completes.

### Requirements

- TrueNAS SCALE host with Docker available
- A running Tailscale container connected to your tailnet
- 
- Python 3.12+
- Python packages (installed by default on TrueNAS SCALE 24.10+):
  - `docker`
  - `requests`
  - `PyYAML`


### Configuration

Create a YAML config file, for example `.config.yaml`, with the following values:

```yaml 
api_key: "<API_KEY>" 
hostname: "hostname.tailnet-name.ts.net" 
# optional parameters
api_base_url: "https://127.0.0.1/api/v2.0" 
tailscale_container_name_pattern: "tailscale" 
certificate_name_prefix: "tailscale-ui" 
verify_ssl: false
```

#### Configuration fields

- `api_key`
  - TrueNAS API key used for authentication.
- `hostname`
  - The Tailscale hostname to pass to `tailscale cert`.
- `api_base_url` (optional)
  - TrueNAS API base URL.
  - Default: `https://127.0.0.1/api/v2.0`
- `tailscale_container_name_pattern` (optional)
  - Pattern used to locate the Tailscale container.
  - Default: `tailscale`
- `certificate_name_prefix` (optional)
  - Prefix used when naming the imported certificate.
  - Default: `tailscale-ui`
- `verify_ssl` (optional)
  - Whether to verify TLS when calling the TrueNAS API.
  - Default: `false`

### Usage

Run the script directly:

```bash
python3 renew_update_cert.py
```

By default, the script looks for `.config.yaml` in the current directory.

To use a different config file, set:

```bash
export TRUENAS_CERT_CONFIG=/path/to/config.yaml 
python3 renew_update_cert.py
```

### Behavior details

- The script searches for a container whose image or name matches the Tailscale pattern.
- It generates the certificate using:
  - `tailscale cert --cert-file ... --key-file ... <hostname>`
- If a matching certificate already exists in TrueNAS, it reuses that certificate entry.
- The old UI certificate is deleted only after:
  1. the new certificate has been set, and
  2. the TrueNAS UI restart has been triggered.

### Notes

- The script assumes TrueNAS is reachable on localhost unless you override `api_base_url`.
- SSL verification is disabled by default for convenience in local TrueNAS setups.
- Make sure the Tailscale container can write certificate files to the temporary directory used by the script.

## References

- https://github.com/acmesh-official/acme.sh
