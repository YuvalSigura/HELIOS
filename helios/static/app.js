const $=(id)=>document.getElementById(id);
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
let reportIndex=[],currentUser=null;
async function api(path,options={}){
  const res=await fetch(path,{credentials:'same-origin',...options,headers:{...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});
  const obj=await res.json().catch(()=>({detail:'Unexpected server response'}));
  if(!res.ok)throw Error(obj.detail||'Request failed');return obj;
}
async function initialize(){
  try{
    currentUser=await api('/api/me');
    $('login').hidden=true;$('dashboard').hidden=false;
    $('account').textContent=currentUser.organization+' · '+currentUser.email;
    await loadReports();
  }catch{$('login').hidden=false;$('dashboard').hidden=true;}
}
async function loadReports(){
  reportIndex=await api('/api/reports');
  $('total').textContent=reportIndex.length;
  $('shared').textContent=reportIndex.filter(x=>x.shared).length;
  $('mine').textContent=reportIndex.filter(x=>!x.shared).length;
  const container=$('reports');container.replaceChildren();
  for(const r of reportIndex){
    const row=el('div',undefined,'report'),meta=el('div'),controls=el('div');
    meta.append(el('div',r.title,'rtitle'),el('div',r.organization+' · '+r.summary,'rdesc'));
    const badge=el('span',r.shared?'PARTNER SHARED':'WORKSPACE','tag '+(r.shared?'':'own'));
    const button=el('button','Open','secondary');button.style.marginLeft='12px';
    button.onclick=()=>showReport(r.id);
    controls.append(badge,button);row.append(meta,controls);container.append(row);
  }
}
async function showReport(id){
  const d=$('detail');d.hidden=false;d.replaceChildren();
  try{
    const r=await api('/api/reports/'+id);
    d.append(el('div','REPORT DETAILS','eyebrow'),el('h2',r.title),el('p',r.summary));
    const actions=el('div',undefined,'actions');
    const notes=el('button','View report notes','secondary');
    notes.onclick=async()=>{
      try{
        const rows=await api('/api/reports/'+id+'/notes');
        const pre=el('div',JSON.stringify(rows,null,2),'data');
        const old=$('report-notes');if(old)old.remove();
        pre.id='report-notes';d.append(pre);
      }catch(e){alert(e.message)}
    };actions.append(notes);
    if(r.owner_org_id!==currentUser.org_id){
      const clone=el('button','Copy to my workspace');
      clone.onclick=async()=>{try{const copy=await api('/api/reports/'+id+'/clone',{method:'POST'});await loadReports();await showReport(copy.id)}catch(e){alert(e.message)}};
      actions.append(clone);
    }else{
      const exp=el('button','Export CSV');
      exp.onclick=async()=>{try{const job=await api('/api/reports/'+id+'/exports',{method:'POST'});trackExport(job.job_id)}catch(e){alert(e.message)}};
      actions.append(exp);
    }
    d.append(actions);
  }catch(e){d.append(el('p',e.message,'error'))}
  d.scrollIntoView({behavior:'smooth',block:'start'});
}
function trackExport(id){
  const wrap=$('exports');
  if(wrap.textContent.includes('No export'))wrap.replaceChildren();
  const item=el('div','Export '+id+': queued','report');wrap.prepend(item);
  let attempts=0;
  const timer=setInterval(async()=>{
    if(++attempts>80){clearInterval(timer);return}
    try{
      const job=await api('/api/exports/'+id);
      item.textContent='Export '+id+': '+job.state;
      if(job.state==='done'){
        clearInterval(timer);
        const link=el('a',' Download CSV');link.href=job.download_url;
        link.style.marginLeft='15px';item.append(link);
      }else if(job.state==='failed'){clearInterval(timer)}
    }catch{clearInterval(timer)}
  },1500);
}
$('login-form').addEventListener('submit',async(e)=>{
  e.preventDefault();$('login-error').textContent='';
  const data=new FormData(e.currentTarget);
  try{
    await api('/api/session',{method:'POST',body:JSON.stringify({email:data.get('email'),password:data.get('password')})});
    await initialize();
  }catch(err){$('login-error').textContent=err.message}
});
$('refresh').onclick=()=>loadReports().catch(e=>alert(e.message));initialize();
