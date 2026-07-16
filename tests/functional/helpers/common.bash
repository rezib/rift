# Shared helpers for Rift Bats functional tests.

FUNCTIONAL_DIR="${BATS_TEST_DIRNAME}"
TESTS_DIR="${FUNCTIONAL_DIR}/.."
MATERIALS="${TESTS_DIR}/materials"
RPMS="${MATERIALS}/rpms"
PROJECT="${MATERIALS}/project"
REPOS="${MATERIALS}/repos"
RIFT_ROOT="$(cd "${TESTS_DIR}/.." && pwd)"

TEMP_PROJECT=""
WORKING_REPO=""

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || skip "'$1' not available"
}

require_mock() {
  require_cmd mock
}

require_podman() {
  require_cmd podman
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

setup_project() {
  TEMP_PROJECT="$(mktemp -d)"
  cp -a "${PROJECT}/." "${TEMP_PROJECT}/"
  mkdir -p "${TEMP_PROJECT}/annex"
  cd "${TEMP_PROJECT}" || return 1
}

configure_x86_64_project() {
  WORKING_REPO="$(mktemp -d)"
  export WORKING_REPO
  python3 "${FUNCTIONAL_DIR}/bin/configure-project" "${TEMP_PROJECT}" \
    --arch x86_64 \
    --working-repo "${WORKING_REPO}" \
    --repos "${REPOS}/almalinux8-x86_64.yaml"
}

teardown_project() {
  if [[ -n "${TEMP_PROJECT}" && -d "${TEMP_PROJECT}" ]]; then
    if [[ -f "${FUNCTIONAL_DIR}/bin/clean-mock" ]]; then
      python3 "${FUNCTIONAL_DIR}/bin/clean-mock" "${TEMP_PROJECT}" 2>/dev/null || true
    fi
    rm -rf "${TEMP_PROJECT}"
  fi
  if [[ -n "${WORKING_REPO}" && -d "${WORKING_REPO}" ]]; then
    rm -rf "${WORKING_REPO}"
  fi
  TEMP_PROJECT=""
  WORKING_REPO=""
}
