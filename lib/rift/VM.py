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
import socket
from subprocess import Popen, PIPE, STDOUT, check_output, CalledProcessError

from rift import RiftError
from rift.Config import _DEFAULT_VIRTIOFSD

__all__ = ['VM']

ARCH_EFI_BIOS = "./usr/share/edk2/aarch64/QEMU_EFI.silent.fd"

def is_virtiofs_qemu(virtiofsd=_DEFAULT_VIRTIOFSD):
    """
    This function checks if vitiofsd is from qemu package or a standalone rust
    version
    """
    output = ""
    try:
        output = check_output(f"{virtiofsd} --version",
                              stderr=STDOUT,
                              shell=True)
    except CalledProcessError:
        try:
            # virtiofsd from qemu need to be lauched as 'root'...
            output = check_output(f"sudo {virtiofsd} --version",
                                  stderr=STDOUT,
                                  shell=True)
        except CalledProcessError:
            logging.error("Cannot get %s version", virtiofsd)

    if 'qemu' in output.decode() or 'FUSE' in output.decode():
        logging.debug("%s: Qemu version detectect", virtiofsd)
        return True
    logging.debug("%s: Qemu version not detectect", virtiofsd)
    return False


def gen_virtiofs_args(socket_path, directory, qemu=False, virtiofsd=_DEFAULT_VIRTIOFSD):
    """
    Handle virtiofsd args.
    Both version don't have the same argument handling, this function provide
    the correct arguments for the two versions.
    """
    if qemu:
        return ['sudo', '%s' % virtiofsd,
                '--socket-path=%s' % socket_path,
                '-o', 'source=%s' % directory,
                '-o', 'cache=auto', '--syslog', '--daemonize']
    return ['%s' % virtiofsd,
            '--socket-path', '%s' % socket_path,
            '--sandbox=none', '--shared-dir', '%s' % directory,
            '--cache', 'auto']

