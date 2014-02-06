import flask
import flask.ext.restless
from flask.ext.restless import APIManager
from putiosync.core import DATABASE_FILE
from putiosync.dbmodel import DownloadRecord, DBModelBase
from flask import render_template
from sqlalchemy import desc, func
from flask_sqlalchemy import SQLAlchemy, BaseQuery, _QueryProperty

RECORDS_PER_PAGE = 50


class WebInterface(object):
    def __init__(self, db_session):
        self.app = flask.Flask(__name__)
        self.app.config['DEBUG'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///{}".format(DATABASE_FILE)
        self.db = SQLAlchemy(self.app)
        self.db.Model = DBModelBase
        self.db.Model.query_class = BaseQuery
        self.db.Model.query = _QueryProperty(self.db)
        self.db_session = db_session
        self.api_manager = APIManager(self.app, session=self.db_session)

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
        downloads = (DownloadRecord.query
                     .order_by(desc(DownloadRecord.id)))
        total_downloaded = self.db.session.query(func.sum(DownloadRecord.size)).scalar()
        print total_downloaded
        return render_template("history.html",
                               total_downloaded=total_downloaded,
                               history=downloads.paginate(page, per_page=100))

    def run(self):
        self.app.run()
