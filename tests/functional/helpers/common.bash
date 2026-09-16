# Shared helpers for Rift Bats functional tests.

FUNCTIONAL_DIR="${BATS_TEST_DIRNAME}"
FUNCTIONAL_STATE="${RIFT_FUNCTIONAL_STATE:-${FUNCTIONAL_DIR}/.state/suite.yaml}"
MANAGE_PROJECT="${FUNCTIONAL_DIR}/bin/manage-project"
MANAGE_STATE=(--state-file "${FUNCTIONAL_STATE}")

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || skip "'$1' not available"
}

require_mock() {
  require_cmd mock
}

# VM functional tests (vm.bats, validate.bats) are skipped on AlmaLinux 8 hosts:
# - The suite builds an Alma 8 cloud guest whose kernel has CONFIG_NET_9P unset,
#   so 9p shared mounts in the guest are not available.
# - On Alma 8 GitHub Actions runners (nested privileged containers), stock qemu
#   virtiofsd (--daemonize, default namespace sandbox) often fails vhost-user setup;
#   we do not change core Rift virtiofsd startup for CI.
# Run the VM suite on the Fedora matrix job; smoke.bats and build.bats still run here.
is_almalinux8_host() {
  if [[ ! -r /etc/os-release ]]; then
    return 1
  fi
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID}" == "almalinux" && "${VERSION_ID%%.*}" == "8" ]]
}

# Call from setup() only; skip in setup_file/teardown_file makes Bats fail the hook.
skip_vm_suite_on_almalinux8() {
  if is_almalinux8_host; then
    skip "VM functional suite skipped on AlmaLinux 8 (see comment above skip_vm_suite_on_almalinux8 in common.bash)"
  fi
}

manage_destroy() {
  python3 "${MANAGE_PROJECT}" "${MANAGE_STATE[@]}" destroy
}

manage_enter_project() {
  cd "$(python3 "${MANAGE_PROJECT}" "${MANAGE_STATE[@]}" show --field project_dir)" || return 1
}

# Stop QEMU for the current project (no-op if none running). Run from project_dir.
stop_vm() {
  rift vm stop >/dev/null 2>&1 || true
}

assert_exit_ok() {
  if [[ "$status" -ne 0 ]]; then
    echo "Expected exit 0, got ${status}" >&2
    echo "output: ${output}" >&2
    false
  fi
}

assert_file_exists() {
  if [[ ! -f "$1" ]]; then
    echo "Expected file '${1}' to exist" >&2
    false
  fi
}
