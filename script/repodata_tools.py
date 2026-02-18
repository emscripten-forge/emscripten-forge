import bz2
import io
import json
import os
import subprocess
import requests
import hashlib

DRY_RUN = os.environ.get("DRY_RUN", False)

RUN_MAX_FILES = 300
DRY_RUN_MAX_FILES = 5
uploaded_files = 0

CHANNEL = "emscripten-forge"

# Known noarch packages that do not need to depend on emscripten-abi
WHITELIST = [
    "astropy-7.2.0-py313h48f9ed5_1.tar.bz2",
    "astropy-7.2.0-py313h4c1943c_2.tar.bz2",
    "clang-resource-headers-20.1.8-hc286ada_1.tar.bz2",
    "clang-resource-headers-21.1.8-hc286ada_0.tar.bz2",
    "fps-kernel-web-worker-0.1.10-py313h1e85631_0.tar.bz2",
    "fps-kernel-web-worker-0.1.10-py313h1e85631_1.tar.bz2",
    "fps-kernel-web-worker-0.1.7-py313h1e85631_0.tar.bz2",
    "fps-kernel-web-worker-0.1.8-py313h1e85631_0.tar.bz2",
    "fps-kernel-web-worker-0.1.9-py313h1e85631_0.tar.bz2",
    "matplotlib-3.10.7-py313hf9b0b07_0.tar.bz2",
    "matplotlib-3.10.8-py313h4b20186_0.tar.bz2",
    "matplotlib-3.10.8-py313hba19ed7_2.tar.bz2",
    "matplotlib-3.10.8-py313hc79e5cd_1.tar.bz2",
    "matplotlib-3.10.8-py313hdac90d7_3.tar.bz2",
]

# Known non-noarch packages that miss the emscripten-abi dependency.
# We can't have those on the merged channel
BLACKLIST = [
    # 3.x packages
    "pyjs-3.1.0-hc286ada_3.tar.bz2",
    "pyjs-3.2.0-hc286ada_0.tar.bz2",
    "python_abi-3.13.1-0_cp313.tar.bz2",
    "python_abi-3.13.1-1_cp313.tar.bz2",
    "protobuf-4.22.3-h7223423_0.conda",

    # 4.x packages
    "google-crc32c-1.8.0-py313h1804a44_1.tar.bz2",
    "jiter-0.13.0-py313h1804a44_1.tar.bz2",
    "joblib-1.5.2-py313h1804a44_2.tar.bz2",
    "lakers-python-0.6.0-py313hf898885_0.tar.bz2",
    "lakers-python-0.6.0-py313hf898885_1.tar.bz2",
    "nlopt-2.10.0-np23py313hb3c72f9_0.tar.bz2",
    "nlopt-2.10.1-np23py313hb3c72f9_0.tar.bz2",
    "nlopt-2.10.1-np23py313hb3c72f9_1.tar.bz2",
    "orjson-3.11.4-py313h3ab680a_0.tar.bz2",
    "orjson-3.11.5-py313h3ab680a_0.tar.bz2",
    "orjson-3.11.6-py313h3ab680a_0.tar.bz2",
    "orjson-3.11.7-py313h3ab680a_0.tar.bz2",
    "orjson-3.11.7-py313h3ab680a_1.tar.bz2",
    "patsy-1.0.1-py313h1804a44_2.tar.bz2",
    "pycrdt-0.12.33-py313h3ab680a_0.tar.bz2",
    "pycrdt-0.12.34-py313h3ab680a_0.tar.bz2",
    "pycrdt-0.12.45-py313h3ab680a_0.tar.bz2",
    "pycrdt-0.12.46-py313h3ab680a_0.tar.bz2",
    "pycrdt-0.12.46-py313h3ab680a_1.tar.bz2",
    "pydantic-core-2.41.5-py313h1e85631_0.tar.bz2",
    "pydantic-core-2.41.5-py313h1e85631_1.tar.bz2",
    "pyiceberg-0.10.0-py313h1804a44_1.tar.bz2",
    "pyjs-4.0.1-hc286ada_3.tar.bz2",
    "pyjs-4.0.2-hc286ada_3.tar.bz2",
    "pysocks-1.7.1-py313h1804a44_0.tar.bz2",
    "pysocks-1.7.1-py313h1804a44_1.tar.bz2",
    "pyyaml-6.0-py313h1804a44_0.tar.bz2",
    "pyyaml-6.0-py313h1804a44_1.tar.bz2",
    "sympy-1.14.0-py313h1804a44_0.tar.bz2",
    "sympy-1.14.0-py313h1804a44_1.tar.bz2",
    "tree-sitter-0.23.2-py313h1804a44_0.tar.bz2",
    "tree-sitter-0.24.0-py313h1804a44_0.tar.bz2",
    "tree-sitter-0.25.0-py313h1804a44_0.tar.bz2",
    "tree-sitter-0.25.1-py313h1804a44_0.tar.bz2",
    "tree-sitter-0.25.2-py313h1804a44_1.tar.bz2",
    "tree-sitter-go-0.23.4-py313h1804a44_1.tar.bz2",
    "tree-sitter-go-0.25.0-py313h1804a44_1.tar.bz2",
    "tree-sitter-java-0.23.5-py313h1804a44_0.tar.bz2",
    "tree-sitter-java-0.23.5-py313h1804a44_1.tar.bz2",
    "tree-sitter-python-0.25.0-py313h1804a44_1.tar.bz2",
]

platforms = ["noarch", "emscripten-wasm32"]

current_emscripten_forge_repodata = {}

# Read current repodata for emscripten-forge
for platform in platforms:
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
            if package in BLACKLIST:
                continue

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

            if platform != 'noarch' and 'emscripten-abi' not in package:
                correct = False
                for dep in pkg_info['depends']:
                    if 'emscripten-abi' in dep:
                        correct = True
                if not correct and package not in WHITELIST:
                    print(f'package {package} from {orig_channel} does not depend on emscripten-abi! Skipping')
                    continue

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
        "https://repo.prefix.dev/emscripten-forge-dev",
        "https://repo.prefix.dev/emscripten-forge-4x",
    ]

    # Cache containing pkgs already processed, storing this info in another file
    # allows us to have a smaller pkg_info.json
    total_packages = 0

    for url in channels_urls:
        for platform in platforms:
            resp = requests.get(f"{url}/{platform}/repodata.json.bz2", timeout=10)
            resp.raise_for_status()

            with bz2.BZ2File(io.BytesIO(resp.content)) as f:
                repodata = json.load(f)

            # TODO Process whls too?
            for packages_entry in ["packages", "packages.conda"]:
                repodata_packages = repodata.get(packages_entry, {})
                upload_packages(repodata_packages, packages_entry, url, platform)
