#
# Copyright (C) 2023 CEA
#

from TestUtils import make_temp_dir, RiftTestCase
from rift.Repository import Repository, RemoteRepository, ProjectArchRepositories
from rift.Config import _DEFAULT_REPO_CMD, Config

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


class ProjectArchRepositoriesTest(RiftTestCase):
    """
    Tests class for ProjectArchRepositories
    """
    def setUp(self):
        self.config = Config()

    def test_basic(self):
        """Test one simple supplementary repository"""
        self.config.options['repos'] = {
            'os': {
                'url': 'file:///rift/packages/x86_64/os',
                'priority': 90,
            }
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(repos.working, None)
        self.assertEqual(len(repos.supplementaries), 1)
        self.assertEqual(len(repos.all), 1)
        self.assertEqual(repos.supplementaries[0].name, 'os')
        self.assertEqual(repos.all[0], repos.supplementaries[0])

    def test_working(self):
        """Test working repository without supplementary repository"""
        self.config.options['working_repo'] = '/tmp/repo'
        self.config.options['repos'] = {}
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertIsInstance(repos.working, Repository)
        self.assertEqual(len(repos.supplementaries), 0)
        self.assertEqual(len(repos.all), 1)
        self.assertEqual(repos.working.name, 'working')
        self.assertEqual(repos.working.path, '/tmp/repo')
        self.assertEqual(repos.all[0], repos.working)

    def test_working_and_supplementaries(self):
        """Test working repository and two supplementary repositories"""
        self.config.options['working_repo'] = '/tmp/repo'
        self.config.options['repos'] = {
            'os': {
                'url': 'file:///rift/packages/x86_64/os',
                'priority': 90,
            },
            'extra': {
                'url': 'file:///rift/packages/x86_64/extra',
                'priority': 90,
            },
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertIsInstance(repos.working, Repository)
        self.assertEqual(len(repos.supplementaries), 2)
        self.assertEqual(len(repos.all), 3)
        self.assertEqual(repos.working.name, 'working')
        self.assertEqual(repos.supplementaries[0].name, 'os')
        self.assertEqual(repos.all[0], repos.working)
        self.assertEqual(repos.all[1], repos.supplementaries[0])

    def test_can_publish(self):
        """Test ProjectArchRepositories.can_publish() method"""
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertFalse(repos.can_publish(), False)
        self.config.options['working_repo'] = '/tmp/repo'
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertTrue(repos.can_publish(), False)

    def test_working_with_arch(self):
        """Test working repo with $arch placeholder and arch specific value"""
        self.config.options['working_repo'] = '/tmp/repo/$arch'
        self.config.options['repos'] = {}
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertIsInstance(repos.working, Repository)
        self.assertEqual(repos.working.name, 'working')
        self.assertEqual(repos.working.path, '/tmp/repo/x86_64')

        # If an arch specific working_repo parameter is defined in
        # configuration, it should override generic working_repo parameter for
        # this arch.

        self.config.options['x86_64'] = { 'working_repo': '/tmp/other/repo'}
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(repos.working.path, '/tmp/other/repo')

    def test_supplementaries_with_arch(self):
        """Test supplementary with $arch placeholder and arch specific value"""
        self.config.options['repos'] = {
            'os': {
                'url': 'file:///rift/packages/$arch/os',
                'priority': 90,
            },
            'extra': {
                'url': 'file:///rift/packages/$arch/extra',
                'priority': 90,
            },
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(repos.supplementaries[0].name, 'os')
        self.assertEqual(
            repos.supplementaries[0].url,
            'file:///rift/packages/x86_64/os'
        )
        self.assertEqual(repos.supplementaries[1].name, 'extra')
        self.assertEqual(
            repos.supplementaries[1].url,
            'file:///rift/packages/x86_64/extra'
        )

        # Add architecture specific repos
        self.config.options['x86_64'] = {}
        self.config.options['x86_64']['repos'] = {
            'other-os': {
                'url': 'file:///rift/other/packages/os',
                'priority': 90,
            },
            'other-extra': {
                'url': 'file:///rift/other/packages/extra',
                'priority': 90,
            },
        }
        repos = ProjectArchRepositories(self.config, 'x86_64')
        self.assertEqual(repos.supplementaries[0].name, 'other-os')
        self.assertEqual(
            repos.supplementaries[0].url,
            'file:///rift/other/packages/os'
        )
        self.assertEqual(repos.supplementaries[1].name, 'other-extra')
        self.assertEqual(
            repos.supplementaries[1].url,
            'file:///rift/other/packages/extra'
        )
