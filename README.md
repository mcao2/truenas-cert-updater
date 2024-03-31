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

## References

- https://github.com/acmesh-official/acme.sh
