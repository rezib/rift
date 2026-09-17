#!/usr/bin/env bats

# shellcheck disable=SC1091
load "${BATS_TEST_DIRNAME}/helpers/common.bash"

ALMA_REPOS="${BATS_TEST_DIRNAME}/../materials/repos/almalinux8-x86_64.yaml"

require_podman() {
  require_cmd podman
}

manage_init_build() {
  python3 "${MANAGE_PROJECT}" "${MANAGE_STATE[@]}" init \
    --repos "${ALMA_REPOS}" \
    --set 'arch=[x86_64]'
}

assert_file_not_exists() {
  if [[ -f "$1" ]]; then
    echo "Expected file '${1}' not to exist" >&2
    false
  fi
}

setup_file() {
  require_cmd rift
  require_mock
}

setup() {
  manage_init_build
  manage_enter_project
  WORKING_REPO="$(python3 "${MANAGE_PROJECT}" "${MANAGE_STATE[@]}" show --field working_repo)"
  export WORKING_REPO
}

teardown() {
  manage_destroy
}

@test "build and publish pkg on x86_64" {
  require_podman
  run rift build pkg --publish
  assert_exit_ok
  assert_file_exists "${WORKING_REPO}/x86_64/pkg-1.0-1.noarch.rpm"
  assert_file_exists "${WORKING_REPO}/oci/pkg_1.0-1.x86_64.tar"
}

@test "build and publish pkg on x86_64 with --formats rpm" {
  run rift build pkg --formats rpm --publish
  assert_exit_ok
  assert_file_exists "${WORKING_REPO}/x86_64/pkg-1.0-1.noarch.rpm"
  assert_file_not_exists "${WORKING_REPO}/oci/pkg_1.0-1.x86_64.tar"
}
