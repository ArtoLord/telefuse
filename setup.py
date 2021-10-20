import setuptools
import os

with open('requirements.txt') as f:
    required = f.read().splitlines()

setuptools.setup(
    name="telefs",
    version="0.0.3",
    description="Console utility to work with telegram fs",
    author="ArtoLord",
    author_email="artolord@yandex.com",
    python_requires='>=3.10',
    entry_points='''
        [console_scripts]
        telefs=telefuse.main:main
    ''',
    install_reqs = required,
    packages=setuptools.find_packages()
)