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
Helper classes to manipulate RPM files and SPEC files.
"""

import os
import re
import rpm
import time
import shutil
import logging
from subprocess import Popen, PIPE, STDOUT

from rift import RiftError
from rift.Annex import Annex, is_binary

RPMLINT_CONFIG = 'rpmlint'

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

    def extract_srpm(self, specdir, srcdir, annex=None):
        """
        Extract source rpm files into `specdir' and `srcdir'.

        If some binary files are extracted, they are moved to default annex
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

        # Move binary source files to Annex
        annex = annex or Annex(self._config)
        for filename in self._srcfiles:
            filepath = os.path.join(srcdir, filename)
            if is_binary(filepath):
                annex.push(filepath)


class Spec(object):
    """Access information from a Specfile and build SRPMS."""

    def __init__(self, filepath=None):
        self.filepath = filepath
        self.srpmname = None
        self.pkgnames = []
        self.sources = []
        self.basename = None
        self.version = None
        self.release = None
        self.changelog_name = None
        self.changelog_time = None
        self.evr = None
        self.arch = None
        if self.filepath is not None:
            self.load()

    def load(self):
        """Extract interesting information from spec file."""
        if not os.path.exists(self.filepath):
            raise RiftError('%s does not exist' % self.filepath)
        try:
            rpm.reloadConfig()
            spec = rpm.TransactionSet().parseSpec(self.filepath)
        except ValueError as exp:
            raise RiftError("%s: %s" % (self.filepath, exp))
        self.pkgnames = [pkg.header['name'] for pkg in spec.packages]
        hdr = spec.sourceHeader
        self.srpmname = hdr.sprintf('%{NAME}-%{VERSION}-%{RELEASE}.src.rpm')
        self.basename = hdr.sprintf('%{NAME}')
        self.version = hdr.sprintf('%{VERSION}')
        self.arch = hdr.sprintf('%{ARCH}')
        if hdr[rpm.RPMTAG_CHANGELOGNAME]:
            self.changelog_name = hdr[rpm.RPMTAG_CHANGELOGNAME][0]
        if hdr[rpm.RPMTAG_CHANGELOGTIME]:
            self.changelog_time = hdr[rpm.RPMTAG_CHANGELOGTIME][0]
        self.sources.extend(hdr[rpm.RPMTAG_SOURCE])
        self.sources.extend(hdr[rpm.RPMTAG_PATCH])

        # Reload to get information without dist macro set.
        rpm.delMacro('dist')
        hdr = rpm.TransactionSet().parseSpec(self.filepath).sourceHeader

        self.release = hdr.sprintf('%{RELEASE}')
        self.evr = hdr.sprintf('%|epoch?{%{epoch}:}:{}|%{version}-%{release}')

    def add_changelog_entry(self, userstring, comment):
        """
        Add a new entry to changelog.

        New record is based on current time and is first in list.
        """

        lines = []
        with open(self.filepath, 'r') as fspec:
            lines = fspec.readlines()

        date = time.strftime("%a %b %d %Y", time.gmtime())
        newchangelogentry = "* %s %s - %s\n%s\n" % \
            (date, userstring, self.evr, comment)

        for i in range(len(lines)):
            if re.match(r'^%changelog(\s|$)', lines[i]):
                if len(lines) > i + 1 and lines[i + 1].strip() != "":
                    newchangelogentry += "\n"

                lines[i] += newchangelogentry
                break
        else:
            if lines[-1].strip() != "":
                lines.append("\n")
            lines.append("%changelog\n")
            lines.append(newchangelogentry)

        with open(self.filepath, 'w') as fspec:
            fspec.writelines(lines)

        # Reload
        self.load()

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

    def _check(self, configdir=None):
        if configdir:
            env = os.environ.copy()
            env['XDG_CONFIG_HOME'] = configdir
        else:
            env = None

        cmd = ['rpmlint', '-o', 'NetworkEnabled False', self.filepath]
        logging.debug('Running rpmlint: %s', ' '.join(cmd))
        return cmd, env

    def check(self, configdir=None):
        """Check specfile content using `rpmlint' tool."""
        cmd, env = self._check(configdir)
        popen = Popen(cmd, stderr=PIPE, env=env)
        stderr = popen.communicate()[1]
        if popen.returncode != 0:
            raise RiftError(stderr or 'rpmlint reported errors')

    def analyze(self, review, configdir=None):
        """Run `rpmlint' for this specfile and fill provided `review'."""
        cmd, env = self._check(configdir)
        popen = Popen(cmd, stdout=PIPE, stderr=PIPE, env=env)
        stdout, stderr = popen.communicate()
        if popen.returncode not in (0, 64, 66):
            raise RiftError(stderr or 'rpmlint returned %d' % popen.returncode)

        for line in stdout.splitlines():
            if line.startswith(self.filepath + ':'):
                line = line[len(self.filepath + ':'):]
                try:
                    linenbr = None
                    code, txt = line.split(':', 1)
                    if code.isdigit():
                        linenbr = int(code)
                        code, txt = txt.split(':', 1)
                    review.add_comment(self.filepath, linenbr,
                                       code.strip(), txt.strip())
                except (ValueError, KeyError):
                    pass

        if popen.returncode != 0:
            review.invalidate()
