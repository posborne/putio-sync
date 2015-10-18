import json
import logging
import flask
import os

logger = logging.getLogger(__name__)


class TransmissionRPCServer(object):

    def __init__(self, putio_client):
        self._putio_client = putio_client
        self.methods = {
            "session-get": self._session_get,
            "torrent-get": self._torrent_get,
            "torrent-add": self._torrent_add,
        }

    def _session_get(self):
        # Many more are supported by real client, this is enough for Sonarr
        return {
            "rpc-version": 15,
            "version": "2.84 (putiosync)",
        }

    def _torrent_add(self, filename):
        if os.path.isfile(filename):
            self._putio_client.Transfer.add_torrent(filename)
        else:
            self._putio_client.Transfer.add_url(filename)
        return {}

    def _torrent_get(self, fields):
        return {"torrents": []}

    def handle_request(self):
        data = json.loads(flask.request.data)
        method = data['method']
        arguments = data.get('arguments', {})
        tag = data.get('tag')
        logger.info("Method: %r, Arguments: %r", method, arguments)
        logger.info("%r", flask.request.headers)
        try:
            result = self.methods[method](**arguments)
        except Exception, e:
            response = {
                "result": "error",
                "error_description": "%s" % e,
            }
        else:
            response = {
                "result": "success",
                "arguments": result,
            }

        if tag:
            response["tag"] = tag

        res = flask.make_response(json.dumps(response))
        res.headers['X-Transmission-Session-Id'] = '1234'  # TODO: X-Transmission-Session-Id
        return res
