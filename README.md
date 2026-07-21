# Rift

Rift is a tool to manage RPM packages development effectively during their
complete lifecycle. It provides commands to perform the following actions:

- Creating new packages, either from scratch or imported from existing sources.
- Maintain and updates packages.
- Launch and report automatic advanced integration and functional tests.

The tests are performed in virtual machines for more isolation and provide more
flexibility in the tests environments.

## Tests

### Prerequisites

We recommend the use of [Fedora](https://fedoraproject.org) as development
environment.

Install Rift and the dependencies shared by linting, unit, and functional tests:

```sh
$ dnf -y install python3-pip python3-jinja2 python3-PyYAML python3-rpm python3-dnf python3-yaml python3-pytest python3-pytest-cov python3-boto3 sudo rpm-sign rpmlint openssh-clients genisoimage qemu qemu-user qemu-img qemu-virtiofsd mock createrepo_c podman bats
$ pip install -e .
```

### Linting

Install pylint and its extra dependencies, then run:

```sh
$ dnf -y install pylint python3-xmltodict
$ pylint lib/rift
```

### Unit tests

Unit tests live in [`tests/unit/`](tests/unit/).

Run:

```sh
$ pytest
```

Pytest is configured in [pyproject.toml](./pyproject.toml) and in [pytest.ini](pytest.ini) files.

> [!IMPORTANT]
> Unit tests download virtual machine images from the Internet. The unit tests
> use the value of `https_proxy` environment variable as the Rift proxy
> configuration parameter, if this variable is defined in your environment. If
> you do not have direct access to Internet, you must define this environment
> variable with your network's proxy server to run the tests successfully.

### Functional tests

Black-box functional tests for the `rift` CLI. Functional tests live in
[`tests/functional/`](tests/functional/).

Run:

```sh
$ bats tests/functional/
```

Smoke tests need only the `rift` command. Build/publish tests run real `mock`
and `podman` builds on x86_64 and require network access to AlmaLinux repos.
