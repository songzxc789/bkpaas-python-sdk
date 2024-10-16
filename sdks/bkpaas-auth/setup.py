# -*- coding: utf-8 -*-

# DO NOT EDIT THIS FILE!
# This file has been autogenerated by dephell <3
# https://github.com/dephell/dephell

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


import os.path

readme = ''
here = os.path.abspath(os.path.dirname(__file__))
readme_path = os.path.join(here, 'README.rst')
if os.path.exists(readme_path):
    with open(readme_path, 'rb') as stream:
        readme = stream.read().decode('utf8')


setup(
    long_description=readme,
    name='bkpaas-auth',
    version='3.0.0',
    description='User authentication django app for blueking internal projects',
    python_requires='<4.0,>=3.8',
    author='blueking',
    author_email='blueking@tencent.com',
    license='Apach License 2.0',
    packages=['bkpaas_auth', 'bkpaas_auth.core'],
    package_dir={"": "."},
    package_data={},
    install_requires=['django<5.0,>=4.2', 'requests', 'six'],
    extras_require={
        "dev": [
            "flake8==3.*,>=3.8.4",
            "mock==4.*,>=4.0.2",
            "mypy==0.*,>=0.942.0",
            "pytest==6.*,>=6.2.5",
            "pytest-django==3.*,>=3.8.0",
            "pytest-mock==3.*,>=3.4.0",
            "rope==0.*,>=0.18.0",
            "types-mock==4.*,>=4.0.13",
            "types-requests==2.*,>=2.27.16",
            "types-six==1.*,>=1.16.12",
        ]
    },
)
