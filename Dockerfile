FROM python:2
ADD . /putio-sync
WORKDIR /putio-sync
RUN python setup.py install
CMD ["putiosync"]