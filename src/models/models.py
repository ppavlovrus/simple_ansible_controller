from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class TaskModel(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    playbook_path = Column(String, nullable=False)
    inventory = Column(String, nullable=False)
    run_time = Column(DateTime, nullable=False)
    playbook_content = Column(Text, nullable=True)  # Store generated playbook content
    is_generated = Column(Boolean, default=False)  # Flag for LLM-generated playbooks
    generation_metadata = Column(JSON, nullable=True)  # Store LLM generation details
    safety_validated = Column(Boolean, default=False)  # Safety validation status
    validation_errors = Column(JSON, nullable=True)  # Store validation errors


class PlaybookTemplate(Base):
    __tablename__ = "playbook_templates"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    template_content = Column(Text, nullable=False)
    variables_schema = Column(JSON, nullable=True)  # JSON schema for template variables
    created_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)


DATABASE_URL = "postgresql://user123:password@db:5432/tasksdb"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)
