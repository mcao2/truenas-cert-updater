#!/usr/bin/env python3

from __future__ import annotations
import re
import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker
import requests
import urllib3
import yaml
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    api_base_url: str
    api_key: str
    hostname: str
    tailscale_container_name_pattern: str
    certificate_name_prefix: str = "tailscale-ui"
    verify_ssl: bool = False


def load_config(config_path: str | Path) -> Config:
    with open(config_path, "rt", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    required = [
        "api_key",
        "hostname",
    ]
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    return Config(
        api_base_url=raw.get("api_base_url", 'https://127.0.0.1/api/v2.0').rstrip("/"),
        api_key=raw["api_key"],
        hostname=raw["hostname"],
        tailscale_container_name_pattern=raw.get("tailscale_container_name_pattern", "tailscale"),
        certificate_name_prefix=raw.get("certificate_name_prefix", "tailscale-ui"),
        verify_ssl=bool(raw.get("verify_ssl", False)),
    )


def build_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def req_get(url: str, headers: dict[str, str], verify: bool) -> Any:
    response = requests.get(url, headers=headers, verify=verify, timeout=60)
    response.raise_for_status()
    return response.json()


def req_post(url: str, headers: dict[str, str], payload: dict[str, Any], verify: bool) -> Any:
    response = requests.post(url, headers=headers, json=payload, verify=verify, timeout=60)
    response.raise_for_status()
    return response.json() if response.content else None


def req_put(url: str, headers: dict[str, str], payload: dict[str, Any], verify: bool) -> Any:
    response = requests.put(url, headers=headers, json=payload, verify=verify, timeout=60)
    response.raise_for_status()
    return response.json() if response.content else None


def req_delete(url: str, headers: dict[str, str], verify: bool) -> Any:
    response = requests.delete(url, headers=headers, verify=verify, timeout=60)
    response.raise_for_status()
    return response.json() if response.content else None


def parse_truenas_version(version_string: str) -> tuple[int, int, int]:
    """
    Extract major/minor/patch from a TrueNAS version string.

    Handles examples like:
      - 'TrueNAS-SCALE-24.10.0'
      - '24.10.0'
      - 'TrueNAS-SCALE-24.10.1.2'
    """
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", version_string)
    if not match:
        return 0, 0, 0

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or 0)
    return major, minor, patch


def get_truenas_version(api_base_url: str, headers: dict[str, str], verify: bool) -> tuple[int, int, int]:
    """
    Query TrueNAS and normalize its version into a comparable tuple.
    Falls back gracefully if the response shape changes.
    """
    version_value = req_get(f"{api_base_url}/system/version", headers=headers, verify=verify)

    if isinstance(version_value, str):
        return parse_truenas_version(version_value)

    if isinstance(version_value, dict):
        for key in ("version", "fullversion", "build"):
            value = version_value.get(key)
            if isinstance(value, str):
                parsed = parse_truenas_version(value)
                if parsed != (0, 0, 0):
                    return parsed

    return 0, 0, 0


def get_app_path(api_base_url: str, headers: dict[str, str], verify: bool) -> str:
    version = get_truenas_version(api_base_url, headers, verify)
    return "app" if version >= (24, 10, 0) else "chart/release"


def get_ui_certificate_id(api_base_url: str, headers: dict[str, str], verify: bool) -> int | None:
    """
    Returns the currently active UI certificate id, if any.
    """
    ui_choices = get_ui_certificate_choices(api_base_url, headers, verify)
    for cert_id, cert_name in ui_choices.items():
        if cert_name is not None:
            return int(cert_id)
    return None


def find_tailscale_container(client: docker.DockerClient, name_pattern: str) -> docker.models.containers.Container:
    containers = client.containers.list(all=True)
    for container in containers:
        image = container.image.tags[0] if container.image.tags else ""
        name = container.name or ""

        if "tailscale" in image.lower() and re.search(name_pattern, name, re.IGNORECASE):
            return container

        if "ghcr.io/tailscale/tailscale" in image.lower():
            return container

    raise RuntimeError(
        "Could not find a Tailscale container. "
        "Check tailscale_container_name_pattern in config."
    )


def generate_tailscale_cert(
    container: docker.models.containers.Container,
    hostname: str,
) -> tuple[str, str]:
    """
    Create the certificate inside the container, then read the generated files
    back into Python strings. Always clean up the temp directory afterward.
    """
    tmp_dir = f"/tmp/tailscale-cert-{os.getpid()}"
    cert_path = f"{tmp_dir}/{hostname}.crt"
    key_path = f"{tmp_dir}/{hostname}.key"

    try:
        create_command = [
            "sh",
            "-lc",
            (
                "set -e; "
                f"mkdir -p '{tmp_dir}'; "
                f"cd '{tmp_dir}'; "
                f"tailscale cert --cert-file '{cert_path}' "
                f"--key-file '{key_path}' '{hostname}'"
            ),
        ]
        exit_code, output = container.exec_run(create_command, stdout=True, stderr=True)
        output_text = output.decode("utf-8", errors="replace") if isinstance(output, (bytes, bytearray)) else str(output)

        if exit_code != 0:
            raise RuntimeError(f"tailscale cert failed:\n{output_text}")

        read_cert_command = ["sh", "-lc", f"cat '{cert_path}'"]
        read_key_command = ["sh", "-lc", f"cat '{key_path}'"]

        cert_exit_code, cert_output = container.exec_run(read_cert_command, stdout=True, stderr=True)
        key_exit_code, key_output = container.exec_run(read_key_command, stdout=True, stderr=True)

        cert_text = cert_output.decode("utf-8", errors="replace") if isinstance(cert_output, (bytes, bytearray)) else str(cert_output)
        key_text = key_output.decode("utf-8", errors="replace") if isinstance(key_output, (bytes, bytearray)) else str(key_output)

        if cert_exit_code != 0:
            raise RuntimeError(f"Failed to read certificate file:\n{cert_text}")
        if key_exit_code != 0:
            raise RuntimeError(f"Failed to read private key file:\n{key_text}")

        return cert_text, key_text
    finally:
        cleanup_command = ["sh", "-lc", f"rm -rf '{tmp_dir}'"]
        container.exec_run(cleanup_command, stdout=True, stderr=True)


