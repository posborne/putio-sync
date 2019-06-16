FROM python:3
ADD . /putio-sync
WORKDIR /putio-sync
RUN pip install .
# Set environment variable PUTIO_SYNC_ARGS to pass additional arguments
CMD putiosync $PUTIO_SYNC_ARGS /volumes/putio_download
VOLUME "/volumes/putio_download"
# Default http port
EXPOSE 7001/tcp
