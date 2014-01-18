from setuptools import setup
import putiosync

__author__ = 'Paul Osborne'

setup(
    name='putiosync',
    version=putiosync.__version__,
    description='Automatically download content from put.io',
    long_description=open('README.rst').read(),
    author=putiosync.__author__,
    license='MIT',
    packages=['putiosync'],
    entry_points={'console_scripts': ['putiosync=putiosync.frontend:main']},
    install_requires=[
        'requests==2.2.0',
        'progressbar==2.2',
        'putio.py==2.1.0'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Operation System :: Microsoft :: Windows',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Utilities'
    ]
)
