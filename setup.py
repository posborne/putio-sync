from setuptools import setup
import putiosync

__author__ = 'Paul Osborne'


def get_requirements():
    reqs = []
    for line in open('requirements.txt').readlines():
        if line and not line.startswith('#'):
            reqs.append(line)
    return reqs


setup(
    name='putiosync',
    version=putiosync.__version__,
    description='Automatically download content from put.io',
    long_description=open('README.rst').read(),
    author=putiosync.__author__,
    author_email='osbpau@gmail.com',
    url="http://posborne.github.io/putio-sync/",
    license='MIT',
    packages=['putiosync'],
    entry_points={'console_scripts': ['putiosync=putiosync.frontend:main']},
    install_requires=get_requirements(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Utilities'
    ]
)
