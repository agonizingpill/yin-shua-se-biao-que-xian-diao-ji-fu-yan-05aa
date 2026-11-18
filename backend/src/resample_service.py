from sqlalchemy import select
from fastapi import HTTPException
from .models import PrintJob,ProofSheet,Audit
from .production_models import PressSample,PressHold
from .resample_models import ResampleChain
from .constants import CHAIN_WAITING
from .services import get,audit,now
from .paper_service import locked

def open_chain_for(s,proof_id):
    return s.scalar(select(ResampleChain).where(ResampleChain.state==CHAIN_WAITING,ResampleChain.original_proof_id==proof_id).with_for_update())
def job_open_chain(s,job_id,purpose=None):
    q=select(ResampleChain).where(ResampleChain.state==CHAIN_WAITING,ResampleChain.job_id==job_id)
    if purpose:q=q.where(ResampleChain.purpose==purpose)
    return s.scalar(q.order_by(ResampleChain.id.desc()).with_for_update())
def guard(s,job_id):
    """首张/抽检/停机复验/封箱发货前统一拦截：存在等待补采承接链即等待，不按合格或已知缺陷放行。"""
    chain=job_open_chain(s,job_id)
    if chain:
        p=get(s,ProofSheet,chain.original_proof_id)
        raise HTTPException(409,f'色标{p.code}拒判待补采（{chain.purpose}用途承接链#{chain.id}），须补采有效判读后再操作')

def _queue(s,proof,r):
    s.commit()
    try:r.rpush('press-classify',proof.id)
    except Exception:
        proof.classification_state='failed';proof.evidence={'error':'判读队列暂不可用'};s.commit();raise HTTPException(503,'判读队列暂不可用，已保留待处置记录')

def create_chain(s,proof,purpose,u=None,sample_id=None,hold_id=None):
    if open_chain_for(s,proof.id):raise HTTPException(409,'该拒判张已有承接链，并发补采只认一条承接链')
    reasons=proof.evidence.get('rejection_reasons')if proof.evidence else None
    chain=ResampleChain(job_id=proof.job_id,purpose=purpose,original_proof_id=proof.id,
        sample_id=sample_id,hold_id=hold_id,reject_reason='；'.join(reasons or ['判读证据未记录具体拒判依据']),
        state=CHAIN_WAITING,created_at=now(),created_by=u.email if u else 'worker')
    s.add(chain);s.flush();proof.chain_id=chain.id
    if u:audit(s,u,f'拒判建承接链#{chain.id} 用途{purpose} 原张{proof.code}')
    return chain

def request_resample(s,key,p,u,r):
    """补采统一入口：关联原张及同一用途，原证据保留，普通合格张不能顶替；重试不重复建张。"""
    chain=locked(s,ResampleChain,key)
    if chain.state!=CHAIN_WAITING:raise HTTPException(409,'承接链已闭合，不能继续补采；请重新走判读流程')
    if p.job_id!=chain.job_id:raise HTTPException(409,'补采色标必须与原张同一工单同一用途')
    if s.scalar(select(ProofSheet.id).where(ProofSheet.code==p.code)):raise HTTPException(409,'色标编号已存在，补采重试不重复建张，请使用新编号或查看承接进度')
    original=get(s,ProofSheet,chain.original_proof_id)
    if original.classification_state!='rejected':raise HTTPException(409,'原张不是拒判状态，承接链数据异常')
    proof=ProofSheet(**p.model_dump(),classification_state='classifying',chain_id=chain.id)
    s.add(proof);s.flush()
    chain.current_proof_id=proof.id;chain.resample_proof_ids=[*(chain.resample_proof_ids or []),proof.id]
    audit(s,u,f'拒判补采 承接链#{chain.id} 用途{chain.purpose} 原张{original.code} 新色标{proof.code}')
    _queue(s,proof,r);return chain

def _resolve(s,chain,proof,note):
    chain.effective_proof_id=proof.id;chain.state='resolved';chain.resolved_at=now();chain.resolution=note

