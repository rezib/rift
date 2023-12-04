# Rift

Rift is a tool to manage RPM packages development effectively during their
complete lifecycle. It provides commands to perform the following actions:

- Creating new packages, either from scratch or imported from existing sources.
- Maintain and updates packages.
- Launch and report automatic advanced integration and functional tests.

The tests are performed in virtual machines for more isolation and provide more
flexibility in the tests environments.

## Tests

To run the unit tests and static analysis, some dependencies are required:

```sh
sudo -n dnf -y install rpmlint rpm-python3 python3-pylint python3-jinja2 \
    python3-nose platform-python-coverage python3-PyYAML python3-rpm
```

Run this command for static source code linting:


```sh
$ pylint-3 '--good-names=i,j,k,ex,Run,_,rc,vm' -d E1101 -d W0511 \
    --msg-template="$msg_template" lib/rift
```

Run this command to run unit tests:

```sh
$ export PYTHONPATH=$PWD/lib
$ nosetests-3.6 -vs --all-modules --with-xunit --with-coverage \
    --cover-package=rift --cover-xml tests
```
