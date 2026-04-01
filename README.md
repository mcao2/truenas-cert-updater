# TrueNAS Certificate AutoUpdate

This repo contains scripts that automate TrueNAS certificate update. Currently
it only supports UI certificate and app certificates updates.

`renew_update_cert.py` automates the process of generating a new Tailscale certificate and applying it to the TrueNAS UI.

## What it does

The script will:

1. Read configuration values from a YAML file.
2. Find the running Tailscale container on the host.
3. Run `tailscale cert` inside that container to generate a fresh certificate and private key.
4. Import the new certificate into TrueNAS.
5. Set the new certificate as the TrueNAS UI certificate.
6. Restart the TrueNAS UI to apply the change.
7. Delete the previously active UI certificate after the restart completes.

## Requirements

- TrueNas SCALE 24.10+
- Python 3.12+ (included in TrueNas SCALE)
- Python packages:
  - `requests` (included in TrueNas SCALE)
  - `PyYAML` (included in TrueNas SCALE)
  - `docker` (included in TrueNas SCALE)
- A running Tailscale app connected to your tailnet
  - expected to be a running docker container

## Configuration

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

### Configuration fields

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

## Usage

1. `git clone git@github.com:mcao2/truenas-cert-updater.git`
2. Create a config file `.config.yaml` as described above.
3. Create a cronjob that runs the script periodically.
    - Select the `root` user for the cronjob.
    - Set the cronjob to run more often than every 90 days (the default expiry for the certificate). It can safely be run as often as you want. 
    - Set the command to:
    ```bash
    python3 /path/to/renew_update_cert.py
    ```
4. (Optional) Test the script by running it directly.

## Behavior details

- The script searches for a container whose image or name matches the Tailscale pattern.
- It generates the certificate using:
  - `tailscale cert --cert-file ... --key-file ... <hostname>`
- If a matching certificate already exists in TrueNAS, it reuses that certificate entry.
- The old UI certificate is deleted only after:
  1. the new certificate has been set, and
  2. the TrueNAS UI restart has been triggered.

## Notes

- The script assumes TrueNAS is reachable on localhost unless you override `api_base_url`.
- SSL verification is disabled by default for convenience in local TrueNAS setups.
- Make sure the Tailscale container can write certificate files to the temporary directory used by the script.
- The authors have attempted to make this script backwards compatible with previous versions of TrueNAS, but are not able to 
    test or guarantee that it will work on all versions. 
- For previous versions, older versions of this repository are known to work. 

## References

- https://github.com/acmesh-official/acme.sh
