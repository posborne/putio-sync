putio-sync
==========

Script for automatically downloading files from put.io

Getting Started
---------------

There are a few requirements that can be installed via pip.  I
recommend doing the following to install the requirements in a
controlled fashion:

    $ cd putio-sync
    $ virtualenv env
    $ source env/bin/activate
    $ pip install -r requirements.txt
    $ ./putiosync.py -h
    ...

Authentication
--------------

The first time you run the application, a webbrowser will be opened to
put.io asking for permissions.  If authorized, you'll get your access
token which you will enter into the application.

Contributing Back
-----------------

* Found a bug? Create an issue on github.
* Fixed a bug or added a feature?  Fork the project on github and
  submit a pull request
