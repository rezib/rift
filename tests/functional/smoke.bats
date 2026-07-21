#!/usr/bin/env bats

# shellcheck disable=SC1091
load "${BATS_TEST_DIRNAME}/helpers/common.bash"

setup_file() {
  require_cmd rift
}

@test "rift --version exits 0" {
  run rift --version
  assert_exit_ok
  [[ "${output}" == *"Rift"* ]]
}

@test "rift --help exits 0" {
  run rift --help
  assert_exit_ok
  [[ "${output}" == *"build"* ]]
  [[ "${output}" == *"validate"* ]]
}
