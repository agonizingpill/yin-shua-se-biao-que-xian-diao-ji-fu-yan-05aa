import numpy as np
from sqlalchemy import select
from sklearn.model_selection import train_test_split,StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.svm import SVC
from sklearn.metrics import confusion_matrix,accuracy_score,pairwise_distances
from .models import ReferenceSheet,PrintJob
from .constants import DEFECTS

SEED=42
def vector(p,target=1.4):return [p.density_c/target,p.density_m/target,p.density_y/target,p.density_k/target,p.dot_gain/100]

def classify(s,p):
    refs=s.scalars(select(ReferenceSheet).order_by(ReferenceSheet.id)).all()
    if len(refs)<60:raise ValueError('带标签参考色标不足60张')
    x=np.array([vector(r)for r in refs]);y=np.array([r.label for r in refs]);ids=np.arange(len(refs))
    # 留出张只作独立评估，固定seed分层拆分；送测ProofSheet从不进入参考数据
    train,test=train_test_split(ids,test_size=.2,stratify=y,random_state=SEED)
    xtr,ytr=x[train],y[train]
    # 判据仅由训练折确定：StandardScaler只fit训练张
    scaler=StandardScaler().fit(xtr);ztr=scaler.transform(xtr)
    # 拒判依据1：训练折标准化空间留一最近邻距离包络，超过训练中最远邻距即脱离训练支撑域
    d=pairwise_distances(ztr);np.fill_diagonal(d,np.inf)
    nn_threshold=float(d.min(axis=1).max())
    # 拒判依据2：训练折5折交叉验证的最低最大后验概率作为可信置信下限
    skf=StratifiedKFold(n_splits=5,shuffle=True,random_state=SEED);oof_max=np.zeros(len(train))
    for a,b in skf.split(ztr,ytr):
        fold=make_pipeline(StandardScaler(),SVC(kernel='rbf',C=2,probability=True,random_state=SEED))
        fold.fit(xtr[a],ytr[a]);oof_max[b]=fold.predict_proba(xtr[b]).max(axis=1)
    proba_threshold=float(oof_max.min())
    model=make_pipeline(StandardScaler(),SVC(kernel='rbf',C=2,probability=True,random_state=SEED));model.fit(xtr,ytr)
    target=s.get(PrintJob,p.job_id).target_density
    q=np.array([vector(p,target)])
    proba=model.predict_proba(q)[0];classes=[str(c)for c in model.classes_]
    tendency=str(classes[int(np.argmax(proba))]);pmax=float(proba.max())
    qz=scaler.transform(q)[0];nn=float(pairwise_distances(qz.reshape(1,-1),ztr).min())
    reasons=[]
    if nn>nn_threshold:reasons.append('脱离训练支撑域：最近邻距离%.3f>训练包络%.3f'%(nn,nn_threshold))
    if pmax<proba_threshold:reasons.append('低于可信置信下限：最大后验概率%.3f<训练折交叉验证下限%.3f'%(pmax,proba_threshold))
    rejected=bool(reasons)
    # 留出张独立评估：同一拒判依据作用于留出集，仅汇报不回灌训练
    pred=model.predict(x[test]);rejected_holdout=[]
    zte=scaler.transform(x[test]);nn_te=pairwise_distances(zte,ztr).min(axis=1);p_te=model.predict_proba(x[test]).max(axis=1)
    accept_mask=np.ones(len(test),dtype=bool)
    for k in range(len(test)):
        rr=[]
        if nn_te[k]>nn_threshold:rr.append('distance')
        if p_te[k]<proba_threshold:rr.append('proba')
        if rr:accept_mask[k]=False;rejected_holdout.append({'code':refs[test[k]].code,'true_label':str(y[test][k]),'reasons':rr})
    acc_idx=np.where(accept_mask)[0]
    evidence={'verdict':'拒判'if rejected else '可信判读','rejected':rejected,
        'rejection_reasons':reasons,
        'tendency':tendency,
        'probabilities':{c:round(float(v),5)for c,v in zip(classes,proba)},
        'nearest_neighbor_distance':round(nn,5),
        'reject_rules':{'nearest_neighbor_envelope':round(nn_threshold,5),'crossval_proba_floor':round(proba_threshold,5),'rule_source':'训练折120张：留一最近邻包络+5折交叉验证置信下限；留出张不参与拟合'},
        'labels':list(DEFECTS),
        'confusion_matrix':confusion_matrix(y[test],pred,labels=list(DEFECTS)).tolist(),
        'accuracy':round(float(accuracy_score(y[test],pred)),4),
        'holdout_accepted':int(accept_mask.sum()),'holdout_rejected':int((~accept_mask).sum()),
        'holdout_accuracy_accepted':round(float((pred[acc_idx]==y[test][acc_idx]).mean()),4)if len(acc_idx)else None,
        'holdout_coverage':round(float(accept_mask.mean()),4),
        'holdout_rejections':rejected_holdout,
        'train_rows':len(train),'holdout_rows':len(test),'seed':SEED,
        'reference_codes':[refs[i].code for i in train],'holdout_codes':[refs[i].code for i in test],
        'current_proof_code':p.code,
        'feature_names':['青密度比','品红密度比','黄密度比','黑密度比','网点扩大率'],
        'features':vector(p,target)}
    # 拒判张不得硬归入三类；可信张才给出三类判读
    return ('拒判'if rejected else tendency),evidence
