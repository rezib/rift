#
# Copyright (C) 2014 CEA
#

class TestResults(object):

    def __init__(self):
        self.results = {}
        self.global_result = True

    def add_failure(self, name):
        self._add_result(name, 'Failure')
        self.global_result = False

    def add_success(self, name):
        self._add_result(name, 'Success')

    def _add_result(self, name, result):
        self.results[name] = result
