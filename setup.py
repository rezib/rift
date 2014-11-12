#!/usr/bin/env python
#
# Copyright (C) 2014 CEA
#

from distutils.core import setup

setup(name='rift',
      version='0.1',
      license='GPL',
      description='RPM repository management',
      author='Aurelien Degremont',
      author_email='aurelien.degremont@cea.fr',
      package_dir={'': 'lib'},
      packages=['Rift'],
      data_files=[('/usr/bin', ['scripts/rift']),
                  ('/usr/share/rift/template', ['template/project.conf', 'template/mock.tpl']),
                  ('/usr/share/rift/template/packages', ['template/packages/modules.yaml', 'template/packages/staff.yaml']),
                  ],
     )

