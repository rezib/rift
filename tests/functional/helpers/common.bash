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
