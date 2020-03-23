#
# Copyright (C) 2014-2016 CEA
#
# This file is part of Rift project.
#
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.
#

"""
Class to start, stop and manipulate VM used mostly for testing.
"""

import os
import pwd
import grp
import sys
import time
import datetime
import shlex
import pipes
import logging
import tempfile
import textwrap
import termios
import select
import struct
from subprocess import Popen, PIPE, STDOUT

from rift import RiftError

__all__ = ['VM']

class VM(object):
    """Manipulate VM process and related temporary files."""

    _PROJ_MOUNTPOINT = '/rift.project'
    NAME = 'rift1.domain'

    def __init__(self, config, repos, tmpmode=True):
        uniq_id = os.getuid() + 2000
        self._image = config.get('vm_image')
        self._project_dir = config.project_dir
        self._repos = repos or []

        self.address = config.get('vm_address')
        self.port = config.get('vm_port', uniq_id)
        self.cpus = config.get('vm_cpus', 1)
        self.cpu_type = config.get('vm_cpu', 'host')
        self.qemu = config.get('qemu')

        self.tmpmode = tmpmode
        self._vm = None
        self._tmpimg = None
        self.consolesock = '/tmp/rift-vm-console-{0}.sock'.format(uniq_id)

    def _mk_tmp_img(self):
        """Create a temp VM image to avoid modifying the real image disk."""

        # Create a temporary file for VM image
        # XXX: Maybe a mkstemp() is better here to avoid removing file
        # when VM process is not stopped in purpose
        self._tmpimg = tempfile.NamedTemporaryFile(prefix='rift-vm-img-')

        # Create qcow image for VM, based on temp file
        cmd = ['qemu-img', 'create', '-f', 'qcow2']
        cmd += ['-o', 'backing_file=%s' % os.path.realpath(self._image)]
        cmd += [self._tmpimg.name]
        logging.debug("Creating VM image file: %s", ' '.join(cmd))
        popen = Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

    def spawn(self):
        """Start VM process in background"""

        if self.tmpmode:
            self._mk_tmp_img()
            imgfile = self._tmpimg.name
        else:
            imgfile = self._image

        # Start VM process
        cmd = shlex.split(self.qemu)
        cmd += ['-enable-kvm', '-name', 'rift', '-display', 'none']
        cmd += ['-m', '8192', '-smp', str(self.cpus), '-cpu', self.cpu_type]

        # Drive
        cmd += ['-drive', 'file=%s,if=virtio,format=qcow2,cache=unsafe'
                % imgfile]

        # Console
        cmd += ['-chardev', 'socket,id=charserial0,path=%s,server,nowait'
                % (self.consolesock)]
        cmd += ['-device', 'isa-serial,chardev=charserial0,id=serial0']

        # NIC
        cmd += ['-netdev', 'user,id=hostnet0,hostname=%s,hostfwd=tcp::%d-:22'
                % (self.NAME, self.port)]
        cmd += ['-device', 'virtio-net-pci,netdev=hostnet0,bus=pci.0,addr=0x3']


        cmd += ['-virtfs', 'local,id=project,path=/%s,mount_tag=project,'
                           'security_model=none' % self._project_dir]
        for repo in self._repos:
            if repo.is_file():
                repo.create()
                cmd += ['-virtfs',
                        'local,id=%s,path=%s,mount_tag=%s,security_model=none' %
                        (repo.name, repo.rpms_dir, repo.name)]

        logging.info("Starting VM process")
        logging.debug("Running VM command: %s", ' '.join(cmd))
        self._vm = Popen(cmd, stderr=PIPE)

    def prepare(self):
        """
        Post-boot VM configuration.

        This configure user, group, hosts, yum repos and mount points.
        """
        # Be sure current user/group exists in VM
        userline = ':'.join([str(item) for item in pwd.getpwuid(os.getuid())])
        (g_name, g_passwd, g_gid, g_mem) = grp.getgrgid(os.getgid())
        groupline = '%s:%s:%s:%s' % (g_name, g_passwd, g_gid, ','.join(g_mem))

        options = 'trans=virtio,version=9p2000.L,msize=131096'
        # Build 9p mount point info.
        mkdirs = [self._PROJ_MOUNTPOINT]
        fstab = ['project /%s 9p %s,ro 0 0' % (self._PROJ_MOUNTPOINT, options)]
        repos = []
        prio = 1000
        for repo in self._repos:
            if repo.is_file():
                mkdirs.append('/rift.%s' % repo.name)
                fstab.append('%s /rift.%s 9p %s 0 0' %
                             (repo.name, repo.name, options))
                url = 'file:///rift.%s/' % repo.name
            else:
                url = repo.url
            prio = repo.priority or (prio - 1)
            repos.append(textwrap.dedent("""\
                [%s]
                name=%s
                baseurl=%s
                gpgcheck=0
                priority=%s
                """) % (repo.name, repo.name, url, prio))

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

            /bin/rm -f /etc/yum.repos.d/*.repo

            cat <<__EOC__ >/etc/yum.repos.d/rift.repo
            %s
            __EOC__

            if [ -x /usr/bin/dnf ] ; then
                dnf -d1 makecache
            else
                yum -d1 makecache fast
            fi

            """) % (self.address, self.NAME, userline, groupline,
                    ' '.join(mkdirs), "\n".join(fstab), "\n".join(repos))

        self.cmd(cmd)

    def cmd(self, command=None, options=('-T',), stderr=None):
        """Run specified command inside this VM"""
        cmd = ['ssh', '-oStrictHostKeyChecking=no', '-oLogLevel=ERROR',
               '-oUserKnownHostsFile=/dev/null', '-p', str(self.port),
               'root@127.0.0.1']
        if options:
            cmd += options
        if command:
            cmd.append(command)
        logging.debug("Running command in VM: %s", ' '.join(cmd))
        popen = Popen(cmd, stderr=stderr) #, stdout=PIPE, stderr=STDOUT)
        popen.wait()
        return popen.returncode

    def copy(self, source, dest, stderr=None):
        """Copy files within or without VM"""
        cmd = ['scp', '-oStrictHostKeyChecking=no', '-oLogLevel=ERROR',
               '-oUserKnownHostsFile=/dev/null', '-P', str(self.port)]
        cmd.append(source.replace('rift:', 'root@127.0.0.1:'))
        cmd.append(dest.replace('rift:', 'root@127.0.0.1:'))
        logging.debug("Copy files with VM: %s", ' '.join(cmd))
        popen = Popen(cmd, stderr=stderr)
        popen.wait()
        return popen.returncode

    def console(self):
        """Console of VM Hit Ctrl-C 3 times to exit"""
        retcode = 0
        self_stdin = sys.stdin.fileno()
        old = termios.tcgetattr(self_stdin)
        new = list(old)
        new[3] = new[3] & ~termios.ECHO & ~termios.ISIG & ~termios.ICANON
        termios.tcsetattr(self_stdin, termios.TCSANOW, new)

        s_ctl = Popen(shlex.split('nc -U %s' % (self.consolesock)), stdin=PIPE)

        last_int = datetime.datetime.now()
        int_count = 0

        while 1:
            rdy = select.select([sys.stdin, s_ctl.stdin], [], [s_ctl.stdin])

            if s_ctl.stdin in rdy[2] or s_ctl.stdin in rdy[0]:
                sys.stderr.write('Connection closed\n')
                retcode = 1
                break

            # Exit if Ctrl-C is pressed repeatedly
            if sys.stdin in rdy[0]:
                buf = os.read(self_stdin, 1024)
                if struct.unpack('b', buf[0:1])[0] == 3:
                    if (datetime.datetime.now() - last_int).total_seconds() > 2:
                        last_int = datetime.datetime.now()
                        int_count = 1
                    else:
                        int_count += 1

                    if int_count == 3:
                        print('\nDetaching ...')
                        break

                s_ctl.stdin.write(buf)

        # Restore terminal now to let user interrupt the wait if needed
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, old)

        s_ctl.terminate()
        s_ctl.wait()
        return retcode

    def run_test(self, test):
        """
        Run specified test using this VM.

        If test is local, it is run on local host, if not, it is run inside the
        VM.
        """
        funcs = {}
        funcs['vm_cmd'] = 'ssh %s -T -p %d root@127.0.0.1 "$@"' \
                 % ('-oUserKnownHostsFile=/dev/null -oStrictHostKeyChecking=no '
                    '-oLogLevel=ERROR', self.port)
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
            vm_cmd 'reboot' || true; sleep 5 && vm_wait || return 1""")

        if not test.local:
            if test.command.startswith(self._project_dir):
                testcmd = test.command[len(self._project_dir) + 1:]
            else:
                testcmd = test.command
            cmd = "cd %s; %s" % (self._PROJ_MOUNTPOINT, testcmd)
            return self.cmd(cmd)

        cmd = ''
        for func, code in funcs.items():
            cmd += '%s() { %s;}; export -f %s; ' % (func, code, func)
        cmd += pipes.quote(test.command)

        logging.debug("Running command outside VM: %s", cmd)
        popen = Popen(cmd, shell=True) #, stdout=PIPE, stderr=STDOUT)
        popen.wait()
        return popen.returncode

    def running(self):
        """Check if VM is already running."""
        return self.cmd('/bin/true', stderr=PIPE) == 0

    def ready(self):
        """
        Wait until VM is ready to accept commands.

        Return False if it is not ready after 25 seconds.
        """
        for _ in range(1, 5):
            # Check if Qemu process is really running
            if self._vm.poll() is not None:
                raise RiftError("Unable to get VM running {}".format(
                    self._vm.stderr.read().decode()))
            time.sleep(5)
            if self.running():
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
