#
# Copyright (C) 2023 CEA
#

from TestUtils import make_temp_dir, RiftTestCase
from rift.Repository import Repository, RemoteRepository
from rift.Config import _DEFAULT_REPO_CMD

class RepositoryTest(RiftTestCase):
    """
    Tests class for Repository
    """

    def test_init(self):
        """ Test Repository instanciation """
        arch = 'x86_64'
        repo_path = '/nowhere'
        repo = Repository(repo_path, arch)

        self.assertEqual(repo.name, repo_path[1:])
        self.assertEqual(repo.path, repo_path)
        self.assertEqual(repo.srpms_dir, '{}/{}'.format(repo_path, 'SRPMS'))
        self.assertEqual(repo.url, 'file://{}/{}'.format(repo_path, arch))
        self.assertEqual(repo.priority, None)
        self.assertEqual(repo.module_hotfixes, None)
        self.assertEqual(repo.excludepkgs, None)
        self.assertEqual(repo.proxy, None)
        self.assertEqual(repo.createrepo, _DEFAULT_REPO_CMD)


    def test_init_with_config(self):
        """ Test Repository instanciation with a specific configuration """
        _config = { 'createrepo': 'mycustom_create_repo' }
        _options = {
                    'module_hotfixes': True,
                    'excludepkgs': 'somepkg',
                    'proxy': 'myproxy',
                   }
        arch = 'x86_64'
        repo_name = 'nowhere'
        repo = Repository('/{}'.format(repo_name),
                          arch,
                          options=_options,
                          config=_config)

        self.assertEqual(repo.name, repo_name)
        self.assertEqual(repo.path, '/{}'.format(repo_name))
        self.assertEqual(repo.srpms_dir, '/{}/{}'.format(repo_name, 'SRPMS'))
        self.assertEqual(repo.url, 'file:///{}/{}'.format(repo_name, arch))
        self.assertEqual(repo.priority, None)
        self.assertEqual(repo.module_hotfixes, True)
        self.assertEqual(repo.excludepkgs, 'somepkg')
        self.assertEqual(repo.proxy, 'myproxy')
        self.assertEqual(repo.createrepo, _config['createrepo'])


class RemoteRepositoryTest(RiftTestCase):
    """
    Tests class for RemoteRepository
    """

    def test_rpms_dir_local_file(self):
        """ test rpms_dir method """
        directory = '/somewhere'
        repo = RemoteRepository(directory)
        self.assertEqual(repo.rpms_dir, directory)

    def test_rpms_dir_local_file_url(self):
        """ test rpms_dir method with a local url"""
        directory = '/somewhere'
        repo =  RemoteRepository('file://{}'.format(directory))
        self.assertEqual(repo.rpms_dir, directory)

    def test_rpms_dir_remote_url(self):
        """ test rpms_dir method with a remote url"""
        directory = '/somewhere'
        repo =  RemoteRepository('http://{}'.format(directory))
        self.assertIsNone(repo.rpms_dir)

    def test_create(self):
        """ test empty method create """
        self.assertIsNone(RemoteRepository('/nowhere').create())
