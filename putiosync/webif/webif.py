import logging
from math import ceil
import datetime

import flask
import flask.ext.restless
from flask.ext.restless import APIManager
from putiosync.dbmodel import DownloadRecord
from flask import render_template
from putiosync.webif.transmissionrpc import TransmissionRPCServer
from sqlalchemy import desc, func

class Pagination(object):
    # NOTE: pagination is a feature that is included with flask-sqlalchemy, but after
    #   working with it initially, it was far too hacky to use this in combination
    #   with a model that wasn't declared with the flask-sqlalchemy meta base.  Since
    #   I did not and do not want to do that, this exists.

    def __init__(self, query, page, per_page):
        self.query = query
        self.page = page
        self.per_page = per_page
        self.total_count = query.count()

    @property
    def items(self):
        return self.query.offset((self.page - 1) * self.per_page).limit(self.per_page).all()

    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if (num <= left_edge or
                    (self.page - left_current - 1 < num < self.page + right_current) or
                        num > self.pages - right_edge):
                if last + 1 != num:
                    yield None
                yield num
                last = num


class DownloadRateTracker(object):
    def __init__(self):
        self._current_download = None
        self._current_download_last_downloaded = 0
        self._last_sample_datetime = None
        self._bps_this_sample = 0

    def get_bps(self):
        return self._bps_this_sample

    def update_progress(self, download):
        current_sample_datetime = datetime.datetime.now()
        bytes_this_sample = 0
        if download is None:
            self._current_download = None
            self._bps_this_sample = 0
            self._last_sample_datetime = current_sample_datetime
            return

        if self._current_download != download:
            if self._current_download is not None:
                # record remaininng progress from the previous download
                bytes_this_sample += self._current_download.get_size() - self._current_download_last_downloaded
            self._current_download = download
            self._current_download_last_downloaded = 0
            self._last_sample_datetime = current_sample_datetime

        bytes_this_sample += download.get_downloaded() - self._current_download_last_downloaded
        time_delta = current_sample_datetime - self._last_sample_datetime
        if bytes_this_sample == 0 or time_delta <= datetime.timedelta(seconds=0):
            self._bps_this_sample = 0
        else:
            self._bps_this_sample = float(bytes_this_sample) / time_delta.total_seconds()
        self._current_download = download
        self._current_download_last_downloaded = download.get_downloaded()
        self._last_sample_datetime = current_sample_datetime


class WebInterface(object):
    def __init__(self, db_manager, download_manager, putio_client, synchronizer, launch_browser=False, host="0.0.0.0",
                 port=7001):
        self.app = flask.Flask(__name__)
        self.synchronizer = synchronizer
        self.db_manager = db_manager
        self.api_manager = APIManager(self.app, session=self.db_manager.get_db_session())
        self.download_manager = download_manager
        self.putio_client = putio_client
        self.transmission_rpc_server = TransmissionRPCServer(putio_client, self.synchronizer)
        self.launch_browser = launch_browser
        self._host = host
        self._port = port
        self._rate_tracker = DownloadRateTracker()

        self.app.logger.setLevel(logging.WARNING)

        def include_datetime(result):
            print(result)

        self.download_record_blueprint = self.api_manager.create_api(
            DownloadRecord,
            methods=['GET'],
            postprocessors={
                "GET_MANY": [include_datetime]
            })

        # filters
        self.app.jinja_env.filters["prettysize"] = self._pretty_size

        # urls
        self.app.add_url_rule("/", view_func=self._view_active)
        self.app.add_url_rule("/active", view_func=self._view_active)
        self.app.add_url_rule("/history", view_func=self._view_history)
        self.app.add_url_rule("/download_queue", view_func=self._view_download_queue)
        self.app.add_url_rule("/history/page/<int:page>", view_func=self._view_history)
        self.app.add_url_rule("/transmission/rpc", methods=['POST', 'GET', ],
                              view_func=self.transmission_rpc_server.handle_request)

    def _pretty_size(self, size):
        if size > 1024 * 1024 * 1024:
            return "%0.2f GB" % (size / 1024. / 1024 / 1024)
        elif size > 1024 * 1024:
            return "%0.2f MB" % (size / 1024. / 1024)
        elif size > 1024:
            return "%0.2f KB" % (size / 1024.)
        else:
            return "%s B" % size

    def _view_active(self):
        return render_template("active.html")

    def _view_download_queue(self):
        downloads = self.download_manager.get_downloads()
        try:
            if downloads[0].get_downloaded() > 0:
                self._rate_tracker.update_progress(downloads[0])
        except IndexError:
            self._rate_tracker.update_progress(None)

        queued_downloads = []
        for download in downloads:
            queued_downloads.append(
                {
                    "name": download.get_putio_file().name,
                    "size": download.get_size(),
                    "downloaded": download.get_downloaded(),
                    "start_datetime": download.get_start_datetime(),
                    "end_datetime": download.get_finish_datetime(),
                }
            )

        recent_completed = []
        for record in self.db_manager.get_db_session().query(DownloadRecord).order_by(desc(DownloadRecord.id)).limit(
                20):
            recent_completed.append(
                {
                    "id": record.id,
                    "name": record.name,
                    "size": record.size,
                }
            )

        download_queue = {
            "current_datetime": datetime.datetime.now(),  # use as basis for other calculations
            "bps": self._rate_tracker.get_bps(),
            "downloads": queued_downloads,
            "recent": recent_completed
        }
        return flask.jsonify(download_queue)

    def _view_history(self, page=1):
        session = self.db_manager.get_db_session()
        downloads = session.query(DownloadRecord).order_by(desc(DownloadRecord.id))
        total_downloaded = session.query(func.sum(DownloadRecord.size)).scalar()
        return render_template("history.html",
                               total_downloaded=total_downloaded,
                               history=Pagination(downloads, page, per_page=100))

    def run(self):
        if self.launch_browser:
            import webbrowser
            webbrowser.open("http://localhost:{}/".format(self._port))
        self.app.run(self._host, self._port)
