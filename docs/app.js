const D = window.FORGE_DATA, $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const CFG = { repo: "https://github.com/Maced78/level-forge", team: "Azərçay: Nural Shukurlu, Alfaddin Hamidov, Chingiz Aslanov" };
if (CFG.repo.startsWith("http")) { $("#repo-link").href = CFG.repo; $("#clone-url").textContent = CFG.repo + ".git"; }
if (CFG.team) $("#team").textContent = "Team: " + CFG.team + ".";

/* ---------- board ---------- */
const NOUN_COL={PLAYER:"#f4f4f8",GOAL:"#f2c14e",BABA:"#f4f4f8",KEKE:"#f08a5d",ROCK:"#c8a46a",BOX:"#c98b4e",WALL:"#7c849c",HEDGE:"#4f9d69",FLAG:"#f2c14e",STAR:"#f7e26b",LOVE:"#ef6f9c",KEY:"#f2a65a",WATER:"#4a90e2",LAVA:"#ff6b35",SKULL:"#c0392b",CRAB:"#e25c5c",TILE:"#39405a"};
const PROP_COL={YOU:"#e5609c",WIN:"#f2c14e",STOP:"#4f9d69",PUSH:"#c8a46a",SINK:"#4a90e2",DEFEAT:"#c0392b"};
function drawBoard(cv,W,H,cells,rules,state){
  const dpr=window.devicePixelRatio||1,cssW=cv.clientWidth||600,cell=Math.max(14,Math.min(60,Math.floor(cssW/W)));
  cv.width=cell*W*dpr;cv.height=cell*H*dpr;cv.style.maxWidth=(cell*W)+"px";cv.style.aspectRatio=`${W}/${H}`;
  const g=cv.getContext("2d");g.scale(dpr,dpr);g.fillStyle="#090a0f";g.fillRect(0,0,cell*W,cell*H);g.strokeStyle="#171a25";g.lineWidth=1;
  for(let x=0;x<=W;x++){g.beginPath();g.moveTo(x*cell+.5,0);g.lineTo(x*cell+.5,H*cell);g.stroke();}
  for(let y=0;y<=H;y++){g.beginPath();g.moveTo(0,y*cell+.5);g.lineTo(W*cell,y*cell+.5);g.stroke();}
  const you=new Set((rules||[]).filter(r=>r.endsWith(" IS YOU")).map(r=>"ICON_"+r.split(" ")[0]));you.add("ICON_PLAYER");
  const ord=c=>c[2]==="ICON_GOAL"?-1:c[2].startsWith("ICON_")?(you.has(c[2])?2:0):1;
  [...cells].sort((a,b)=>ord(a)-ord(b)).forEach(c=>{const x=c[0]*cell,y=c[1]*cell,p=Math.max(2,cell*.09),name=c[2];
    if(name==="ICON_GOAL"){g.strokeStyle="#f2c14e";g.lineWidth=Math.max(2,cell*.07);g.beginPath();g.arc(x+cell/2,y+cell/2,cell*.2,0,7);g.stroke();return;}
    if(name.startsWith("ICON_")){const n=name.slice(5),col=NOUN_COL[n]||"#9aa3b8";g.fillStyle=col;
      if(["WALL","HEDGE","WATER","LAVA","TILE"].includes(n)){g.globalAlpha=n==="TILE"?.5:.9;g.fillRect(x+1,y+1,cell-2,cell-2);g.globalAlpha=1;
        if(n==="WATER"||n==="LAVA"){g.strokeStyle="rgba(255,255,255,.35)";g.lineWidth=1.4;for(let k=1;k<=2;k++){g.beginPath();const yy=y+cell*k/3;g.moveTo(x+p,yy);g.quadraticCurveTo(x+cell*.3,yy-3,x+cell*.5,yy);g.quadraticCurveTo(x+cell*.7,yy+3,x+cell-p,yy);g.stroke();}}
      }else{g.beginPath();
        if(["ROCK","BOX"].includes(n))g.roundRect(x+p*1.6,y+p*1.6,cell-p*3.2,cell-p*3.2,n==="ROCK"?cell*.28:cell*.12);
        else if(["FLAG","STAR","LOVE","KEY"].includes(n)){const cx=x+cell/2,cy=y+cell/2,R=cell*.36;for(let i=0;i<10;i++){const a=-Math.PI/2+i*Math.PI/5,rr=i%2?R*.48:R;g[i?"lineTo":"moveTo"](cx+rr*Math.cos(a),cy+rr*Math.sin(a));}g.closePath();}
        else g.arc(x+cell/2,y+cell/2,cell*.34,0,7);
        g.fill();if(you.has(name)){g.strokeStyle="#e5609c";g.lineWidth=2.5;g.stroke();}
        if(["SKULL","CRAB"].includes(n)){g.fillStyle="#090a0f";g.beginPath();g.arc(x+cell*.4,y+cell*.46,cell*.06,0,7);g.arc(x+cell*.6,y+cell*.46,cell*.06,0,7);g.fill();}}
      if(cell>=26){g.fillStyle=["WALL","HEDGE","WATER","LAVA"].includes(n)?"rgba(255,255,255,.78)":(n==="TILE"?"#8f96a8":"#090a0f");g.font=`700 ${Math.max(8,cell*.2)}px ui-monospace,Menlo,monospace`;g.textAlign="center";g.textBaseline="middle";g.fillText(n==="PLAYER"?"you":n.toLowerCase(),x+cell/2,y+cell*(["ROCK","BOX","BABA","KEKE","SKULL","CRAB"].includes(n)?.66:.5),cell-4);}
    }else{const col=name==="IS"?"#eceef4":(PROP_COL[name]||NOUN_COL[name]||"#b9a0ff"),isProp=name in PROP_COL;
      g.beginPath();g.roundRect(x+p,y+p,cell-2*p,cell-2*p,cell*.12);
      if(isProp){g.fillStyle=col;g.fill();g.fillStyle="#090a0f";}else{g.fillStyle="#12141c";g.fill();g.strokeStyle=col;g.lineWidth=1.5;g.stroke();g.fillStyle=col;}
      g.font=`800 ${Math.max(7,cell*(name.length>4?.2:.26))}px ui-monospace,Menlo,monospace`;g.textAlign="center";g.textBaseline="middle";g.fillText(name,x+cell/2,y+cell/2+.5,cell-2*p-2);}
  });
  if(state==="WON"||state==="LOST"){g.fillStyle=state==="WON"?"rgba(87,199,133,.16)":"rgba(239,111,108,.18)";g.fillRect(0,0,cell*W,cell*H);g.fillStyle=state==="WON"?"#8ff0b8":"#ffb1ae";g.font=`800 ${cell*.5}px ui-monospace,monospace`;g.textAlign="right";g.textBaseline="bottom";g.fillText(state,cell*W-8,cell*H-4);}
}
const stateCells=(st,W)=>st.map(o=>[o.c%W,Math.floor(o.c/W),o.n]);
const cellsState=(cells,W)=>cells.map(c=>({c:c[1]*W+c[0],n:c[2]}));

