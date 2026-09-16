#!/usr/bin/env bats

# Package validate/test functional tests using the VM from vm.bats.

# shellcheck disable=SC1091
load "${BATS_TEST_DIRNAME}/helpers/common.bash"

manage_state_defined() {
  python3 "${MANAGE_PROJECT}" "${MANAGE_STATE[@]}" state --defined "$1" \
    || skip "suite meta '$1' not defined (run prerequisite bats first)"
}

setup_file() {
  if is_almalinux8_host; then
    return 0
  fi
  require_cmd rift
  require_mock
  manage_state_defined vm_image_ready
}

teardown_file() {
  if is_almalinux8_host; then
    return 0
  fi
  manage_destroy
}

setup() {
  skip_vm_suite_on_almalinux8
  manage_enter_project
}

teardown() {
  stop_vm
}

@test "validate pkg (rpm) on shared VM image" {
  run rift validate pkg --formats rpm
  assert_exit_ok
}

@test "validate pkg (rpm) with --quiet on shared VM image" {
  run rift validate pkg --formats rpm --quiet
  assert_exit_ok
}

@test "rift test pkg (rpm) after build on shared VM image" {
  run rift build pkg --formats rpm --publish
  assert_exit_ok
  run rift test pkg --formats rpm
  assert_exit_ok
}
