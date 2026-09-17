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
$ dnf -y install python3-pip python3-jinja2 python3-PyYAML python3-rpm python3-pytest python3-pytest-cov sudo rpm-sign rpmlint openssh-clients genisoimage qemu qemu-user qemu-img qemu-virtiofsd mock createrepo_c python3-yaml python3-xmltodict python3-boto3 pylint podman bats
$ dnf -y install dnf-plugins-core || dnf -y install dnf5-plugins
```

### Linting

Run this command for static source code linting:

```sh
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

## Formatting

Python code is formatted with [Ruff](https://docs.astral.sh/ruff/). Install it
with either:

```sh
$ pip install ruff
$ uv tool install ruff
```

Format and sort imports manually with:

```sh
$ ruff check --fix lib tests && ruff format lib tests
```

[prek](https://prek.j178.dev/) runs Ruff plus generic file checks (trailing
whitespace, end-of-file newlines, YAML/TOML syntax, merge-conflict markers,
LF line endings) as a git commit hook and in CI on every push and pull
request to `master`. Install it with either:

```sh
$ pip install prek
$ uv tool install prek
```

Then enable the commit hook:

```sh
$ prek install
```

Or run all hooks on the whole tree with:

```sh
$ prek run --all-files
```
