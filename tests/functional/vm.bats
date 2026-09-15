#!/usr/bin/env bats

# VM image build functional tests. Run before validate.bats.

# shellcheck disable=SC1091
load "${BATS_TEST_DIRNAME}/helpers/common.bash"

ALMA_REPOS="${BATS_TEST_DIRNAME}/../materials/repos/almalinux8-x86_64.yaml"
# AlmaLinux 8 Generic Cloud image (same URL as tests/unit/vm.py).
ALMA_CLOUD_IMAGE_X86_64="https://repo.almalinux.org/almalinux/8/cloud/x86_64/images/AlmaLinux-8-GenericCloud-latest.x86_64.qcow2"

require_qemu_img() {
  require_cmd qemu-img
}

require_kvm() {
  if [[ ! -e /dev/kvm ]]; then
    skip "/dev/kvm not available"
  fi
}

manage_init_vm() {
  local -a args=(
    --repos "${ALMA_REPOS}"
    --set 'arch=[x86_64]'
    --set shared_fs_type=virtiofs
    --set vm.memory=2048
  )
  if [[ -n "${https_proxy:-}" ]]; then
    args+=(--set "proxy=${https_proxy}")
  fi
  python3 "${MANAGE_PROJECT}" "${MANAGE_STATE[@]}" init "${args[@]}"
}

manage_state_set() {
  python3 "${MANAGE_PROJECT}" "${MANAGE_STATE[@]}" state --set "$1"
}

setup_file() {
  require_cmd rift
  require_mock
  require_qemu_img
  require_kvm
  manage_init_vm
}

setup() {
  manage_enter_project
}

@test "build and deploy VM test image" {
  run rift vm build --url "${ALMA_CLOUD_IMAGE_X86_64}" --deploy
  assert_exit_ok
  assert_file_exists "${PWD}/test.img"
  manage_state_set vm_image_ready=true
}

teardown() {
  stop_vm
}
