#!/usr/bin/env python3

import requests
import json
from datetime import date

# Read the credentials from `.config.json` file
with open('.config.json') as config_file:
    config = json.load(config_file)

    # API endpoint URLs
    API_BASE_URL = config.get("API_BASE_URL")

    # API key
    TRUENAS_API_KEY = config.get("API_KEY")

    # Certs
    CERT_FILE_PATH = config.get("CERT_FILE_PATH")
    CERT_KEY_PATH = config.get("CERT_KEY_PATH")
    CERT_NAME_PREFIX = config.get("CERT_NAME_PREFIX", "cert")

headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
date_suffix = date.today().strftime("%Y%m%d")
certificate_name = f"{CERT_NAME_PREFIX}_{date_suffix}"


def req_get(url, headers=headers, verify=False):
    response = requests.get(url, headers=headers, verify=verify)
    response.raise_for_status()
    return response.json()


def get_cert_by_name(cert_check_url, cert_name):
    certificates = req_get(cert_check_url)
    # If a certificate with a matching name is found, existing_certificate will be
    # set to that certificate object. Otherwise, it will be set to None.
    return next((cert for cert in certificates if cert["name"] == cert_name), None)


# Check connection
print("Testing Connection TrueNAS")
req_get(f"{API_BASE_URL}/system/state")

# Import if not exists
if not get_cert_by_name(f"{API_BASE_URL}/chart/release/certificate_choices", certificate_name):
    print(f"Uploading cert with name {certificate_name} to TrueNAS")
    # Create a new certificate
    with open(CERT_KEY_PATH, "r") as private_key_file, open(CERT_FILE_PATH, "r") as certificate_file:
        private_key = private_key_file.read()
        certificate = certificate_file.read()

    certificate_data = {
        "name": certificate_name,
        "privatekey": private_key,
        "certificate": certificate,
        "create_type": "CERTIFICATE_CREATE_IMPORTED"
    }

    response = requests.post(f"{API_BASE_URL}/certificate", headers=headers, json=certificate_data, verify=False)
    response.raise_for_status()
    print(f"New certificate '{certificate_name}' created")

# Retrieve the cert
new_certificate = get_cert_by_name(f"{API_BASE_URL}/chart/release/certificate_choices", certificate_name)
new_cert_id = new_certificate['id']

# Update UI cert
print("Fetching list of installed UI certificates")
ui_certificates = req_get(f"{API_BASE_URL}/system/general/ui_certificate_choices")
assert str(new_certificate["id"]) in ui_certificates
print(f"Activating new cert: {new_cert_id}")
response = requests.put(f"{API_BASE_URL}/system/general",
                        headers=headers,
                        json={"ui_certificate": str(new_cert_id)},
                        verify=False)
response.raise_for_status()

# Get all services
# Filter services with certs
services = [
    service for service in req_get(f"{API_BASE_URL}/chart/release") if service.get("config", {}).get("ixCertificates")
]

# Print the filtered services
for service in services:
    service_id = service["id"]
    service_name = service["name"]
    ix_certificates = service["config"]["ixCertificates"]
    print(f"Service ID: {service_id}, Name: {service_name}, ixCertificates name: {ix_certificates}")

# Update each service to use the new certificate ID
for service in services:
    service_id = service["id"]
    ingress = service.get("config", {}).get("ingress", {})
    main_tls = ingress.get("main", {}).get("tls", [])
    if not main_tls:
        print(f"Skip {service_id} since no main ingress defined")
        continue

    print(f"Updating certificate to {new_cert_id} for chart release: {service_id}")
    # Find and update the matching certificate ID
    updated_main_tls = [{**tls, "scaleCert": new_certificate["id"]} for tls in main_tls]
    # Update the service configuration
    ingress["main"]["tls"] = updated_main_tls

    update_url = f"{API_BASE_URL}/chart/release/id/{service_id}"
    response = requests.put(update_url, headers=headers, json={"values": {"ingress": ingress}}, verify=False)
    if response.ok:
        print(f"Service with ID {service_id} updated successfully.")
    else:
        print(f"Failed to update service with ID {service_id}")

print("Certificate update completed.")

print("Deleting old certificate")
for cert_id in ui_certificates.keys():
    if cert_id == new_cert_id:
        continue
    response = requests.delete(f"{API_BASE_URL}/certificate/id/{cert_id}", headers=headers, verify=False)
    try:
        response.raise_for_status()
    except Exception:
        print(f"Failed to delete cert {cert_id}, skip")

print("Reloading TrueNAS web UI")
req_get(f"{API_BASE_URL}/system/general/ui_restart")
