#
# Copyright (C) 2014 CEA
#

"""
Class to start, stop and manipulate VM used mostly for testing.
"""

import os
import pwd
import grp
import sys
import time
import logging
import tempfile
import textwrap
from subprocess import Popen, PIPE, STDOUT

from Rift import RiftError

__all__ = [ 'VM' ]

class VM(object):
    """Manipulate VM process and related temporary files."""

    _PROJ_MOUNTPOINT = '/rift.project'
    NAME = 'rift1'

    def __init__(self, config, repos, suppl_repos=[]):
        self._image = config.get('vm_image')
        self._repos = repos
        self._suppl_repos = suppl_repos

        self.address = config.get('vm_address')
        self.port = config.get('vm_port', os.getuid() + 2000)
        self.qemu = config.get('qemu')

        self._vm = None
        self._tmpimg = None

    def spawn(self):
        """Start VM process in background"""
        # Create a temporary file for VM image
        # XXX: Maybe a mkstemp() is better here to avoid removing file
        # when VM process is not stopped in purpose
        self._tmpimg = tempfile.NamedTemporaryFile(prefix='rift-vm-img-')

        # Create qcow image for VM, based on temp file
        cmd = [ 'qemu-img', 'create', '-f', 'qcow2' ]
        cmd += [ '-o', 'backing_file=%s' % os.path.realpath(self._image) ]
        cmd += [ self._tmpimg.name ]
        logging.debug("Creating VM image file: %s", ' '.join(cmd))
        popen = Popen(cmd, stdout=PIPE, stderr=STDOUT)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

        # Start VM process
        # Assume we are in project directory
        projectdir = os.path.realpath('.')
        cmd = [self.qemu, '-enable-kvm', '-name', 'rift', '-display', 'none']
        cmd += ['-m', '8192', '-smp', '8']
        cmd += ['-drive', 'file=%s,id=drive-ide0,format=qcow2,cache=none' 
                              % self._tmpimg.name]
        cmd += ['-netdev', 'user,id=hostnet0,hostname=%s,hostfwd=tcp::%d-:22'
                              % (self.NAME, self.port)]
        cmd += ['-device', 'virtio-net-pci,netdev=hostnet0,bus=pci.0,addr=0x3']
        cmd += ['-virtfs', 'local,id=project,path=/%s,mount_tag=project,'
                           'security_model=none' % projectdir]
        for repo in self._repos:
            cmd += ['-virtfs', 
                    'local,id=%s,path=%s,mount_tag=%s,security_model=none' %
                     (repo.name, repo.rpms_dir, repo.name) ]

        logging.info("Starting VM")
        logging.debug("Running VM command: %s", ' '.join(cmd))
        self._vm = Popen(cmd)

    def prepare(self):
        """
        Post-boot VM configuration.

        This configure user, group, hosts, yum repos and mount points.
        """
        # Be sure current user/group exists in VM
        userline = ':'.join([str(item) for item in pwd.getpwuid(os.getuid())])
        (g_name, g_passwd, g_gid, g_mem) = grp.getgrgid(os.getgid())
        groupline = '%s:%s:%s:%s' % (g_name, g_passwd, g_gid, ','.join(g_mem))

        # Build 9p mount point info.
        mkdirs = [self._PROJ_MOUNTPOINT]
        fstab = ['project /%s 9p trans=virtio,version=9p2000.L,ro 0 0' 
                                                       % self._PROJ_MOUNTPOINT]
        repos = []
        for prio, repo in enumerate(reversed(self._repos), 1):
            mkdirs.append('/rift.%s' % repo.name)
            fstab.append('%s /rift.%s 9p trans=virtio,version=9p2000.L 0 0' % 
                         (repo.name, repo.name))
            repos.insert(0, textwrap.dedent("""\
                [%s]
                name=%s
                baseurl=file:///rift.%s/
                gpgcheck=0
                priority=%s
                """) % (repo.name, repo.name, repo.name, prio))

        for prio, repo in enumerate(reversed(self._suppl_repos), len(self._repos) + 1):
            repos.insert(0, textwrap.dedent("""\
                [%s]
                name=%s
                baseurl=%s
                gpgcheck=0
                priority=%s
                """) % (repo.name, repo.name, repo.url, prio))

        # Build the full command line
        cmd = textwrap.dedent("""\
            # Static host resolution
            echo '%s %s'  >> /etc/hosts

            echo '%s' >> /etc/passwd
            echo '%s' >> /etc/group

            mkdir %s
            cat <<__EOF__ >>/etc/fstab
            %s
            __EOF__
            mount -t 9p -a

            cat <<__EOC__ >/etc/yum.repos.d/rift.repo
            %s
            __EOC__

            yum -d1 makecache
            """) % (self.address, self.NAME, userline, groupline,
                    ' '.join(mkdirs), "\n".join(fstab), "\n".join(repos))

        self.cmd(cmd)

    def cmd(self, command):
        """Run specified command inside this VM"""
        cmd = [ 'ssh', '-oStrictHostKeyChecking=no', '-oLogLevel=ERROR',
                '-oUserKnownHostsFile=/dev/null', '-T',
                '-p', str(self.port), 'root@127.0.0.1', command ]
        logging.debug("Running command in VM: %s", ' '.join(cmd))
        popen = Popen(cmd) #, stdout=PIPE, stderr=STDOUT)
        popen.wait()
        return popen.returncode

    def run_test(self, test):
        """
        Run specified test using this VM.
        
        If test is local, it is run on local host, if not, it is run inside the VM.
        """
        funcs = {}
        funcs['vm_cmd'] = 'ssh %s -T -p %d root@127.0.0.1 "$@"' \
                                    % ('-oStrictHostKeyChecking=no', self.port)
        funcs['vm_wait'] = textwrap.dedent("""\
            rc=1
            for i in {1..7}
            do
              sleep 5
              echo -n .
              vm_cmd echo -e '\\\\nConnection is OK' && rc=0 && break
            done
            return $rc""")
        funcs['vm_reboot'] = textwrap.dedent("""\
            echo -n 'Restarting VM...'
            vm_cmd 'reboot' && sleep 5 && vm_wait || return 1""")

        if not test.local:
            cmd = "cd %s; %s" % (self._PROJ_MOUNTPOINT, test.command)
            return self.cmd(cmd)
        else:
            cmd = ''
            for func, code in funcs.items():
                cmd += '%s() { %s;}; export -f %s; ' % (func, code, func)
            cmd += test.command

            logging.debug("Running command outside VM: %s", cmd)
            popen = Popen(cmd, shell=True) #, stdout=PIPE, stderr=STDOUT)
            popen.wait()
            return popen.returncode

    def ready(self):
        """
        Wait until VM is ready to accept commands. 
        
        Return False if it is not ready after 25 seconds.
        """
        for _ in range(1, 5):
            time.sleep(5)
            if self.cmd('/bin/true') == 0:
                return True
            sys.stdout.write('.')
            sys.stdout.flush()
        return False

    def stop(self):
        """
        Shutdown the VM and remove temporary files.

        First try to terminate it cleanly for 5 sec. It fails, kill it.
        """
        # Sending TERM signal
        if self._vm.poll() is None:
            pid = self._vm.pid
            logging.debug("Sending TERM signal to VM process (%d)", pid)
            self._vm.terminate()

        # Delay for VM to cleanly shutdown before killing it
        for _ in range(1, 5):
            if self._vm.poll() is not None:
                break   
            time.sleep(1)
        else:
            pid = self._vm.pid
            logging.debug("Sending KILL signal to VM process (%d)", pid)
            self._vm.kill()

        # Unlink temp VM image
        if self._tmpimg and not self._tmpimg.closed:
            logging.debug("Unlink VM temporary image file '%s'",
                          self._tmpimg.name)
            self._tmpimg.close()
            self._tmpimg = None