/* ---------- hero + KPIs ---------- */
const ALL = D.llm_runs.concat(D.gallery, (D.sokoban||{runs:[]}).runs);
const flagship = D.gallery[0];
(function(){ let i=0; const f=flagship.frames; const tick=()=>{ drawBoard($("#hero"),flagship.width,flagship.height,f[i].cells,f[i].rules,f[i].state); $("#hero-rules").innerHTML=f[i].rules.map(r=>`<span class="rule">${esc(r)}</span>`).join(""); i=(i+1)%f.length; };
  tick(); if(!window.matchMedia("(prefers-reduced-motion: reduce)").matches) setInterval(tick,330);
  const dq=flagship.verification.levels.solution_quality.difficulty_components;
  $("#hero-cap").textContent=`A hard level, won by the computer in ${flagship.solution.length} moves`;
})();
(function(){ const b=D.bench.arms.full_pipeline, c=D.claim_summary, m=D.bench.model_vs_engine_on_sabotaged_levels, ch=D.bench.contradiction_handling;
  const k=[[b.solvability_established_pct+"%",`of ${b.n} test requests produced a level the game could win`],
    [`${b.false_acceptances} of ${b.levels_labelled_solvable}`,"levels were wrongly marked as winnable"],
    [b.fully_validated_pct+"%","passed every check: winnable, as hard as asked, needs the skills asked for"],
    [`${ch.correctly_rejected} of ${ch.contradictory_prompts}`,"impossible requests refused, with the reason"]];
  $("#kpis").innerHTML=k.map(x=>`<div class="kpi"><b>${x[0]}</b><span>${x[1]}</span></div>`).join("");
})();