def get_certificate_by_name(
    api_base_url: str,
    headers: dict[str, str],
    verify: bool,
    app_path: str,
    cert_name: str,
) -> dict[str, Any] | None:
    certificates = req_get(f"{api_base_url}/{app_path}/certificate_choices", headers=headers, verify=verify)
    return next((cert for cert in certificates if cert.get("name") == cert_name), None)


def wait_for_certificate_by_name(
    api_base_url: str,
    headers: dict[str, str],
    verify: bool,
    app_path: str,
    cert_name: str,
    attempts: int = 10,
    delay_seconds: float = 1.0,
) -> dict[str, Any]:
    import time

    for _ in range(attempts):
        cert = get_certificate_by_name(api_base_url, headers, verify, app_path, cert_name)
        if cert is not None:
            return cert
        time.sleep(delay_seconds)

    raise RuntimeError(f"Certificate {cert_name!r} was not found after import")


def create_certificate(
    api_base_url: str,
    headers: dict[str, str],
    verify: bool,
    cert_name: str,
    certificate: str,
    private_key: str,
) -> dict[str, Any]:
    payload = {
        "name": cert_name,
        "privatekey": private_key,
        "certificate": certificate,
        "create_type": "CERTIFICATE_CREATE_IMPORTED",
    }
    return req_post(f"{api_base_url}/certificate", headers=headers, payload=payload, verify=verify)


def get_ui_certificate_choices(api_base_url: str, headers: dict[str, str], verify: bool) -> dict[str, Any]:
    return req_get(f"{api_base_url}/system/general/ui_certificate_choices", headers=headers, verify=verify)


def set_ui_certificate(
    api_base_url: str,
    headers: dict[str, str],
    verify: bool,
    cert_id: int,
) -> Any:
    return req_put(
        f"{api_base_url}/system/general",
        headers=headers,
        payload={"ui_certificate": cert_id},
        verify=verify,
    )


def delete_certificate(api_base_url: str, headers: dict[str, str], verify: bool, cert_id: int) -> Any:
    return req_delete(f"{api_base_url}/certificate/id/{cert_id}", headers=headers, verify=verify)


def restart_ui(api_base_url: str, headers: dict[str, str], verify: bool) -> Any:
    return req_post(f"{api_base_url}/system/general/ui_restart", headers=headers, payload={}, verify=verify)


def main() -> None:
    config_path = os.environ.get("TRUENAS_CERT_CONFIG", ".config.yaml")
    config = load_config(config_path)
    headers = build_headers(config.api_key)

    logger.info("Checking TrueNAS connectivity...")
    req_get(f"{config.api_base_url}/system/state", headers=headers, verify=config.verify_ssl)

    app_path = get_app_path(config.api_base_url, headers, config.verify_ssl)
    logger.info(f"Using TrueNAS API path: {app_path}")

    cert_name = f"{config.certificate_name_prefix}-{datetime.datetime.now().strftime('%Y%m%d')}"

    docker_client = docker.from_env()
    container = find_tailscale_container(docker_client, config.tailscale_container_name_pattern)
    logger.info(f"Using Tailscale container: {container.name}")

    logger.info("Generating certificate via tailscale cert...")
    certificate, private_key = generate_tailscale_cert(container, config.hostname)

    previous_ui_cert_id = get_ui_certificate_id(config.api_base_url, headers, config.verify_ssl)

    existing_cert = get_certificate_by_name(
        config.api_base_url,
        headers,
        config.verify_ssl,
        app_path,
        cert_name,
    )

    if existing_cert:
        logger.info(f"Certificate already exists: {cert_name} (id={existing_cert['id']})")
        cert_record = existing_cert
    else:
        logger.info(f"Creating certificate in TrueNAS: {cert_name}")
        # despite what the documentation says, the API returns a job ID for certificate imports
        # and not the object representing the certificate
        job_id = create_certificate(
            config.api_base_url,
            headers,
            config.verify_ssl,
            cert_name,
            certificate,
            private_key,
        )
        logger.info(f"Certificate import job started: {job_id}")
        cert_record = wait_for_certificate_by_name(
            config.api_base_url,
            headers,
            config.verify_ssl,
            app_path,
            cert_name,
        )

    cert_id = cert_record["id"]
    logger.info(f"Setting UI certificate to id={cert_id}")
    set_ui_certificate(config.api_base_url, headers, config.verify_ssl, cert_id)

    logger.info("Restarting TrueNAS UI...")
    restart_ui(config.api_base_url, headers, config.verify_ssl)

    if previous_ui_cert_id and previous_ui_cert_id != cert_id:
        try:
            logger.info(f"Deleting previous UI certificate id={previous_ui_cert_id}")
            delete_certificate(config.api_base_url, headers, config.verify_ssl, previous_ui_cert_id)
        except Exception as exc:
            logger.info(f"Skipping delete for previous UI cert id={previous_ui_cert_id}: {exc}")
    else:
        logger.info("No previous UI certificate to delete, or it is the same as the new one.")

    logger.info("Done.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
