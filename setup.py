import setuptools

setuptools.setup(
    name="telefs",
    version="0.0.1",
    description="Console utility to work with telegram fs",
    author="ArtoLord",
    author_email="artolord@yandex.com",
    python_requires='>=3.10',
    entry_points='''
        [console_scripts]
        telefs=telefuse.main:main
    ''',
    packages=setuptools.find_packages()
)