/* ---------- demo runs ---------- */
let R=null, step=0, timer=null, live=null;
function chipLabel(g){ const st=(g.game==="sokoban_sg"?"SOKOBAN · ":"")+(g.status==="REJECTED_CONTRADICTION"?"REFUSED":(g.spec.difficulty||"").toUpperCase()); const ai=g.ai&&g.ai.mode&&g.ai.mode!=="off"?" · LLM":""; return `<small style="color:${g.status==="REJECTED_CONTRADICTION"?"var(--bad)":"var(--accent)"}">${st}${ai}</small>${esc(g.request.length>110?g.request.slice(0,108)+"…":g.request)}`; }
$("#chips").innerHTML=ALL.map((g,i)=>`<button class="chip" data-i="${i}">${chipLabel(g)}</button>`).join("");
$("#chips").onclick=e=>{const b=e.target.closest(".chip"); if(b) select(+b.dataset.i);};
function row(name,lv,extra){ if(!lv) return ""; const cls=lv.passed?"p":(lv.established===false?"u":"f"); return `<div class="lvl"><span class="dot ${cls}">${lv.passed?"✓":cls==="u"?"?":"✕"}</span><div><b>${name}</b><small>${extra}</small></div></div>`; }
function aiCard(g){ const a=g.ai; if(!a||a.mode==="off") return `<div class="card"><h3>Request understanding</h3><p class="hint" style="margin:0">This run used the deterministic keyword parser and the constraint planner (no language model). Parsed spec: difficulty <b>${esc(g.spec.difficulty)}</b>; required skills <span class="mono">${esc((g.spec.skills_required||[]).join(", ")||"none named")}</span>${(g.spec.skills_forbidden||[]).length?`; forbidden <span class="mono">${esc(g.spec.skills_forbidden.join(", "))}</span>`:""}.</p></div>`;
  const u=a.usage||{}, kw=a.keyword_parser_would_have_said;
  return `<div class="card"><h3>AI trace · ${esc((u.models||[]).join(", ")||a.intent_source)}</h3>
   <p style="margin:0 0 6px"><span class="tag t-info">LLM understood</span> ${esc(g.spec.summary||"")} → difficulty <b>${esc(g.spec.difficulty)}</b>, skills <span class="mono">${esc((g.spec.skills_required||[]).join(", ")||"none")}</span>${(g.spec.skills_forbidden||[]).length?`, forbidden <span class="mono">${esc(g.spec.skills_forbidden.join(", "))}</span>`:""}</p>
   ${kw?`<p class="hint" style="margin:0 0 8px">The keyword parser alone would have said: ${esc(kw.difficulty)}, skills <span class="mono">${esc(kw.skills_required.join(", ")||"none")}</span>.</p>`:""}
   ${(a.proposals||[]).length?`<div class="tw"><table><tr><th>LLM as designer</th><th>Verifier's verdict</th></tr>${a.proposals.map(p=>`<tr><td>${esc(p.by.replace(/\s*\(.*\)/,""))}<br><span class="hint">${esc(p.idea||"")}</span></td><td><span class="tag ${p.status==="FULLY_VALIDATED"?"t-ok":p.status==="PROVEN_SOLVABLE"?"t-warn":"t-bad"}">${esc(p.status.replaceAll("_"," ").toLowerCase())}</span><br><span class="hint">${esc((p.reasons||[]).slice(0,3).join("; "))}</span></td></tr>`).join("")}</table></div>`:""}
   ${g.delivered_from?`<p class="hint" style="margin:8px 0 0">Delivered level came from: <b>${esc(g.delivered_from)}</b>.</p>`:""}
   <p class="hint" style="margin:6px 0 0">${u.calls||0} model call(s), ${u.total_tokens||0} tokens, ${u.seconds||0}s of model time.${(a.errors||[]).length?" Errors: "+esc(a.errors.join("; ")):""}</p></div>`; }
function select(i){
  clearInterval(timer); live=null; R=ALL[i]; document.querySelectorAll(".chip").forEach((c,k)=>c.classList.toggle("on",k===i));
  const g=R, v=$("#run-view");
  if(g.status==="REJECTED_CONTRADICTION"){
    v.innerHTML=`<div class="card"><span class="badge b-REJECTED_CONTRADICTION">REQUEST REFUSED · no level produced</span>
      <p class="hint" style="margin:10px 0 0">No valid level of this game can satisfy the request, so nothing was generated and nothing is labelled verified.</p>
      ${g.contradictions.map((c,k)=>`<div class="contra"><h4>${esc(c.kind.replaceAll("_"," "))}</h4>${esc(c.explanation)}
        ${c.cycle&&c.cycle.length?`<div class="chain">${c.cycle.map(x=>`<span>${esc(x)}</span>`).join("<i>needs →</i>")}</div>`:""}
        ${c.evidence&&c.evidence.detail?`<p class="hint"><b>Machine evidence:</b> ${esc(c.evidence.detail)}.</p><canvas id="ev${k}"></canvas>`:""}
        <b style="display:block;margin-top:8px;font-size:13px">Valid alternatives</b><ul class="tight">${(c.suggestions||[]).map(s=>`<li>${esc(s)}</li>`).join("")}</ul></div>`).join("")}</div>
      <div style="margin-top:14px">${aiCard(g)}</div>`;
    g.contradictions.forEach((c,k)=>{const ev=c.evidence; if(ev&&ev.cells) requestAnimationFrame(()=>drawBoard($("#ev"+k),ev.width,ev.height,ev.cells,[],""));});
    return; }
  const V=g.verification, L=V.levels, q=L.solution_quality, rb=L.robustness, mc=L.mechanic_coverage, dc=q&&q.difficulty_components, pr=g.presentation;
  v.innerHTML=`<div class="card">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px"><span class="badge b-${g.status}">${esc(g.status.replaceAll("_"," "))}</span>${pr&&pr.title?`<b style="font-size:17px">“${esc(pr.title)}”</b>`:""}<span class="hint">${g.game==="sokoban_sg"?"second game: Sokoban · ":""}${g.width}×${g.height} · generated in ${g.elapsed_seconds}s</span></div>
    ${pr&&pr.designer_note?`<p class="hint" style="margin:0 0 10px"><span class="tag t-info">LLM note</span> ${esc(pr.designer_note)}</p>`:""}
    <canvas id="board"></canvas>
    <div class="play"><button class="btn sec sm" id="b-prev">◀</button><button class="btn sm" id="b-play">▶ Play solution</button><button class="btn sec sm" id="b-next">▶|</button><input type="range" id="slider" min="0" max="${g.frames.length-1}" value="0"><span class="mono hint" id="stepno"></span>${g.game==="sokoban_sg"?"":`<button class="btn sec sm" id="b-live">Play it yourself</button>`}</div>
    <p class="hint" id="live-msg" style="margin:8px 0 0"></p>
    <div class="rules" id="rules"></div>
    <details><summary>Native level file (what the game loads) and shortest solution</summary><pre>${esc(g.native)}</pre><pre>${esc(g.solution)}</pre></details></div>
   <div class="grid2" style="margin-top:14px">
    <div class="card"><h3>What was proven</h3>
     ${row("Structural validity",L.structural,`${L.structural.checks.filter(c=>c.passed).length}/${L.structural.checks.length} checks, including the original engine's loader`)}
     ${row("Solvability",L.solvable,esc(L.solvable.detail))}
     ${row("Difficulty (not length)",q?{...q,established:q.difficulty_established}:null,q&&q.difficulty_established?`score <b style="color:var(--ink)">${q.difficulty_score}</b> (band ${q.difficulty_band[0]}–${q.difficulty_band[1]>=1000?"∞":q.difficulty_band[1]}): a random careful player stays winnable 1 time in ${Math.round(2**dc.trap_bits).toLocaleString()}; ${dc.trap_states} trap points; ${Math.round(dc.dead_ratio*100)}% of reachable states are dead ends; ${g.game==="sokoban_sg"?`${dc.boxes} box(es) to deliver`:`${dc.rule_changes} rule change(s); ${dc.sacrifices} rule word(s) sacrificed`}`:"not established")}
     ${row("Requested skills",mc,mc?`${mc.covered}/${mc.requested} exercised and proven necessary`:"")}
     ${row("Dead states",rb?{passed:rb.analysis_complete,established:rb.analysis_complete}:null,rb?esc(rb.detail):"")}
     ${Object.keys(V.skills||{}).length?`<div class="tw" style="margin-top:8px"><table><tr><th>Skill</th><th>Necessary?</th></tr>${Object.entries(V.skills).map(([k,s])=>`<tr><td><b>${esc(k.replaceAll("_"," "))}</b><br><span class="hint">${esc(s.detail||"")}</span></td><td><span class="tag ${s.forbidden?(s.passed?"t-ok":"t-bad"):s.necessity==="proven"?"t-ok":s.necessity==="n/a"?"t-dim":"t-warn"}">${s.forbidden?(s.passed?"avoidable":"needed"):esc((s.necessity||"").replaceAll("_"," "))}${s.proof?" · "+s.proof:""}</span></td></tr>`).join("")}</table></div>`:""}
    </div>
    <div>${aiCard(g)}
     <div class="card" style="margin-top:14px"><h3>Generation log · ${g.attempts.length} attempt(s)</h3>
      ${g.search?`<p class="hint" style="margin:0 0 8px">Hard-level search: ${g.search.candidates_built} candidates built in ${g.search.seconds}s, ${g.search.candidates_scored} scored exactly; median difficulty ${g.search.median_score}, best ${g.search.best_scores[0]}.</p>`:""}
      <div class="tw"><table>${g.attempts.map(a=>`<tr><td class="num">${a.attempt}</td><td><span class="tag ${a.status==="FULLY_VALIDATED"?"t-ok":a.status==="PROVEN_SOLVABLE"?"t-warn":"t-bad"}">${esc(a.status.replaceAll("_"," ").toLowerCase())}</span></td><td class="hint">${esc((a.reasons||[]).join("; ")||a.proposer||"")}</td></tr>`).join("")}</table></div></div></div>
   </div>`;
  const show=k=>{ step=Math.max(0,Math.min(g.frames.length-1,k)); const f=g.frames[step], prev=step?g.frames[step-1]:null; drawBoard($("#board"),g.width,g.height,f.cells,f.rules,f.state);
    $("#slider").value=step; $("#stepno").textContent=`${step}/${g.frames.length-1}`; const before=new Set(prev?prev.rules:f.rules);
    $("#rules").innerHTML=f.rules.map(r=>`<span class="rule ${before.has(r)?"":"new"}">${esc(r)}</span>`).join(""); };
  $("#b-prev").onclick=()=>{live=null;show(step-1)}; $("#b-next").onclick=()=>{live=null;show(step+1)}; $("#slider").oninput=e=>{live=null;show(+e.target.value)};
  $("#b-play").onclick=()=>{ live=null; $("#live-msg").textContent=""; clearInterval(timer); if(step>=g.frames.length-1) show(0); timer=setInterval(()=>{ if(step>=g.frames.length-1){clearInterval(timer);return;} show(step+1); },230); };
  if($("#b-live")) $("#b-live").onclick=()=>{ clearInterval(timer); const m=new ForgeModel(g.width,g.height,D.nouns); live={m,hist:[cellsState(g.frames[0].cells,g.width)],over:""}; drawLive(); $("#board").scrollIntoView({block:"center",behavior:"smooth"}); };
  requestAnimationFrame(()=>show(0));
}
function drawLive(){ const g=R, st=live.hist[live.hist.length-1], rules=live.m.parse(st).list; drawBoard($("#board"),g.width,g.height,stateCells(st,g.width),rules,live.over);
  $("#rules").innerHTML=rules.map(r=>`<span class="rule">${esc(r)}</span>`).join(""); $("#stepno").textContent=`${live.hist.length-1} moves`;
  $("#live-msg").innerHTML=live.over==="WON"?`You won in ${live.hist.length-1} moves (shortest possible: ${g.solution.length}). <kbd>R</kbd> restart`:live.over==="LOST"?`Nothing is YOU any more. <kbd>Z</kbd> undo · <kbd>R</kbd> restart`:`You are playing: <kbd>←</kbd><kbd>↑</kbd><kbd>↓</kbd><kbd>→</kbd> move · <kbd>Z</kbd> undo · <kbd>R</kbd> restart. Runs on the JavaScript model, checked against ${D.trace_frames.toLocaleString()} frames recorded from the original engine.`; }
window.addEventListener("keydown",e=>{ if(!live||e.target.tagName==="TEXTAREA") return; const k={ArrowUp:"U",ArrowDown:"D",ArrowLeft:"L",ArrowRight:"R",w:"U",s:"D",a:"L",d:"R"}[e.key];
  if(k){ e.preventDefault(); if(live.over) return; const r=live.m.step(live.hist[live.hist.length-1],k); live.hist.push(r.state); live.over=r.won?"WON":r.lost?"LOST":""; drawLive(); }
  else if(e.key==="z"||e.key==="Z"){ if(live.hist.length>1) live.hist.pop(); live.over=""; drawLive(); }
  else if(e.key==="r"||e.key==="R"){ live.hist=[live.hist[0]]; live.over=""; drawLive(); } });
select(0);

/* ---------- verify your own ---------- */
const EX=`BABA  .     .     .     water .     .     .\nIS    .     baba  .     water .     flag  .\nYOU   .     .     rock  water .     .     .\nROCK  IS    PUSH  .     water .     .     .\nWATER IS    SINK  .     water FLAG  IS    WIN`;
const BROKEN=EX.replace("rock  water .     .     .\nROCK",".     water .     rock  .\nROCK");
let vres=null, vtimer=null;
$("#dsl").value=EX;
function vdraw(st,W,H,over,m){ drawBoard($("#v-board"),W,H,stateCells(st,W),m.parse(st).list,over); }
function verify(){ clearInterval(vtimer); const msg=$("#v-msg"); try{
    const lv=ForgeModel.fromDsl($("#dsl").value,new Set(D.known)), m=new ForgeModel(lv.W,lv.H,D.nouns), rules=m.parse(lv.state).list;
    vdraw(lv.state,lv.W,lv.H,"",m);
    if(!rules.some(r=>r.endsWith(" IS YOU"))){ msg.innerHTML=`<span class="tag t-bad">invalid</span> no “X IS YOU” sentence is readable at the start, so nothing can be controlled.`; $("#v-moves").textContent=""; vres=null; return; }
    const t0=performance.now(), r=m.solve(lv.state,200000), ms=Math.round(performance.now()-t0); vres={lv,m,r};
    msg.innerHTML=r.status==="solved"?`<span class="tag t-ok">solvable</span> shortest solution ${r.moves.length} moves · ${r.states.toLocaleString()} states searched in ${ms} ms`:r.status==="unsolvable"?`<span class="tag t-bad">proved unsolvable</span> all ${r.states.toLocaleString()} reachable states searched in ${ms} ms; none is a win`:`<span class="tag t-warn">not established</span> search stopped at ${r.states.toLocaleString()} states`;
    $("#v-moves").textContent=r.moves; }catch(e){ msg.innerHTML=`<span class="tag t-bad">malformed</span> ${esc(e.message)}`; vres=null; } }
$("#v-go").onclick=verify; $("#v-reset").onclick=()=>{$("#dsl").value=EX;verify();}; $("#v-break").onclick=()=>{$("#dsl").value=BROKEN;verify();};
$("#v-play").onclick=()=>{ if(!vres||vres.r.status!=="solved") return; clearInterval(vtimer); let st=vres.lv.state,i=0; const {lv,m,r}=vres; vdraw(st,lv.W,lv.H,"",m);
  vtimer=setInterval(()=>{ if(i>=r.moves.length){clearInterval(vtimer);return;} const s=m.step(st,r.moves[i++]); st=s.state; vdraw(st,lv.W,lv.H,s.won?"WON":"",m); },230); };
verify();

/* ---------- evidence ---------- */
(function(){ const A=D.bench.arms, names={random_tiles:"Random tiles (no blueprint)",blueprint_only:"Blueprint-guided, unverified",full_pipeline:"Full pipeline"};
  const rows=[["schema_validity_pct","Accepted by the original loader"],["solvability_established_pct","Solvability established"],["mechanic_coverage_pct","Requested skills exercised and proven necessary"],["difficulty_alignment_pct","Difficulty score inside the requested band"],["fully_validated_pct","Fully validated"]];
  const fp=A.full_pipeline, bd=fp.by_difficulty;
  $("#bench").innerHTML=`<table><tr><th>Metric</th>${Object.values(names).map(n=>`<th class="num">${n}</th>`).join("")}</tr>
   ${rows.map(([k,l])=>`<tr><td>${l}</td>${Object.keys(names).map(a=>`<td class="num">${A[a][k]}%</td>`).join("")}</tr>`).join("")}
   <tr><td>Latency, median / p90 (s)</td>${Object.keys(names).map(a=>`<td class="num">${A[a].latency_seconds.median} / ${A[a].latency_seconds.p90}</td>`).join("")}</tr></table>
   <p class="hint" style="margin:10px 0 0">Median difficulty score by requested difficulty: easy ${bd.easy.median_difficulty_score}, medium ${bd.medium.median_difficulty_score}, hard ${bd.hard.median_difficulty_score}. Fully validated: easy ${bd.easy.fully_validated_pct}%, medium ${bd.medium.fully_validated_pct}%, hard ${bd.hard.fully_validated_pct}%. The 200 requests come from templates over the skills the generator supports, so this measures reliability inside its vocabulary. Not measured: a second game version, and human difficulty ratings.</p>`;
  $("#cmp-time").textContent=`median ${fp.latency_seconds.median}s, hard ≈ ${bd.hard.median_latency_s}s (measured)`;
  const t=D.tests||{};
  const F=[["The real engine explores only about 2,000 states per second","wrote a fast model of it; every solution is still replayed in the real engine, and the two are compared move by move"+(t.difftest_moves?` (${t.difftest_moves.toLocaleString()} moves in the regression suite, no disagreement)`:"")],
    ["A loose rule word can be drowned instead of a rock, so “pushing is required” was false in early hard levels","found by the ablation search; sink gates are now one column thicker than the number of loose words"],
    ["Early levels were long but easy: 0–1 trap points on the solution","replaced length with a difficulty score from the full state space; hard requests now search and keep the hardest candidate"],
    ["Objects pushed into water in the same turn were not counted as pushed","trace analysis fixed; the skill is now detected"],
    ["The game's bundled viewer is a fixed tiny window, scripted, and has no sprite for boxes or hedges","wrote a resizable keyboard player that drives the same engine"],
    [`Hard requests: ${(100-bd.hard.fully_validated_pct).toFixed(1)}% not fully validated in the benchmark`,"delivered with the lower label and the unmet requirement listed, never upgraded"],
    ["Keyword parser misses paraphrased requests","an LLM now does the reading; the keyword parser remains as a fallback and as a safety net for refusals"],
    ["Not established","model ≡ engine is tested, not proven; “unsolvable” means with the four directional inputs; nobody has play-tested the difficulty score"]];
  $("#failures").innerHTML=F.map(f=>`<li><b>${esc(f[0])}.</b> ${esc(f[1])}.</li>`).join("");
  const tag=s=>s==="confirmed"?"t-ok":s==="unresolved"?"t-bad":"t-warn";
  $("#claims").innerHTML=`<table><tr><th>Status</th><th>Claim</th><th>Source</th><th>Probe</th></tr>${D.claims.map(c=>`<tr><td><span class="tag ${tag(c.status)}">${esc(c.status)}</span></td><td>${esc(c.statement)}${c.consequence?`<br><span class="hint">→ ${esc(c.consequence)}</span>`:""}</td><td class="mono hint">${c.source&&c.source.line?esc(c.source.file.split("/").pop()+":"+c.source.line):"—"}</td><td class="mono hint">${c.evidence?esc(c.evidence.probe.split("::")[1])+(c.evidence.passed?" ✓":" ✕"):""}</td></tr>`).join("")}</table>`;
  $("#unsup").innerHTML=`<table>${D.unsupported.map(w=>`<tr><td class="mono"><b>${esc(w.name)}</b></td><td class="hint">${esc(w.evidence)}</td></tr>`).join("")}</table>`;
  if(D.sokoban){ const S=D.sokoban, sb=S.bench, bd2=sb.by_difficulty;
    $("#second").innerHTML=`<p style="margin:0 0 8px">The second game, an open-source pygame <b>Sokoban</b> (<span class="mono">${esc(sb.game.name)}</span>, MIT), was added during the hackathon as a second blueprint package of ${S.adapter_lines} lines. <b>The generation loop in <span class="mono">forge/pipeline.py</span> was not changed for it.</b></p>
     <div class="tw"><table><tr><th></th><th class="num">Baba Is You engine</th><th class="num">Sokoban engine</th></tr>
     <tr><td>Mechanic claims confirmed by probes on the real engine</td><td class="num">${D.claim_summary.confirmed}</td><td class="num">${S.claims.confirmed}</td></tr>
     <tr><td>Search model vs real engine, moves compared</td><td class="num">${(D.tests.difftest_moves||0).toLocaleString()}</td><td class="num">${S.difftest.moves_compared.toLocaleString()}</td></tr>
     <tr><td>Benchmark requests</td><td class="num">${D.bench.arms.full_pipeline.n}</td><td class="num">${sb.trials}</td></tr>
     <tr><td>Solvable, replayed in the original engine</td><td class="num">${D.bench.arms.full_pipeline.solvability_established_pct}%</td><td class="num">${sb.solvable_pct}%</td></tr>
     <tr><td>Fully validated</td><td class="num">${D.bench.arms.full_pipeline.fully_validated_pct}%</td><td class="num">${sb.fully_validated_pct}%</td></tr>
     <tr><td>False acceptances</td><td class="num">${D.bench.arms.full_pipeline.false_acceptances}/${D.bench.arms.full_pipeline.levels_labelled_solvable}</td><td class="num">${sb.false_acceptances}/${sb.labelled_solvable}</td></tr>
     <tr><td>Impossible requests refused</td><td class="num">${D.bench.contradiction_handling.correctly_rejected}/${D.bench.contradiction_handling.contradictory_prompts}</td><td class="num">${sb.contradictory_rejected}</td></tr></table></div>
     <p class="hint" style="margin:8px 0 10px">The Sokoban blueprint is about one hour old and its generator is simple (random rooms filtered by the solver). Its first benchmark run scored 68% fully validated; boxes were being placed in dead corners, which we fixed.</p>`; }
  const L=D.llm, box=$("#llm-evidence");
  if(L&&L.intent_summary){ const I=L.intent_summary, G=L.generation_summary||{}, f=(x)=>`${x.correct}/${x.of}`;
    const gn={raw_llm:"LLM writes the level file directly",llm_skill:"LLM + skill.md, one shot",llm_loop:"LLM + skill.md + verifier feedback (≤2 repairs)",full_pipeline:"Full pipeline (LLM reads, planner builds, verifier judges)"};
    box.innerHTML=`<div class="grid2"><div class="card"><h3>Measured: understanding the request · ${esc(L.model)}</h3><div class="tw"><table><tr><th>Requests</th><th class="num">Keyword parser</th><th class="num">LLM</th></tr>
      <tr><td>Literal wording (${I.keyword.literal.of})</td><td class="num">${f(I.keyword.literal)}</td><td class="num">${f(I.llm.literal)}</td></tr>
      <tr><td>Paraphrased, no keyword matches (${I.keyword.paraphrased.of})</td><td class="num">${f(I.keyword.paraphrased)}</td><td class="num">${f(I.llm.paraphrased)}</td></tr>
      <tr><td><b>All ${I.keyword.all.of} hand-labelled requests</b></td><td class="num"><b>${f(I.keyword.all)}</b></td><td class="num"><b>${f(I.llm.all)}</b></td></tr></table></div>
      <p class="hint" style="margin:8px 0 0">Correct = right difficulty, every labelled skill found, nothing forbidden required, and impossible requests refused. Labels were written by the team before the run.</p></div>
     <div class="card"><h3>Measured: who should build the level · ${(G.raw_llm||{}).n||0} requests, same verifier</h3><div class="tw"><table><tr><th>Approach</th><th class="num">Loads</th><th class="num">Solvable</th><th class="num">Fully validated</th></tr>
      ${Object.keys(gn).filter(k=>G[k]).map(k=>`<tr><td>${gn[k]}</td><td class="num">${G[k].loader_accepts}/${G[k].n}</td><td class="num">${G[k].solvable}/${G[k].n}</td><td class="num">${G[k].fully_validated}/${G[k].n}</td></tr>`).join("")}</table></div>
      <p class="hint" style="margin:8px 0 0">${L.totals?`${L.totals.cached_answers} model calls, ${L.totals.tokens.toLocaleString()} tokens in total for all of the above.`:""} Small samples: read these as direction, not precision.</p></div></div>`;
    if(G.raw_llm){ $("#cmp-raw-load").textContent=`${G.raw_llm.loader_accepts}/${G.raw_llm.n} loaded (measured)`; $("#cmp-raw-solv").textContent=`${G.raw_llm.solvable}/${G.raw_llm.n} solvable (measured)`; }
    if(L.totals) $("#cost-llm").innerHTML=`<b>LLM:</b> optional. Measured on ${esc(L.model)}: ${L.totals.tokens.toLocaleString()} tokens for ${L.totals.cached_answers} calls, about ${Math.round(L.totals.tokens/L.totals.cached_answers).toLocaleString()} tokens per call; a request uses 1–4 calls. Run on a free-tier key.`;
  } else box.innerHTML=`<div class="note">Language-model measurements are produced by <span class="mono">bench/llm_evidence.py</span> and appear here once that script has been run with a key.</div>`;
})();
window.addEventListener("resize",()=>{ if(R&&R.frames&&!live) drawBoard($("#board"),R.width,R.height,R.frames[step].cells,R.frames[step].rules,R.frames[step].state); });