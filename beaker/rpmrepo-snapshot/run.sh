#!/bin/bash

set -eo pipefail

dnf -y group install "Development Tools"
pip3 install python-keystoneclient python-swiftclient

mkdir \
        -p \
        "build" \
        "src"
git \
        clone \
        "https://github.com/osbuild/rpmci" \
        "src/rpmci"

python3 -m "src/rpmci/rpmrepo" \
        --cache "build" \
        --local "beaker" \
        pull \
                --base-url "${RPMREPO_BASEURL}" \
                --platform-id "${RPMREPO_PLATFORM_ID}"

python3 -m "src/rpmci/rpmrepo" \
        --cache "build" \
        --local "beaker" \
        index

if [[ ${RPMREPO_STORAGE} == "psi" ]] ; then
        KEY_ID="${RPMREPO_OS_APP_CRED_ID}"
        KEY_SECRET="${RPMREPO_OS_APP_CRED_SECRET}"
else
        KEY_ID="${RPMREPO_AWS_ACCESS_KEY_ID}"
        KEY_SECRET="${RPMREPO_AWS_SECRET_ACCESS_KEY}"
fi

python3 -m "src/rpmci/rpmrepo" \
        --cache "build" \
        --local "beaker" \
        push \
                --to \
                        "snapshot" \
                        "s3" \
                        "${RPMREPO_SNAPSHOT_ID}" \
                        "${RPMREPO_AWS_ACCESS_KEY_ID}" \
                        "${RPMREPO_AWS_SECRET_ACCESS_KEY}" \
                --to \
                        "data" \
                        "${RPMREPO_STORAGE}" \
                        "${RPMREPO_PLATFORM_ID}" \
                        "${KEY_ID}" \
                        "${KEY_SECRET}"
