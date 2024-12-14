from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class TaskModel(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    playbook_path = Column(String, nullable=False)
    inventory = Column(String, nullable=False)
    run_time = Column(DateTime, nullable=False)


DATABASE_URL = "postgresql://user123:password@db:5432/tasksdb"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)
