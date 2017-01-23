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

import xml.etree.cElementTree as ET

from Rift.TextTable import TextTable

class TestCase(object):

    def __init__(self, name):
        self.name = name
        self.classname = None
        self.result = None
        self.time = None

    def fullname(self):
        if self.classname:
            return '%s.%s' % (self.classname, self.name)
        else:
            return self.name

class TestResults(object):

    def __init__(self, name=None):
        self.name = name
        self.results = []
        self.global_result = True

    def __len__(self):
        return len(self.results)

    def add_failure(self, name, classname=None, time=None):
        self._add_result(classname, name, 'Failure', time)
        self.global_result = False

    def add_success(self, name, classname=None, time=None):
        self._add_result(classname, name, 'Success', time)

    def _add_result(self, classname, name, result, time):
        case = TestCase(name)
        case.time = time
        case.result = result
        case.classname = classname
        self.results.append(case)

    def junit(self, filename):

        suite = ET.Element('testsuite', tests=str(len(self.results)))
        if self.name:
            suite.set('name', self.name)

        for case in self.results:
            sub = ET.SubElement(suite, 'testcase', name=case.name)
            if case.classname:
                sub.set('classname', case.classname)
            if case.time:
                sub.set('time', '%.2f' % case.time)
            if case.result == 'Failure':
                ET.SubElement(sub, 'failure')

        tree = ET.ElementTree(suite)
        tree.write(filename, encoding='UTF-8', xml_declaration=True)

    def summary(self):
        tbl = TextTable("%name %>duration %result")
        for case in self.results:
            result = case.result
            if case.result == 'Failure':
                result = result.upper()
            tbl.append({'name': case.fullname(),
                        'duration': '%.0fs' % case.time,
                        'result': result})
        return str(tbl)
