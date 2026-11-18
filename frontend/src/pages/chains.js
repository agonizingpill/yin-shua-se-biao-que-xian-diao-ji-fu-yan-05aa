import {esc,formData,fixed,localStamp} from '../utils/format.js';
import {badge,notify,jobLabel} from '../components/press.js';
import {CHAIN_PURPOSES,CHAIN_STATES} from '../constants.js';
import {send} from '../api.js';
const inputs=()=>`<div class="cmykfields">${['c','m','y','k'].map(k=>`<div class="tone"><label>${k.toUpperCase()} / 实地密度</label><input name="density_${k}" type="number" min="0" max="3" step=".01" value="1.4" required></div>`).join('')}</div><label>网点扩大率 / %</label><input name="dot_gain" type="number" min="0" max="50" step=".1" value="14" required>`;
const verdict=p=>p?p.classification_state==='rejected'?'拒判':p.classification_state==='classified'?p.defect:p.classification_state==='failed'?'判读失败（可重试补采）':p.classification_state:'—';
export function render(s){
  const waiting=s.chains.filter(c=>c.state==='waiting').length;
  const proofOf=id=>s.proofs.find(p=>p.id===id);
  return `<div class="head"><div><div class="eyebrow">REJECTION / RESAMPLE CHAIN / 10</div><h1>判不准，就拒判补采，不放行。</h1><p>陌生色标不硬归三类。拒判依据由参考训练部分确定，留出张只作独立评估。首张、抽检、停机复验遇拒判均在此等待补采：关联原张与同一用途，原证据保留，普通合格张不能顶替；并发补采只认一条承接链。</p></div><span class="mono">WAITING ${waiting}</span></div>
  <section class="section">
    <h2>拒判补采承接链</h2>
    ${s.chains.length?`<div class="chains">${s.chains.map(c=>{const orig=proofOf(c.original_proof_id);const eff=proofOf(c.effective_proof_id);return `<article class="chain ${c.state}" data-chain="${c.id}">
      <div class="chain-head"><span class="eyebrow">CHAIN-${String(c.id).padStart(3,'0')} / ${esc(CHAIN_PURPOSES[c.purpose]||c.purpose)} / ${jobLabel(s,c.job_id)}</span>${badge(c.state==='waiting'?'fail':c.state==='resolved'?'pass':'fail',CHAIN_STATES[c.state]||c.state)}</div>
      <h3>原张 ${esc(orig?.code||'#'+c.original_proof_id)} ${badge('rejected','拒判')}</h3>
      <p class="muted">建链 ${esc(localStamp(c.created_at))} · 操作人 ${esc(c.created_by)}</p>
      <div class="reject-reason"><b>拒判依据（训练折确定）：</b><ul>${(c.reject_reason||'').split('；').filter(Boolean).map(r=>`<li>${esc(r)}</li>`).join('')}</ul>${orig?.evidence?.reject_rules?`<small>最近邻包络 ${orig.evidence.reject_rules.nearest_neighbor_envelope} · 交叉验证置信下限 ${orig.evidence.reject_rules.crossval_proba_floor} · 本张最近邻距离 ${orig.evidence.nearest_neighbor_distance}</small>`:''}</div>
      <div class="chain-progress"><b>承接进度：</b><ol><li>原张 ${esc(orig?.code)} · ${esc(verdict(orig))}</li>${(c.resample_proof_ids||[]).map(id=>{const rp=proofOf(id);return `<li class="${rp?.classification_state==='rejected'||rp?.classification_state==='failed'?'rej':rp?.classification_state==='classified'?'ok':''}">补采 ${esc(rp?.code||'#'+id)} · ${esc(verdict(rp))}${c.effective_proof_id===id?' · <b>有效判读</b>':''}</li>`}).join('')}</ol></div>
      ${c.state==='resolved'?`<p class="note">承接闭合：${esc(c.resolution)}${eff?` · 有效张 ${esc(eff.code)}（${esc(eff.defect)}）`:''}<br>${esc(c.resolved_at?localStamp(c.resolved_at):'')}</p>`:
        c.state==='failed'?`<p class="note">补采判读失败：${esc(c.resolution)}，请重新登记色标判读。</p>`:
        `<form class="resample-form" data-key="${c.id}"><input name="job_id" type="hidden" value="${c.job_id}"><label>补采色标编号（新编号，重试不重复建张）</label><input name="code" placeholder="PS-RESAMPLE-${c.id}-${(c.resample_proof_ids||[]).length+1}" required>${inputs()}<div class="actions"><button class="primary" ${s.user.role==='viewer'?'disabled':''}>补采并沿用训练判读</button></div><small class="muted">补采关联原张及同一用途；合格后按原签印或复机权限解除拦截，缺陷照常调机。</small></form>`}
    </article>`}).join('')}</div>`:'<p class="note">暂无拒判承接链。只有脱离训练支撑域或低于可信置信下限的色标才会拒判。</p>'}
  </section>`;
}
export function bind(s,reload){
  const numeric=d=>{for(const k of ['job_id','density_c','density_m','density_y','density_k','dot_gain'])d[k]=Number(d[k]);return d;};
  document.querySelectorAll('.resample-form').forEach(f=>f.onsubmit=async e=>{e.preventDefault();try{await send('/resample-chains/'+f.dataset.key+'/resample',numeric(formData(f)));await reload();notify('补采色标已入队，沿用同一训练判别');}catch(err){notify(err.message)}});
}