class VM():
    """Manipulate VM process and related temporary files."""

    _PROJ_MOUNTPOINT = '/rift.project'
    NAME = 'rift1.domain'
    SUPPORTED_FS = ('9p', 'virtiofs')

    def __init__(self, config, repos, tmpmode=True):
        uniq_id = os.getuid() + 2000
        self._image = config.get('vm_image')
        self._project_dir = config.project_dir
        self._repos = repos or []

        self.address = config.get('vm_address')
        self.port = config.get('vm_port', uniq_id)
        self.cpus = config.get('vm_cpus', 1)
        self.memory = config.get('vm_memory')
        self.qemu = config.get('qemu')
        self.arch = config.get('arch')

        # default emulated cpu architecture
        if self.arch == 'aarch64':
            self.cpu_type = config.get('vm_cpu', 'cortex-a72')
        else:
            self.cpu_type = config.get('vm_cpu', 'host')

        # Specific aarch64 options
        self.arch_efi_bios = config.get('arch_efi_bios', ARCH_EFI_BIOS)
        ##

        # Get guest shared fstype
        self.virtiofsd = config.get('virtiofsd', _DEFAULT_VIRTIOFSD)
        self.shared_fs_type = config.get('shared_fs_type', '9p')
        if self.shared_fs_type not in self.SUPPORTED_FS:
            raise RiftError('{} not supported to share filesystems'.format(
                self.shared_fs_type))
        ##


        self.tmpmode = tmpmode
        self.copymode = config.get('vm_image_copy')
        self._vm = None
        self._helpers = []
        self._tmpimg = None
        self.consolesock = '/tmp/rift-vm-console-{0}.sock'.format(uniq_id)

    def _mk_tmp_img(self):
        """Create a temp VM image to avoid modifying the real image disk."""

        # Create a temporary file for VM image
        # XXX: Maybe a mkstemp() is better here to avoid removing file
        # when VM process is not stopped in purpose
        self._tmpimg = tempfile.NamedTemporaryFile(prefix='rift-vm-img-')

        if self.copymode:
            # Copy qcow image for VM, based on temp file
            cmd = ['dd', 'status=progress', 'conv=sparse', 'bs=1M']
            cmd += ['if=%s' % os.path.realpath(self._image)]
            cmd += ['of=%s' % self._tmpimg.name]
        else:
            # Create qcow image for VM, based on temp file
            cmd = ['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2']
            cmd += ['-o', 'backing_file=%s' % os.path.realpath(self._image)]
            cmd += [self._tmpimg.name]

        logging.debug("Creating VM image file: %s", ' '.join(cmd))
        popen = Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

    def _make_drive_cmd(self):
        cmd = []
        helper_cmd = []
        if self.shared_fs_type == '9p':
            cmd += ['-virtfs', 'local,id=project,path=/%s,mount_tag=project,'
                    'security_model=none' % self._project_dir]
            for repo in self._repos:
                if repo.is_file():
                    repo.create()
                    cmd += ['-virtfs',
                            'local,id=%s,path=%s,mount_tag=%s,security_model=none' %
                            (repo.name, repo.rpms_dir, repo.name)]
        elif self.shared_fs_type == 'virtiofs':
            # Add a shared memory object to allow virtiofsd shares
            cmd += ['-object',
                    f'memory-backend-file,id=mem,size={str(self.memory)}M,mem-path=/tmp,share=on',
                    '-machine',
                    'memory-backend=mem,accel=kvm']
            cmd += ['-chardev', 'socket,id=project,path=/tmp/.virtio_fs_project',
                    '-device', 'vhost-user-fs-pci,queue-size=1024,chardev=project,tag=project']

            qemu_version = is_virtiofs_qemu(self.virtiofsd)
            helper_cmd.append(
                gen_virtiofs_args(
                    socket_path='/tmp/.virtio_fs_project',
                    directory=self._project_dir,
                    qemu=qemu_version,
                    virtiofsd=self.virtiofsd
                )
            )
            for repo in self._repos:
                if repo.is_file():
                    repo.create()
                    cmd += ['-chardev', 'socket,id=%s,path=/tmp/.virtio_fs_%s' % ((repo.name,) * 2),
                            '-device', 'vhost-user-fs-pci,queue-size=1024,chardev=%s,tag=%s'
                            % ((repo.name,) * 2)]
                    helper_cmd.append(
                        gen_virtiofs_args(
                            socket_path='/tmp/.virtio_fs_%s' % repo.name,
                            directory=repo.rpms_dir,
                            qemu=qemu_version,
                            virtiofsd=self.virtiofsd
                        )
                    )
        return cmd, helper_cmd

    def _fix_socket_rights(self):
        """
        Ugly hack to have root accessible sockets for virtiofsd...
        """
        sockets = []
        if self.shared_fs_type == 'virtiofs':
            sockets = ['/tmp/.virtio_fs_project']
            for repo in self._repos:
                if repo.is_file():
                    sockets.append('/tmp/.virtio_fs_%s' % (repo.name))
            Popen(['sudo', '/bin/chmod', '777'] + sockets).wait()


    def spawn(self):
        """Start VM process in background"""

        # TODO: use -snapshot from qemu cmdline instead of creating temporary VM image
        if self.tmpmode:
            self._mk_tmp_img()
            imgfile = self._tmpimg.name
        else:
            imgfile = self._image

        # Start VM process
        cmd = shlex.split(self.qemu)
        if self.arch == 'x86_64':
            cmd += ['-enable-kvm']
        else:
            cmd += ['-machine', 'virt']

        cmd += ['-cpu', self.cpu_type]

        cmd += ['-name', 'rift', '-display', 'none']
        cmd += ['-m', str(self.memory), '-smp', str(self.cpus)]


        # UEFI for aarch64
        if self.arch == 'aarch64':
            cmd += ['-bios', self.arch_efi_bios]

        # Drive
        # TODO: switch to --device syntax
        cmd += ['-drive', 'file=%s,if=virtio,format=qcow2,cache=unsafe'
                % imgfile]

        # Console
        cmd += ['-chardev', 'socket,id=charserial0,path=%s,server=on,wait=off'
                % (self.consolesock)]
        if self.arch == 'aarch64':
            cmd += ['-device', 'virtio-serial,id=ser0,max_ports=8']
            cmd += ['-serial', 'chardev:charserial0']
        else:
            cmd += ['-device', 'isa-serial,chardev=charserial0,id=serial0']


        # NIC
        cmd += ['-netdev', 'user,id=hostnet0,hostname=%s,hostfwd=tcp::%d-:22'
                % (self.NAME, self.port)]
        if self.arch == 'aarch64':
            cmd += ['-device', 'virtio-net-device,netdev=hostnet0']
        else:
            cmd += ['-device', 'virtio-net-pci,netdev=hostnet0,bus=pci.0,addr=0x3']


        fs_cmds, helper_cmds = self._make_drive_cmd()
        cmd += fs_cmds


        logging.info("Qemu shared fs type: %s", self.shared_fs_type)
        for helper_cmd in helper_cmds:
            logging.info("Starting helper process (%s)", helper_cmd)
            self._helpers.append(Popen(helper_cmd, stderr=PIPE))

        logging.info("Waiting 5s for helper processes VM")
        time.sleep(5)
        logging.debug("Fix sockets right...")
        self._fix_socket_rights()

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

        if self.shared_fs_type == '9p':
            options = 'trans=virtio,version=9p2000.L,msize=131096'
        else:
            options = 'defaults'
            # For guest kernel > 5.6
            #options = 'defaults'
        # Build shared mount point info.
        mkdirs = [self._PROJ_MOUNTPOINT]
        fstab = ['project /%s %s %s,ro 0 0' % (self._PROJ_MOUNTPOINT, self.shared_fs_type, options)]
        repos = []
        prio = 1000
        for repo in self._repos:
            if repo.is_file():
                mkdirs.append('/rift.%s' % repo.name)
                fstab.append('%s /rift.%s %s %s 0 0' %
                             (repo.name, repo.name, self.shared_fs_type, options))
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
            if repo.excludepkgs:
                repos.append("excludepkgs={}\n".format(repo.excludepkgs))
            if repo.module_hotfixes:
                repos.append("module_hotfixes={}\n".format(repo.module_hotfixes))
            if repo.proxy:
                repos.append("proxy={}\n".format(repo.proxy))

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
            mount -t %s -a

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
                    ' '.join(mkdirs), "\n".join(fstab),
                    self.shared_fs_type, "\n".join(repos))
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
        output = memoryview(bytearray(32))

        # We use SOCK_STREAM as it comes the qemu UNIX socket confiuration
        console_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        console_socket.connect(self.consolesock)
        console_socket.setblocking(0)

        self_stdin = sys.stdin.fileno()
        old = termios.tcgetattr(self_stdin)
        new = list(old)
        new[3] = new[3] & ~termios.ECHO & ~termios.ISIG & ~termios.ICANON
        termios.tcsetattr(self_stdin, termios.TCSANOW, new)

        last_int = datetime.datetime.now()
        int_count = 0
        while 1:
            rdy = select.select([sys.stdin, console_socket], [], [console_socket])
            if console_socket in rdy[2]:
                sys.stderr.write('Connection closed\n')
                retcode = 1
                break
            # Exit if Ctrl-C is pressed repeatedly
            if sys.stdin in rdy[0]:
                buf = os.read(self_stdin, 4)
                # Here 3 == ^C
                if len(buf) > 0 and struct.unpack('b', buf[0:1])[0] == 3:
                    if (datetime.datetime.now() - last_int).total_seconds() > 2:
                        last_int = datetime.datetime.now()
                        int_count = 1
                    else:
                        int_count += 1

                    if int_count == 3:
                        print('\nDetaching ...')
                        break
                console_socket.sendall(buf)

            ## Get distant output (recv_into metod)
            if console_socket in rdy[0]:
                msg_len = console_socket.recv_into(output, 32)
                # Write to bytes array converted into strings
                sys.stdout.write(''.join(['%c' % m for m in output[:msg_len]]))
                sys.stdout.flush()

        # Restore terminal now to let user interrupt the wait if needed
        termios.tcsetattr(self_stdin, termios.TCSANOW, old)
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
        sleeping_time = 5
        if self.arch == 'aarch64': # VM very long to boot in emulation mode
            sleeping_time = 20

        for _ in range(1, 5):
            # Check if Qemu process is really running
            if self._vm.poll() is not None:
                raise RiftError("Unable to get VM running {}".format(
                    self._vm.stderr.read().decode()))
            time.sleep(sleeping_time)
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

        # Stop helper processes
        for helper in self._helpers:
            if helper.poll() is None:
                pid = helper.pid
                logging.debug("Sending TERM signal to helper process (%d)", pid)
                helper.terminate()


        # Unlink temp VM image
        if self._tmpimg and not self._tmpimg.closed:
            logging.debug("Unlink VM temporary image file '%s'",
                          self._tmpimg.name)
            self._tmpimg.close()
            self._tmpimg = None
