import flask
import flask.ext.sqlalchemy
import flask.ext.restless
from flask.ext.restless import APIManager
from putiosync.dbmodel import DownloadRecord
from flask import render_template


class WebInterface(object):

    def __init__(self, db_session):
        self.app = flask.Flask(__name__)
        self.app.config['DEBUG'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
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

        # urls
        self.app.add_url_rule("/", view_func=self._view_active)
        self.app.add_url_rule("/active", view_func=self._view_active)
        self.app.add_url_rule("/history", view_func=self._view_history)

    def _view_active(self):
        return render_template("index.html")

    def _view_history(self):
        return render_template("history.html")

    def run(self):
        self.app.run()
