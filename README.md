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

Many applications like this one require you to register a new "app" just
to run some script on your PC.  This is pretty annoying, so we run a
small app on the web that on request (from this app) will follow
the "web server application" flow described  in the put.io api docs at
https://put.io/v2/docs/gettingstarted.html#obtain-an-access-token

If there is not already an access token stored on this PC, the following
will occur:

1. Web browser will be opened put.io to authenticate
2. Web browser will redirect back to a simple web application running on
   at paulosborne.org (my domain).
3. Server will request access token from put.io
4. Web page will display token that user will enter at the command-line
   prompt.

The source for the server (with a few details removed) is also available
in this codebase.  You are welcome to run your own server.

Contributing Back
-----------------

* Found a bug? Create an issue on github.
* Fixed a bug or added a feature?  Fork the project on github and
  submit a pull request
