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

import collections
import xml.etree.cElementTree as ET

from rift.TextTable import TextTable

class TestCase():
    """
    TestCase: oject for to manage a Test to format ajunit file in TestResult
    """

    def __init__(self, name, classname, arch):
        """
        name: TestCase name
        classname: TestCase classname
        arch: TestCase CPU architecture
        """
        self.name = name
        self.classname = classname
        self.arch = arch

    @property
    def fullname(self):
        """
        return the TestCase fullname
        """
        if self.classname:
            return '%s.%s' % (self.classname, self.name)
        return self.name


TestResult = collections.namedtuple(
    'TestResult', ['case', 'value', 'time', 'output']
)


class TestResults():
    """
    TestResults: gather and mange TestCase results
    """

    def __init__(self, name=None):
        """
        name: TestResults name
        properties:
            - results: list containing tests results
        """
        self.name = name
        self.results = []
        self.global_result = True

    def __len__(self):
        """
        return number of results
        """
        return len(self.results)

    def add_failure(self, case, time, output=None):
        """
        Add a failed TestCase
        """
        self._add_result(TestResult(case, 'Failure', time, output))
        self.global_result = False

    def add_success(self, case, time, output=None):
        """
        Add a successful TestCase
        """
        self._add_result(TestResult(case, 'Success', time, output))

    def _add_result(self, result):
        """
        Add a result from a TestCase
        """
        self.results.append(result)

    def junit(self, filename):
        """
        Generate a junit xml file containing all tests results
        """

        suite = ET.Element('testsuite', tests=str(len(self.results)))
        if self.name:
            suite.set('name', self.name)

        for result in self.results:
            sub = ET.SubElement(suite, 'testcase', name=result.case.name)
            if result.case.classname:
                sub.set('classname', 'rift.%s' % result.case.classname)
            if result.time:
                sub.set('time', '%.2f' % result.time)
            if result.value == 'Failure':
                failure = ET.SubElement(sub, 'failure')
                failure.text = result.output

        tree = ET.ElementTree(suite)
        tree.write(filename, encoding='UTF-8', xml_declaration=True)

    def summary(self):
        """
        Get a summary table of all tests
        """
        tbl = TextTable("%name %arch %>duration %result")
        for result in self.results:
            tbl.append(
                {
                    'name': result.case.fullname,
                    'arch': result.case.arch,
                    'duration': '%.0fs' % result.time,
                    'result': (
                        result.value.upper()
                        if result.value == 'Failure'
                        else result.value
                    )
                }
            )
        return str(tbl)
