#!/usr/bin/env bash
# Syntax/configuration checks only; no service is installed or started.
set -euo pipefail
out=${1:?output directory required}
mkdir -p "$out"
trap 'result=$?; printf "exit_code=%s\n" "$result" > "$out/result.txt"' EXIT
uname -a > "$out/kernel.txt"
lscpu > "$out/cpu.txt"
systemd --version > "$out/systemd.txt"
git rev-parse HEAD > "$out/source-commit.txt"
for script in cloud/linux/*.sh; do
    bash -n "$script"
done
systemd-analyze verify --man=no cloud/linux/m3-worker-example.service > "$out/unit-verification.txt" 2>&1
printf 'PASS: shell syntax and worker unit configuration. Runtime limits and laptop performance are not measured.\n' > "$out/summary.txt"
