#
# Copyright (C) 2023 CEA
#

import getpass
from TestUtils import make_temp_dir, RiftTestCase
from rift.Mock import Mock
from rift.Repository import Repository

class MockTest(RiftTestCase):
    """
    Tests class for Mock
    """

    def test_init(self):
        """ Test Mock instanciation """
        mock = Mock(config=[], proj_vers=1.0)
        self.assertEqual(mock._mockname, "rift-{}-1.0".format(getpass.getuser()))
        self.assertEqual(mock._config, [])

    def test_build_context(self):
        """ Test mock context generation """
        repolist = []
        arch = 'aarch64'
        _config = {
                'module_hotfixes': True,
                'excludepkgs': 'kernel*',
                }
        repolist.append(Repository('/tmp', arch, name='tmp', config=_config))
        mock = Mock(_config)
        context = mock._build_template_ctx(repolist)
        self.assertEqual(context['name'], 'rift-{}'.format(getpass.getuser()))
        repos_ctx = context['repos'][0]
        self.assertEqual(repos_ctx['name'], 'tmp')
        self.assertEqual(repos_ctx['priority'], 999)
        self.assertEqual(repos_ctx['url'], 'file:///tmp/{}'.format(arch))
        self.assertEqual(repos_ctx['module_hotfixes'], True)
        self.assertEqual(repos_ctx['excludepkgs'], 'kernel*')
