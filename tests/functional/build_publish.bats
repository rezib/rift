#!/usr/bin/env bats

# shellcheck disable=SC1091
load "${BATS_TEST_DIRNAME}/helpers/common.bash"

setup_file() {
  require_cmd rift
  require_mock
  require_podman
}

setup() {
  setup_project
  configure_x86_64_project
}

teardown() {
  teardown_project
}

@test "build and publish pkg on x86_64" {
  run rift build pkg --publish
  assert_exit_ok
  assert_file_exists "${WORKING_REPO}/x86_64/pkg-1.0-1.noarch.rpm"
  assert_file_exists "${WORKING_REPO}/oci/pkg_1.0-1.x86_64.tar"
}
