from sqlalchemy import Integer, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base

DBModelBase = declarative_base()


class DownloadRecord(DBModelBase):
    __tablename__ = 'download_history'
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, unique=True)
    size = Column(Integer)
    timestamp = DateTime()
    name = Column(String)