def handle_result(s,proof):
    """worker判读落库后统一收口：补采张按承接链处理；非承接张（首张/抽检/停机复验）拒判则建链。"""
    chain=s.get(ResampleChain,proof.chain_id)if proof.chain_id else None
    rejected=proof.classification_state=='rejected'
    failed=proof.classification_state=='failed'
    # 1) 承接链上的补采张
    if chain:
        s.refresh(chain,with_for_update=True)
        # 迟回原张判读不解除拦截：链已闭合后的迟到结果只保留本张证据，不再产生链副作用
        if chain.state!=CHAIN_WAITING:return {'chain':'stale','state':chain.state}
        if failed:
            # 判读失败（队列/worker异常）不是拒判：承接链保持等待，失败张证据保留，操作员用新编号重试，不重复建张
            s.add(Audit(actor='worker',action=f'承接链#{chain.id}补采{proof.code}判读失败，等待重试补采',stamp=now()))
            return {'chain':'waiting_failed'}
        if rejected:
            # 再次拒判：承接链保持等待，指针指向最新补采张，原张及历次证据保留
            s.add(Audit(actor='worker',action=f'承接链#{chain.id}补采{proof.code}仍拒判，继续等待补采',stamp=now()))
            return {'chain':'waiting'}
        # 有效判读：仍沿用训练判别；按结果闭合承接链
        if chain.purpose=='sample':
            item=get(s,PressSample,chain.sample_id)
            _resolve(s,chain,proof,f'补采{proof.code}有效判读 {proof.defect}')
            if proof.pass_flag and proof.defect=='合格':
                item.state='passed'
                return {'chain':'resolved','sample':'passed'}
            item.state='held'
            job=locked(s,PrintJob,chain.job_id);job.status='hold'
            hold=PressHold(job_id=job.id,sample_id=item.id,reason='补采判缺陷 '+proof.code+' / '+proof.defect,created_at=now(),reproof_ids=[])
            s.add(hold);s.flush()
            return {'chain':'resolved','sample':'held','hold':hold.id}
        if chain.purpose=='recheck':
            hold=get(s,PressHold,chain.hold_id)
            hold.reproof_id=proof.id;hold.reproof_ids=[*(hold.reproof_ids or []),proof.id]
            _resolve(s,chain,proof,f'补采复验{proof.code}有效判读 {proof.defect}')
            return {'chain':'resolved','recheck':True}
        # first：承接链闭合，拦截解除；合格张可作复验/签印，缺陷张照常生成调机
        _resolve(s,chain,proof,f'补采{proof.code}有效判读 {proof.defect}')
        return {'chain':'resolved','first':True}
    # 2) 非承接张：判断用途并在拒判时建链
    sample=s.scalar(select(PressSample).where(PressSample.proof_id==proof.id).with_for_update())
    if sample:
        if failed:
            sample.state='held';job=locked(s,PrintJob,sample.job_id);job.status='hold'
            hold=PressHold(job_id=job.id,sample_id=sample.id,reason='量产抽检 '+proof.code+' / 判读失败',created_at=now(),reproof_ids=[]);s.add(hold)
            return {'sample':'failed-hold'}
        if rejected:
            sample.state='waiting_resample'
            create_chain(s,proof,'sample',None,sample_id=sample.id)
            return {'sample':'waiting_resample'}
        if proof.pass_flag and proof.defect=='合格':
            sample.state='passed';return {'sample':'passed'}
        sample.state='held';job=locked(s,PrintJob,sample.job_id);job.status='hold'
        hold=PressHold(job_id=job.id,sample_id=sample.id,reason='量产抽检 '+proof.code+' / '+proof.defect,created_at=now(),reproof_ids=[]);s.add(hold)
        return {'sample':'held'}
    hold=s.scalar(select(PressHold).where(PressHold.reproof_id==proof.id).with_for_update())
    if hold and rejected:
        create_chain(s,proof,'recheck',None,hold_id=hold.id)
        return {'recheck':'waiting_resample'}
    if rejected:
        create_chain(s,proof,'first',None)
        return {'first':'waiting_resample'}
    return {}
