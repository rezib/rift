%global foo 1.%{bar}
%define bar 1

Name:           pkg
Version:        1.0
Release:        1
Summary:        A package
Group:          System Environment/Base
License:        GPL
URL:            http://nowhere.com/projects/%{name}/
Source0:        https://nowhere.com/sources/%{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       another-package

Provides:       pkg-provide

%description
A package

%prep

%build
# Nothing to build

%install
# Nothing to install

%files

# No files

%changelog
* Tue Feb 26 2019 Myself <buddy@somewhere.org> 1.0-1
- Update to 1.0 release
