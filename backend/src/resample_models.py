from sqlalchemy import String,ForeignKey,JSON,UniqueConstraint,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
class ResampleChain(Base):
    """拒判补采承接链：原张拒判后唯一一条承接链，重试不重复建张，普通合格张不能顶替。"""
    __tablename__='resample_chains'
    __table_args__=(UniqueConstraint('original_proof_id'),CheckConstraint("purpose in ('first','sample','recheck') and state in ('waiting','resolved','failed')"))
    id:Mapped[int]=mapped_column(primary_key=True)
    job_id:Mapped[int]=mapped_column(ForeignKey('print_jobs.id'))
    purpose:Mapped[str]=mapped_column(String(24))
    original_proof_id:Mapped[int]=mapped_column(ForeignKey('proof_sheets.id'),unique=True)
    sample_id:Mapped[int|None]=mapped_column(ForeignKey('press_samples.id'),nullable=True)
    hold_id:Mapped[int|None]=mapped_column(ForeignKey('press_holds.id'),nullable=True)
    current_proof_id:Mapped[int|None]=mapped_column(ForeignKey('proof_sheets.id'),nullable=True)
    effective_proof_id:Mapped[int|None]=mapped_column(ForeignKey('proof_sheets.id'),nullable=True)
    resample_proof_ids:Mapped[list]=mapped_column(JSON,default=list)
    state:Mapped[str]=mapped_column(String(24),default='waiting')
    reject_reason:Mapped[str]=mapped_column(String(600),default='')
    created_at:Mapped[str]=mapped_column(String(40))
    resolved_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    resolution:Mapped[str]=mapped_column(String(300),default='')
    created_by:Mapped[str]=mapped_column(String(100),default='')
