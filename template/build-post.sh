#!/bin/bash

set -x
set -e

echo '> Fetching Vm kernel version...'
uname -r

echo '> Fetching Vm repositories...'
grep '^\[' /etc/yum.repos.d/*

echo '> Disable default repositories'
for repo in $(grep "^\[" /etc/yum.repos.d/CentOS* /etc/yum.repos.d/alma* /etc/yum.repos.d/Rocky* -h | sed -e "s/\]\|\[//g"); do
    yum-config-manager --disable $repo
    echo "    * $repo - disabled"
done

if [ -n "${RIFT_ADDITIONAL_RPMS}" ]; then
  RPM_NAMES=$(echo ${RIFT_ADDITIONAL_RPMS}| tr ':' ' ')
  echo '> Installing provided RPMS...'
  cd /tmp
  ls -atl
  rpm -Uvh $RPM_NAMES
  rm $RPM_NAMES
  test $? || exit 1
fi

if [ ${RIFT_SHARED_FS_TYPE} = "9p" ] ; then
    echo '> Checking 9p modules...'
    modinfo 9pnet_virtio
    echo '> Loading 9p kernel module...'
    modprobe 9pnet_virtio
fi

echo '> Yum update...'
yum -y update || true

echo '> Yum cleaning...'
yum clean all
rm -f /var/log/yum.log
