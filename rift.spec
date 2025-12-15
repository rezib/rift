%{?python_enable_dependency_generator}

Name:           rift
Version:        0.12
Release:        1%{?dist}

License:        CeCILL-C
Source:         https://github.com/cea-hpc/rift/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz
URL:            https://github.com/cea-hpc/rift

BuildRequires:  python3-devel
Summary:        Tool to build and maintain your own RPM based repository
BuildArch:      noarch

%description
Rift is a tool to manage RPM packages development effectively during their
complete lifecycle. It provides commands to perform the following actions:

* Creating new packages, either from scratch or imported from existing sources.
* Maintain and updates packages.
*Launch and report automatic advanced integration and functional tests.

The tests are performed in virtual machines for more isolation and provide more
flexibility in the tests environments.

%prep
%autosetup -n rift

%build
%py3_build

%install
%py3_install

%files
%license Licence_CeCILL-C_V1-en.txt
%doc README.md
%doc AUTHORS
%doc Changelog
%{_bindir}/rift
%{python3_sitelib}/
%{_datadir}/%{name}

%changelog
* Mon Dec 15 2025 Rémi Palancher <remi@rackslab.io> - 0.12-1
- Initial package
