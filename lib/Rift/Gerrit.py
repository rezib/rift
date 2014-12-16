#
# Copyright (C) 2014 CEA
#

"""
Helper to push REST review to Gerrit Code Reviewer server.
"""

import json
import logging
import urllib2

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
            'line': line,
            'message': msg,
        }
        self.comments.setdefault(filepath, []).append(comment)

    def _message(self):
        stats = ((cnt, self.labels[code]) for code, cnt in self.stats.items())
        msg = ", ".join("%d %s(s)" % (cnt, label) for cnt, label in stats)
        return "%s: %s" % (self.msg_header, msg)

    def invalidate(self):
        self.validated = False

    def push(self, config, changeid, revid):
        """Send REST request to Gerrit server from config"""

        realm = config.get('gerrit_realm', 'Gerrit Code Review')
        server = config.get('gerrit_server', 'ci-gerrit.vm.c-aury.ocre.cea.fr:8080')
        username = config.get('gerrit_username', 'linter')
        password = config.get('gerrit_password', 'NbH9ddVyLudz')

        authhandler = urllib2.HTTPDigestAuthHandler()
        authhandler.add_password(realm, server, username, password)
        opener = urllib2.build_opener(authhandler)

        urllib2.install_opener(opener)

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

        req = urllib2.Request(api_url, data,
                              {'Content-Type': 'application/json'})
        req.get_method = lambda: 'POST'
        urllib2.urlopen(req).read()
