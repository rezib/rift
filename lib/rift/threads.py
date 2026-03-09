#
# Copyright (C) 2026 CEA
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

import threading
import contextlib
import io

class BuildThreadOutcome:

    def __init__(self):
        self.output = io.StringIO()
        self.results = None

class BuildThread(threading.Thread):

    def __init__(self, target, args, config, arch, pkgs):
        # Initializing the Thread class
        super().__init__(None, target, f"build-{arch}", args=(args, config, arch, pkgs))
        self.outcome = BuildThreadOutcome()

    # Overriding the Thread.run function
    def run(self):
        if self._target is not None:
            with contextlib.redirect_stderr(self.outcome.output):
                with contextlib.redirect_stdout(self.outcome.output):
                    self.output.results = self._target(*self._args, **self._kwargs)

    def join(self):
        super().join()
        return self.outcome
