import os,redis
from fastapi import APIRouter,Depends
from sqlalchemy import select
from .db import db_session
from .auth import current,writers
from .schemas import ProofInput
from .resample_models import ResampleChain
from .services import pack
from . import resample_service
router=APIRouter();queue=redis.Redis.from_url(os.environ['REDIS_URL'],decode_responses=True)
@router.get('/resample-chains')
def chains(s=Depends(db_session),u=Depends(current)):
    return [pack(x)for x in s.scalars(select(ResampleChain).order_by(ResampleChain.id.desc()))]
@router.post('/resample-chains/{key}/resample')
def resample(key:int,p:ProofInput,s=Depends(db_session),u=Depends(writers)):
    return pack(resample_service.request_resample(s,key,p,u,queue))
