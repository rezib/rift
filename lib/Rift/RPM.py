#
# Copyright (C) 2014 CEA
#

"""
Helper classes to manipulate RPM files and SPEC files.
"""

import os
import rpm
import shutil
import logging
from subprocess import Popen, PIPE, STDOUT

from Rift import RiftError
from Rift.LookAside import LookAside, is_binary

class RPM(object):
    """Manipulate a source or binary RPM."""

    def __init__(self, filepath, config=None):
        self.filepath = filepath
        self._config = config

        self.name = None
        self.is_source = False
        self.arch = None
        self._srcfiles = []

        self._load()

    def _load(self):
        """Extract interesting information from RPM file header"""
        # Read header
        fileno = os.open(self.filepath, os.O_RDONLY)
        ts = rpm.TransactionSet()
        ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)
        hdr = ts.hdrFromFdno(fileno)
        os.close(fileno)

        # Extract data
        self.name = hdr[rpm.RPMTAG_NAME]
        self.arch = hdr[rpm.RPMTAG_ARCH]
        self.is_source = hdr.isSource()
        self._srcfiles.extend(hdr[rpm.RPMTAG_SOURCE])
        self._srcfiles.extend(hdr[rpm.RPMTAG_PATCH])

    def extract_srpm(self, specdir, srcdir, lookaside=None):
        """
        Extract source rpm files into `specdir' and `srcdir'.
        
        If some binary files are extracted, they are moved to default lookaside
        or provided one.
        """
        assert self.is_source

        srcdir = os.path.realpath(srcdir)

        # Extract (install) source file and spec file from source rpm
        cmd = ['rpm', '-iv']
        cmd += ['--define', '_sourcedir %s' % srcdir]
        cmd += ['--define', '_specdir %s' % os.path.realpath(specdir)]
        cmd += [self.filepath]
        popen = Popen(cmd, stdout=PIPE, stderr=STDOUT)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

        # Backup original spec file
        specfile = os.path.join(specdir, '%s.spec' % self.name)
        shutil.copy(specfile, '%s.orig' % specfile)

        # Move binary source files to LookAside
        lookaside = lookaside or LookAside(self._config)
        for filename in self._srcfiles:
            filepath = os.path.join(srcdir, filename)
            if is_binary(filepath):
                lookaside.push(filepath)


class Spec(object):
    """Access information from a Specfile and build SRPMS."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.srpmname = None
        self.pkgnames = []
        self._load()

    def _load(self):
        """Extract interesting information from spec file."""
        if not os.path.exists(self.filepath):
            raise RiftError('%s does not exist' % self.filepath)
        try:
            spec = rpm.TransactionSet().parseSpec(self.filepath)
        except ValueError as exp:
            raise RiftError(str(exp))
        self.pkgnames = [pkg.header['name'] for pkg in spec.packages]
        hdr = spec.sourceHeader
        self.srpmname = hdr.sprintf('%{NAME}-%{VERSION}-%{RELEASE}.src.rpm')

    def build_srpm(self, srcdir, destdir):
        """
        Build a Source RPM described by this spec file.

        Return a RPM instance of this source RPM.
        """
        cmd = ['rpmbuild', '-bs']
        cmd += ['--define', '_sourcedir %s' % srcdir]
        cmd += ['--define', '_srcrpmdir %s' % destdir]
        cmd += [self.filepath]

        popen = Popen(cmd, stdout=PIPE, stderr=STDOUT)
        stdout = popen.communicate()[0]
        if popen.returncode != 0:
            raise RiftError(stdout)

        return RPM(os.path.join(destdir, self.srpmname))

    def check(self, configdir=None):
        """Check specfile content using `rpmlint' tool."""
        if configdir:
            env = os.environ.copy()
            env['XDG_CONFIG_HOME'] = configdir
        else:
            env = None

        cmd = ['rpmlint', '-o', 'NetworkEnabled False', self.filepath]
        logging.debug('Running rpmlint: %s', ' '.join(cmd))
        popen = Popen(cmd, stderr=PIPE, env=env)
        stderr = popen.communicate()[1]
        if popen.returncode != 0:
            raise RiftError(stderr or 'rpmlint reported errors')
