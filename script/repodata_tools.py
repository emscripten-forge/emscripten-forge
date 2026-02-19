import bz2
import io
import json
import os
import subprocess
import requests
import hashlib

DRY_RUN = os.environ.get("DRY_RUN", False)
DRY_RUN = True

RUN_MAX_FILES = 300
DRY_RUN_MAX_FILES = 5
uploaded_files = 0

CHANNEL = "emscripten-forge-3x"

PLATFORMS = ["noarch", "emscripten-wasm32"]

current_emscripten_forge_repodata = {}

# Read current repodata for emscripten-forge
for platform in PLATFORMS:
    try:
        resp = requests.get(f"https://repo.prefix.dev/{CHANNEL}/{platform}/repodata.json.bz2", timeout=10)
        resp.raise_for_status()

        with bz2.BZ2File(io.BytesIO(resp.content)) as f:
            current_emscripten_forge_repodata[platform] = json.load(f)
    except Exception:
        pass


def upload_packages(packages, packages_entry, orig_channel, platform):
    global uploaded_files

    current_repodata = current_emscripten_forge_repodata.get(platform, {})
    current_packages = current_repodata.get(packages_entry, {})

    for package, pkg_info in packages.items():
        if package not in current_packages:
            if DRY_RUN and uploaded_files >= DRY_RUN_MAX_FILES:
                continue
            if not DRY_RUN and uploaded_files >= RUN_MAX_FILES:
                continue

            url = f"{orig_channel}/{platform}/{package}"

            # Download
            local_filename = os.path.join("/tmp", package)
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            # Check sha256
            expected_sha256 = pkg_info.get("sha256")
            if expected_sha256:
                sha256_hash = hashlib.sha256()
                with open(local_filename, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                calculated_sha256 = sha256_hash.hexdigest()

                if calculated_sha256 != expected_sha256:
                    print(f"SHA256 mismatch for {package}: expected {expected_sha256}, got {calculated_sha256}", flush=True)
                    continue  # Skip upload

            # Upload
            upload_cmd = [
                "rattler-build",
                "upload",
                "prefix",
                "--channel",
                CHANNEL,
                "--skip-existing",
                local_filename
            ]
            print("Running:", " ".join(upload_cmd), flush=True)

            if not DRY_RUN:
                subprocess.run(upload_cmd, check=True)

            uploaded_files = uploaded_files + 1

            # Optional: remove temp file
            os.remove(local_filename)


def update_mirror():
    channels_urls = [
        "https://repo.prefix.dev/emscripten-forge-dev"
    ]

    # Cache containing pkgs already processed, storing this info in another file
    # allows us to have a smaller pkg_info.json
    total_packages = 0

    all_packages = set()

    for url in channels_urls:
        for platform in PLATFORMS:
            resp = requests.get(f"{url}/{platform}/repodata.json.bz2", timeout=10)
            resp.raise_for_status()

            with bz2.BZ2File(io.BytesIO(resp.content)) as f:
                repodata = json.load(f)

            # TODO Process whls too?
            for packages_entry in ["packages", "packages.conda"]:
                repodata_packages = repodata.get(packages_entry, {})
                upload_packages(repodata_packages, packages_entry, url, platform)

                all_packages.update(repodata.get(packages_entry, {}).keys())

    # Delete non-existing packages from the emscripten-forge channel
    for platform in PLATFORMS:
        current_repodata = current_emscripten_forge_repodata.get(platform, {})

        for packages_entry in ["packages", "packages.conda"]:
            current_packages = current_repodata.get(packages_entry, {})

            for package in current_packages:
                if package not in all_packages:
                    print(f"WOULD DELETE {package}")
