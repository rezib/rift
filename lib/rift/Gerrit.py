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
Helper to push REST review to Gerrit Code Reviewer server.
"""

import json
import logging
try:
    import urllib2 as urllib
except ImportError:
    import urllib.request as urllib

from rift import RiftError

class Review(object):
    """Gerrit review."""

    def __init__(self):
        self.labels = {'W': 'warning', 'E': 'error'}
        self.stats = {'E': 0}
        self.msg_header = 'Rift review'
        self.comments = {}
        self.validated = True

    def add_comment(self, filepath, line, label, message):
        self.stats.setdefault(label, 0)
        self.stats[label] += 1

        msg = "(%s) %s" % (self.labels[label], message)
        comment = {
            'message': msg,
        }
        if line is not None:
            comment['line'] = line
        self.comments.setdefault(filepath, []).append(comment)

    def _message(self):
        stats = ((cnt, self.labels[code]) for code, cnt in self.stats.items())
        msg = ", ".join("%d %s(s)" % (cnt, label) for cnt, label in stats)
        return "%s: %s" % (self.msg_header, msg)

    def invalidate(self):
        self.validated = False

    def push(self, config, changeid, revid):
        """Send REST request to Gerrit server from config"""

        realm = config.get('gerrit_realm')
        server = config.get('gerrit_server')
        username = config.get('gerrit_username')
        password = config.get('gerrit_password')

        if realm is None:
            raise RiftError("Gerrit realm is not defined")
        if server is None:
            raise RiftError("Gerrit server is not defined")
        if username is None:
            raise RiftError("Gerrit username is not defined")
        if password is None:
            raise RiftError("Gerrit password is not defined")

        authhandler = urllib.HTTPDigestAuthHandler()
        authhandler.add_password(realm, server, username, password)
        opener = urllib.build_opener(authhandler)

        urllib.install_opener(opener)

        api_url = "http://%s/gerrit/a/changes/%s/revisions/%s/review" % \
                                                      (server, changeid, revid)
        # Create request data structure
        request = {
            "message": self._message(),
            "comments": self.comments,
        }
        if self.validated:
            request['labels'] = {"Code-Review": '+1'}
        data = json.dumps(request, indent=2)


        logging.debug("Sending review request to %s", api_url)
        logging.debug("Request content: %s", data)

        req = urllib.Request(api_url, data,
                              {'Content-Type': 'application/json'})
        req.get_method = lambda: 'POST'
        urllib.urlopen(req).read()
