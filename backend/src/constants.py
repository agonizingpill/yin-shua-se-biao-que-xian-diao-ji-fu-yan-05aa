ROLES=('admin','pressman','viewer')
DEFECTS=('合格','乳化','偏色')
JOB_STATES=('setup','adjusting','production','hold')
ADJUSTMENT_STATES=('issued','executed','signed')
# 判读状态：rejected为可信判据外的拒判，不属合格也不属已知缺陷
CLASSIFICATION_STATES=('unmeasured','classifying','classified','rejected','failed')
REJECTED='rejected'
# 补采承接链用途
CHAIN_PURPOSES=('first','sample','recheck')
CHAIN_STATES=('waiting','resolved','failed')
CHAIN_WAITING='waiting'
# 量产抽检状态新增waiting_resample：拒判等待补采，不按合格也不按已知缺陷停机
SAMPLE_STATES=('classifying','passed','held','waiting_resample')
