from math import ceil

import flask
import flask.ext.restless
from flask.ext.restless import APIManager
from putiosync.dbmodel import DownloadRecord
from flask import render_template
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
        return self.query.offset((self.page - 1) * self.per_page).all()

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
        for num in xrange(1, self.pages + 1):
            if (num <= left_edge or
                (self.page - left_current - 1 < num < self.page + right_current) or
                num > self.pages - right_edge):
                if last + 1 != num:
                    yield None
                yield num
                last = num


class WebInterface(object):
    def __init__(self, db_manager):
        self.app = flask.Flask(__name__)
        self.db_manager = db_manager
        self.api_manager = APIManager(self.app, session=self.db_manager.get_db_session())

        def include_datetime(result):
            print result

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
        self.app.add_url_rule("/history/page/<int:page>", view_func=self._view_history)

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
        return render_template("index.html")

    def _view_history(self, page=1):
        session = self.db_manager.get_db_session()
        downloads = session.query(DownloadRecord).order_by(desc(DownloadRecord.id))
        total_downloaded = session.query(func.sum(DownloadRecord.size)).scalar()
        return render_template("history.html",
                               total_downloaded=total_downloaded,
                               history=Pagination(downloads, page, per_page=100))

    def run(self):
        self.app.run()
