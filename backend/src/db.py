import os
from sqlalchemy import create_engine,inspect,text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True,isolation_level="READ COMMITTED")
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
def db_session():
    with Session() as s:
        yield s
def ensure_columns():
    """create_all只建新表，不补旧表列；对既有proof_sheets幂等补挂承接链外键列。"""
    insp=inspect(engine)
    if 'proof_sheets' not in insp.get_table_names():return
    cols={c['name']for c in insp.get_columns('proof_sheets')}
    if 'chain_id' not in cols:
        with engine.begin()as conn:conn.execute(text('ALTER TABLE proof_sheets ADD COLUMN chain_id INTEGER NULL'))
