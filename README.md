# TrueNAS Certificate AutoUpdate

This repo contains scripts that automate TrueNAS certificate update. Currently
it only supports UI certificate and app certificates updates.

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

## References

- https://github.com/acmesh-official/acme.sh
