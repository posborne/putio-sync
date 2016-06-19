import json
import logging
import uuid
import flask
import os


logger = logging.getLogger(__name__)


def map_status(status):
    return {
        "IN_QUEUE": 3,  # queued
        "DOWNLOADING": 4,  # downloading
        "COMPLETED": 6,  # seeding
    }.get(status, 3)  # default: queued

def geteta(eta):
    if eta is None:
        return 0
    else:
        if eta < 0:
            return 0
        else:
            return eta

class TransmissionTransferProxy(object):
    """Wrap a put.io transfer and map to Transmission torrent iface

    Here's an example of the information we get from Put.io for a transfer:

        {
            "availability": null,
            "callback_url": null,
            "client_ip": null,
            "created_at": "2015-10-13T05:20:22",
            "created_torrent": false,
            "current_ratio": "0.00",
            "down_speed": 0,
            "download_id": 17654355,
            "downloaded": 0,
            "error_message": null,
            "estimated_time": null,
            "extract": false,
            "file_id": 313672617,
            "finished_at": "2015-10-13T05:20:24",
            "id": 30210267,
            "is_private": false,
            "magneturi": "magnet:?xt=urn:btih:9ce5e6fc6aa605287c8e2af20c01c5655ff59074&dn=Fargo+S02E01+720p+HDTV+x264+KILLERS",
            "name": "Fargo S02E01 720p HDTV x264 KILLERS",
            "peers_connected": 0,
            "peers_getting_from_us": 0,
            "peers_sending_to_us": 0,
            "percent_done": 100,
            "save_parent_id": 0,
            "seconds_seeding": 0,
            "size": 935982427,
            "source": "magnet:?xt=urn:btih:9CE5E6FC6AA605287C8E2AF20C01C5655FF59074&dn=Fargo+S02E01+720p+HDTV+x264+KILLERS&tr=udp://tracker.coppersurfer.tk:6969/announce&tr=udp://tracker.leechers-paradise.org:6969&tr=udp://open.demonii.com:1337",
            "status": "COMPLETED",
            "status_message": "Completed 5 days ago.",
            "subscription_id": 4895894,
            "torrent_link": "/v2/transfers/30210267/torrent",
            "tracker_message": null,
            "trackers": null,
            "type": "TORRENT",
            "up_speed": 0,
            "uploaded": 0
        },

    """

    def __init__(self, putio_transfer, synchronizer):
        self.synchronizer = synchronizer
        self.transfer = putio_transfer
        # sonar requests the following:
        # - id
        # - hashString
        # - name
        # - downloadDir
        # - status
        # - totalSize
        # - leftUntilDone
        # - eta
        # - errorString
        self._field_providers = {
            "id": lambda: self.transfer.id,
            "hashString": lambda: "%s" % self.transfer.id,
            "name": lambda: self.transfer.name,
            "downloadDir": lambda: self.synchronizer.get_download_directory(),
            "status": lambda: map_status(self.transfer.status),
            "totalSize": lambda: self.transfer.size,
            "leftUntilDone": lambda: self.transfer.size - self.transfer.downloaded,
            "errorString": lambda : '' if self.transfer.error_message is None else self.transfer.error_message,
            "isFinished": lambda : self.synchronizer.is_already_downloaded(self.transfer),
            "eta": lambda : geteta(self.transfer.estimated_time)
        }

    def render_json(self, fields):
        return {f: self._field_providers.get(f, lambda: None)() for f in fields}


class TransmissionRPCServer(object):
    """Expose a JSON-RPC interface attempting to match Transmission

    This API interface is documented at
    https://trac.transmissionbt.com/browser/trunk/extras/rpc-spec.txt.  We attempt
    to match enough so that we can get integration from clients of the transmission
    API (e.g. Sonarr) without having to modify those pieces of software directly.

    The implementation is (and probably always will be) partial and your results
    may vary from client to client depending on how much, how little they expect
    to have implemented.
    """

    def __init__(self, putio_client, synchronizer):
        self._synchronizer = synchronizer
        self._putio_client = putio_client
        self._session_id = str(uuid.uuid1())
        self.methods = {
            "session-get": self._session_get,
            "session-stats": self._session_stats,
            "torrent-get": self._torrent_get,
            "torrent-add": self._torrent_add,
            "torrent-set": self._torrent_set,
            "torrent-remove": self._torrent_remove,
        }

    def _session_get(self, **arguments):
        # Many more are supported by real client, this is enough for Sonarr
        return {
            "rpc-version": 15,
            "version": "2.84 (putiosync)",
            "download-dir": self._synchronizer.get_download_directory()
        }

    def _session_stats(self, **arguments):
        return {}

    def _torrent_add(self, filename, **arguments):
        if os.path.isfile(filename):
            self._putio_client.Transfer.add_torrent(filename)
        else:
            self._putio_client.Transfer.add_url(filename)
        return {}

    def _torrent_remove(self, ids, **arguments):
        for id in ids:
            file = self._putio_client.File.get(id)
            file.delete()
        return {}

    def _torrent_set(self, **arguments):
        return {}

    def _torrent_get(self, fields, **arguments):
        transfers = self._putio_client.Transfer.list()
        transmission_transfers = [TransmissionTransferProxy(t, self._synchronizer) for t in transfers]
        return {"torrents": [t.render_json(fields) for t in transmission_transfers]}

    def handle_request(self):
        # If GET, just provide X-Transmission-Session-Id with HTTP 409
        if flask.request.method == "GET":
            res = flask.make_response("Session ID: %s" % self._session_id)
            res.headers['X-Transmission-Session-Id'] = self._session_id
            return res, 409
        else:
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
            res.headers['X-Transmission-Session-Id'] = self._session_id
            return res
