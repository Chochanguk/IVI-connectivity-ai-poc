<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type Device = {state:string, adb_ready:boolean, adb_path:string, model:string|null, android_version:string|null, message:string|null}
type Case = {id:string,name:string,purpose:string,steps:string,expected:string}
type Event = {id:string,time:string,level:string,tag:string,message:string}
type LogStats = {total:number,levels:Record<string,number>,timeline:{minute:string,total:number,warnings:number,errors:number}[],top_tags:{tag:string,count:number}[],signals:Record<string,{label:string,count:number,examples:Event[]}>,note:string}
type Session = {id:string,case_id:string,started_at:string,ended_at:string|null,status:string,actual_result:string,notes:string,screenshot:string,log_file:string|null,collection_state:string,analysis:any}
const tab = ref('개요')
const presentationMode = ref(false)
const tabs = ['개요','테스트 관리','로그 통계','로그 탐색','AI 진단','보고서']
const device = ref<Device|null>(null)
const cases = ref<Case[]>([])
const sessions = ref<Session[]>([])
const selected = ref('')
const chosenCase = ref('TC-01')
const events = ref<Event[]>([])
const stats = ref<LogStats|null>(null)
const level = ref('WEF')
const query = ref('')
const report = ref('')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const form = ref({status:'NOT_RUN',actual_result:'',notes:'',screenshot:''})
const statusLabel = (s:string) => ({PASS:'통과',FAIL:'실패',NOT_RUN:'미실행',BLOCKED:'진행 불가'} as Record<string,string>)[s] || s
const deviceLabel = (s?:string) => ({connected:'연결됨',disconnected:'연결 안 됨',unauthorized:'디버깅 승인 필요',multiple:'기기 여러 대',error:'오류'} as Record<string,string>)[s || ''] || '확인 중'
const collectionLabel = (s:string) => ({idle:'대기',collecting:'수집 중',stopped:'수집 종료',interrupted:'중단됨'} as Record<string,string>)[s] || s
function explainTerms(value:string):string {
  const terms:[RegExp,string][] = [
    [/adb forward --list(?!\s*\()/gi,'adb forward --list (포트 포워딩 목록 확인)'],
    [/adb devices(?!\s*\()/gi,'adb devices (연결된 기기 확인)'],
    [/adb logcat(?!\s*\()/gi,'adb logcat (안드로이드 시스템 로그 조회)'],
    [/focus audio off\/on(?!\s*\()/gi,'focus audio off/on (오디오 포커스 해제/복구)'],
    [/focus audio off(?!\s*\(|\/)/gi,'focus audio off (오디오 포커스 해제)'],
    [/focus audio on(?!\s*\()/gi,'focus audio on (오디오 포커스 복구)'],
    [/AudioFocus LOSS(?!\s*\()/gi,'AudioFocus LOSS (오디오 포커스 상실)'],
    [/AudioFocus Granted(?!\s*\()/gi,'AudioFocus Granted (오디오 포커스 획득)'],
    [/Ping timeout(?!\s*\()/gi,'Ping timeout (연결 응답 시간 초과)'],
    [/transport disconnect(?!\s*\()/gi,'transport disconnect (전송 연결 해제)'],
    [/shouldResumeOnAudioFocusGain=false(?!\s*\()/g,'shouldResumeOnAudioFocusGain=false (포커스 복구 후 자동 재개 안 함)'],
    [/\boff\/on\b(?!\s*\()/gi,'off/on (포커스 해제/복구)'],
    [/\bgain\b(?!\s*\()/gi,'gain (포커스 획득)'],
  ]
  return terms.reduce((text,[pattern,replacement])=>text.replace(pattern,replacement),value)
}
const current = computed(() => sessions.value.find(s => s.id === selected.value))
const currentCase = computed(() => cases.value.find(c => c.id === current.value?.case_id))
const counts = computed(() => Object.fromEntries(['PASS','FAIL','BLOCKED','NOT_RUN'].map(s => [s,sessions.value.filter(x => x.status === s).length])))
const maxMinute = computed(() => Math.max(1,...(stats.value?.timeline.map(x=>x.total)||[])))
const maxTag = computed(() => Math.max(1,...(stats.value?.top_tags.map(x=>x.count)||[])))
async function api<T>(url:string, options?:RequestInit):Promise<T> {
  const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options})
  if (!response.ok) { let detail = response.statusText; try { detail = (await response.json()).detail || detail } catch {} throw new Error(detail) }
  return response.json()
}
async function refresh() {
  const [d,c,s] = await Promise.all([api<Device>('/api/device'),api<Case[]>('/api/cases'),api<Session[]>('/api/sessions')])
  device.value=d; cases.value=c; sessions.value=s
  if (!selected.value && s.length) select(s[0].id)
  if (selected.value && !s.some(x=>x.id===selected.value)) selected.value=''
}
function select(id:string) {
  selected.value=id
  const s=sessions.value.find(x=>x.id===id)
  if (s) form.value={status:s.status,actual_result:s.actual_result,notes:s.notes,screenshot:s.screenshot}
  loadLogs()
  loadStats()
}
async function act(fn:()=>Promise<any>, message:string) {
  loading.value=true; error.value=''; notice.value=''
  try { await fn(); await refresh(); await Promise.all([loadLogs(),loadStats()]); notice.value=message }
  catch(e:any) { error.value=e.message || '요청 실패' }
  finally { loading.value=false }
}
async function createSession() { await act(async()=>{const s=await api<Session>('/api/sessions',{method:'POST',body:JSON.stringify({case_id:chosenCase.value})}); selected.value=s.id; form.value={status:'NOT_RUN',actual_result:'',notes:'',screenshot:''}},'세션이 생성됐습니다.') }
async function save() { if(!selected.value)return; await act(()=>api(`/api/sessions/${selected.value}`,{method:'PATCH',body:JSON.stringify(form.value)}),'결과를 저장했습니다.') }
async function collect(mode:'start'|'stop') { if(!selected.value)return; await act(()=>api(`/api/sessions/${selected.value}/logs/${mode}`,{method:'POST'}),mode==='start'?'Logcat 수집 중입니다.':'Logcat 수집을 중지했습니다.') }
async function loadLogs() { if(!selected.value){events.value=[];return} try { events.value=await api<Event[]>(`/api/sessions/${selected.value}/logs?level=${level.value}&q=${encodeURIComponent(query.value)}`) } catch {events.value=[]} }
async function loadStats() { if(!selected.value){stats.value=null;return} try { stats.value=await api<LogStats>(`/api/sessions/${selected.value}/log-stats`) } catch {stats.value=null} }
async function diagnose(use_ai:boolean) { if(!selected.value)return; await act(()=>api(`/api/sessions/${selected.value}/analyze`,{method:'POST',body:JSON.stringify({use_ai})}),'진단 결과를 저장했습니다.') }
async function loadReport() { try { const r=await fetch('/api/report'); report.value=await r.text() } catch(e:any) {error.value=e.message} }
function download(content:string,name:string) {const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([content],{type:'text/plain;charset=utf-8'})); a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
async function downloadLogs() {if(!selected.value)return;const r=await fetch(`/api/sessions/${selected.value}/logs/download`);download(await r.text(),`${selected.value}-masked.log`)}
onMounted(()=>{act(refresh,'');setInterval(()=>{refresh().catch(()=>{})},10000)})
</script>

<template>
<div :class="['shell',presentationMode?'presentation-mode':'']">
  <aside class="sidebar"><div class="brand"><span class="mark">IVI</span><div>폰 연결<br><small>검증 도구</small></div></div><div class="side-label">작업 메뉴</div><button v-for="item in tabs" :key="item" :class="['nav',tab===item?'active':'']" @click="tab=item; if(item==='보고서')loadReport(); if(item==='로그 탐색')loadLogs(); if(item==='로그 통계'||item==='AI 진단')loadStats()">{{item}}</button><div class="side-bottom"><span class="dot"></span> 로컬 PoC<br><small>실제 데이터 / 테스트 기록</small></div></aside>
  <main><header><div><div class="eyebrow">개발자용 검증 대시보드 / Android Auto DHU</div><h1>{{presentationMode?'IVI 연결 검증과 AI 진단':tab}}</h1></div><div class="header-right"><span class="pill">{{deviceLabel(device?.state)}}</span><button v-if="!presentationMode" class="ghost" @click="act(refresh,'새로고침 완료')">새로고침</button></div></header>
  <div v-if="error" class="alert error">{{error}}</div><div v-if="notice" class="alert">{{notice}}</div>
  <section v-if="tab==='개요'"><div class="section-head"><h2>시스템 현황</h2><span>10초마다 새로고침 · DHU 연결 성공은 수동 확인</span></div><div class="metrics"><article class="metric"><div>기기 연결 상태</div><strong>{{deviceLabel(device?.state)}}</strong><small>{{device?.message || device?.model || '장치 정보 조회 중'}}</small></article><article class="metric"><div>ADB 상태</div><strong>{{device?.adb_ready?'준비됨':'사용 불가'}}</strong><small>{{device?.adb_path}}</small></article><article class="metric"><div>테스트 세션</div><strong>{{sessions.length}}</strong><small>통과 {{counts.PASS}} · 실패 {{counts.FAIL}} · 진행 불가 {{counts.BLOCKED}}</small></article><article class="metric"><div>안드로이드 버전</div><strong>{{device?.android_version || '—'}}</strong><small>실제 ADB 조회 결과</small></article></div><div class="grid-two"><article class="panel"><h3>최근 테스트</h3><div v-if="!sessions.length" class="empty">아직 실행한 테스트가 없습니다.</div><button v-for="s in sessions.slice(0,5)" :key="s.id" class="row" @click="select(s.id);tab='테스트 관리'"><span>{{s.case_id}} · {{cases.find(c=>c.id===s.case_id)?.name}}</span><b :class="s.status.toLowerCase()">{{statusLabel(s.status)}}</b></button></article><article class="panel"><h3>최근 진단</h3><div v-if="!sessions.some(s=>s.analysis)" class="empty">아직 진단 결과가 없습니다.</div><div v-for="s in sessions.filter(s=>s.analysis).slice(0,3)" :key="s.id" class="analysis-row"><span>{{s.case_id}} · {{s.analysis.source==='openai'?'OpenAI':'규칙 기반'}}</span><p>{{s.analysis.result.summary}}</p></div></article></div></section>
  <section v-if="tab==='테스트 관리'"><div class="section-head"><h2>테스트 실행 및 기록</h2><span>판정은 실제 관찰 후 입력</span></div><div class="toolbar"><select v-model="chosenCase"><option v-for="c in cases" :value="c.id">{{c.id}} · {{c.name}}</option></select><button class="primary" :disabled="loading" @click="createSession">+ 세션 시작</button></div><div class="grid-two"><article class="panel"><h3>테스트 시나리오</h3><div v-for="c in cases" :key="c.id" class="case"><div><b>{{c.id}}</b> {{c.name}}</div><small>{{c.purpose}}</small><p>{{c.steps}}</p><small>기대 결과: {{c.expected}}</small></div></article><article class="panel"><h3>실행 세션</h3><div v-if="!sessions.length" class="empty">세션을 시작하세요.</div><button v-for="s in sessions" :key="s.id" :class="['row',selected===s.id?'selected':'']" @click="select(s.id)"><span>{{s.case_id}} · {{new Date(s.started_at).toLocaleString('ko-KR')}}</span><b :class="s.status.toLowerCase()">{{statusLabel(s.status)}}</b></button><div v-if="current" class="editor"><div class="subhead">{{currentCase?.name}} <span>{{collectionLabel(current.collection_state)}}</span></div><p>기대 결과: {{currentCase?.expected}}</p><div class="buttons"><button class="primary" :disabled="loading || !!current.log_file" @click="collect('start')">로그 수집 시작</button><button class="ghost" :disabled="loading || current.collection_state!=='collecting'" @click="collect('stop')">로그 수집 중지</button></div><label>판정<select v-model="form.status"><option v-for="s in ['NOT_RUN','PASS','FAIL','BLOCKED']" :value="s">{{statusLabel(s)}}</option></select></label><label>실제 결과<textarea v-model="form.actual_result" placeholder="직접 관찰한 현상을 기록하세요"/></label><label>메모<textarea v-model="form.notes"/></label><label>스크린샷 파일명<input v-model="form.screenshot" placeholder="results/screenshots/..."/></label><button class="primary" :disabled="loading" @click="save">결과 저장</button></div></article></div></section>
  <section v-if="tab==='로그 통계'">
    <div class="section-head"><h2>세션 로그 통계</h2><span>전체 Logcat 집계 · 원인 판정과 분리</span></div>
    <div class="toolbar"><select v-model="selected" @change="loadStats"><option value="">세션 선택</option><option v-for="s in sessions" :value="s.id">{{s.case_id}} · {{new Date(s.started_at).toLocaleString('ko-KR')}}</option></select><button class="ghost" :disabled="!selected" @click="loadStats">통계 갱신</button></div>
    <template v-if="stats">
      <article class="panel volume-panel">
        <div class="volume-head"><div><div class="eyebrow">LOGCAT ACTIVITY</div><h3>시간별 로그 흐름</h3></div><div class="chart-legend"><span><i class="legend-normal"></i>일반</span><span><i class="legend-warning"></i>경고</span><span><i class="legend-error"></i>오류</span></div></div>
        <div class="stat-summary"><div><small>전체 로그</small><strong>{{stats.total.toLocaleString()}}</strong></div><div><small>경고</small><strong>{{(stats.levels.W||0).toLocaleString()}}</strong></div><div><small>오류</small><strong>{{((stats.levels.E||0)+(stats.levels.F||0)).toLocaleString()}}</strong></div><div><small>연결 관련</small><strong>{{(stats.signals.connection?.count||0).toLocaleString()}}</strong></div></div>
        <div v-if="!stats.timeline.length" class="empty">수집 로그가 없습니다.</div>
        <div v-else class="volume-chart" role="img" aria-label="분당 전체 로그량과 경고·오류 비율을 보여주는 막대 그래프">
          <div v-for="m in stats.timeline" :key="m.minute" class="volume-column" :title="`${m.minute} 전체 ${m.total}건, 경고 ${m.warnings}건, 오류 ${m.errors}건`">
            <strong>{{m.total.toLocaleString()}}</strong>
            <div class="volume-track"><div class="volume-stack" :style="{height:(100*m.total/maxMinute)+'%'}"><span class="volume-normal" :style="{height:(100*(m.total-m.warnings-m.errors)/m.total)+'%'}"></span><span class="volume-warning" :style="{height:(100*m.warnings/m.total)+'%'}"></span><span class="volume-error" :style="{height:(100*m.errors/m.total)+'%'}"></span></div></div>
            <span class="volume-time">{{m.minute.slice(6)}}</span><small>경고 {{m.warnings.toLocaleString()}} · 오류 {{m.errors.toLocaleString()}}</small>
          </div>
        </div>
      </article>
      <p class="stats-note">{{stats.note}}</p>
      <div class="grid-two"><article class="panel"><h3>경고·오류 상위 태그</h3><div v-if="!stats.top_tags.length" class="empty">경고·오류가 없습니다.</div><div v-for="t in stats.top_tags" :key="t.tag" class="chart-row"><span :title="t.tag">{{t.tag}}</span><div class="chart-track"><div class="chart-fill warn" :style="{width:(100*t.count/maxTag)+'%'}"></div></div><b>{{t.count.toLocaleString()}}</b></div></article><article class="panel"><h3>직무 관련 이벤트 분류</h3><div v-for="(group,key) in stats.signals" :key="key" class="category-row"><span>{{group.label}}</span><div class="category-track"><div :class="['category-fill',key]" :style="{width:(100*group.count/Math.max(1,...Object.values(stats.signals).map(x=>x.count)))+'%'}"></div></div><strong>{{group.count.toLocaleString()}}</strong></div><small class="category-note">태그·문구 기준으로 분류한 로그 건수</small></article></div>
      <article class="panel signal-panel"><h3>근거 로그 예시</h3><div class="signal-grid"><div v-for="(group,key) in stats.signals" :key="key"><h4>{{group.label}} <strong>{{group.count.toLocaleString()}}건</strong></h4><p v-for="e in group.examples" :key="e.id" class="signal-example"><b>{{e.id}}</b> {{e.time}} · {{e.tag}}: {{e.message}}</p><p v-if="!group.examples.length">경고·오류 예시는 없습니다.</p></div></div></article>
    </template><div v-else class="empty large">세션을 선택하면 수집된 로그의 통계가 표시됩니다.</div>
  </section>
  <section v-if="tab==='로그 탐색'"><div class="section-head"><h2>마스킹된 Logcat 이벤트</h2><span>원본은 로컬 results/logs에만 저장</span></div><div class="toolbar"><select v-model="selected" @change="loadLogs"><option value="">세션 선택</option><option v-for="s in sessions" :value="s.id">{{s.case_id}} · {{new Date(s.started_at).toLocaleString('ko-KR')}}</option></select><select v-model="level" @change="loadLogs"><option value="WEF">경고 / 오류</option><option value="VDIWEF">전체</option></select><input v-model="query" @keyup.enter="loadLogs" placeholder="태그 또는 메시지 검색"><button class="ghost" @click="loadLogs">검색</button><button class="ghost" :disabled="!selected" @click="downloadLogs">마스킹된 로그 다운로드</button></div><article class="panel"><div v-if="!events.length" class="empty">표시할 로그가 없습니다. 세션과 필터를 확인하세요.</div><div v-for="e in events" :key="e.id" class="log-row"><span class="log-id">{{e.id}}</span><span>{{e.time}}</span><b :class="e.level==='E'||e.level==='F'?'fail':'blocked'">{{e.level}}</b><span>{{e.tag}}</span><code>{{e.message}}</code></div></article></section>
  <section v-if="tab==='AI 진단'" class="diagnostic-section">
    <div class="section-head"><h2>로그 기반 진단</h2><span>관찰 사실 · 통계 · AI 원인 후보를 구분</span></div>
    <div class="toolbar diagnostic-toolbar"><select v-model="selected" @change="loadStats"><option value="">세션 선택</option><option v-for="s in sessions" :value="s.id">{{s.case_id}} · {{statusLabel(s.status)}} · {{new Date(s.started_at).toLocaleString('ko-KR')}}</option></select><button v-if="!presentationMode" class="ghost" :disabled="!selected||loading" @click="diagnose(false)">규칙 기반 진단</button><button v-if="!presentationMode" class="primary" :disabled="!selected||loading" @click="diagnose(true)">AI 진단 실행</button><button class="ghost" @click="presentationMode=!presentationMode">{{presentationMode?'일반 보기':'발표용 보기'}}</button></div>
    <div class="diagnostic-board">
      <article class="panel diagnostic-stat-panel">
        <div class="board-heading"><div class="eyebrow">01 · 측정 데이터</div><h3>세션 로그 통계</h3><small>실제 스마트폰 Logcat (안드로이드 시스템 로그)</small></div>
        <template v-if="stats"><div class="board-metrics"><div><span>전체 로그</span><strong>{{stats.total.toLocaleString()}}</strong></div><div><span>경고</span><strong>{{(stats.levels.W||0).toLocaleString()}}</strong></div><div><span>오류</span><strong>{{((stats.levels.E||0)+(stats.levels.F||0)).toLocaleString()}}</strong></div></div>
          <div class="board-chart-title">분당 로그량 <small>일반 / 경고 / 오류</small></div>
          <div class="board-chart" role="img" aria-label="분당 로그량 막대 그래프"><div v-for="m in stats.timeline.slice(-8)" :key="m.minute" class="board-bar"><b>{{m.total.toLocaleString()}}</b><div class="board-bar-track"><div class="board-bar-stack" :style="{height:(100*m.total/maxMinute)+'%'}"><span class="volume-normal" :style="{height:(100*(m.total-m.warnings-m.errors)/m.total)+'%'}"></span><span class="volume-warning" :style="{height:(100*m.warnings/m.total)+'%'}"></span><span class="volume-error" :style="{height:(100*m.errors/m.total)+'%'}"></span></div></div><span>{{m.minute.slice(6)}}</span></div></div>
          <div class="board-signals"><div><span>연결·전송</span><b>{{stats.signals.connection?.count||0}}건</b></div><div><span>오디오 포커스</span><b>{{stats.signals.audio?.count||0}}건</b></div><div><span>화면·비디오</span><b>{{stats.signals.display?.count||0}}건</b></div></div><p class="board-caution">로그 건수와 경고는 장애 원인이나 실패 횟수를 뜻하지 않습니다.</p>
        </template><div v-else class="empty">선택한 세션의 수집 로그가 없습니다.</div>
      </article>
      <article class="panel diagnostic-ai-panel">
        <div class="board-heading"><div class="eyebrow">02 · 분석 보조</div><h3>AI 진단 결과</h3><small v-if="current?.analysis">{{current.analysis.source==='openai'?'OpenAI · '+current.analysis.model:'규칙 기반'}} · {{new Date(current.analysis.created_at).toLocaleString('ko-KR')}}</small></div>
        <template v-if="current?.analysis"><div class="board-summary">{{explainTerms(current.analysis.result.summary)}}</div><div class="board-block"><h4>관찰 사실</h4><p v-for="x in current.analysis.result.observations.slice(0,2)" :key="x">{{explainTerms(x)}}</p></div><div class="board-block"><h4>원인 후보 <small>미검증</small></h4><div v-for="h in current.analysis.result.hypotheses.slice(0,2)" :key="h.cause" class="board-hypothesis"><b>{{explainTerms(h.cause)}}</b><p>근거 로그 {{h.evidence_ids.join(', ') || '없음'}} · 확인 방법 {{explainTerms(h.next_step)}}</p></div><p v-if="!current.analysis.result.hypotheses.length">현재 근거로 특정 원인 후보를 제시하기 어렵습니다.</p></div><div class="board-block"><h4>다음 검증</h4><p v-for="x in current.analysis.result.next_steps.slice(0,2)" :key="x">{{explainTerms(x)}}</p></div><div class="board-limit">판단 한계: {{explainTerms(current.analysis.result.limitations[0] || '로그만으로 내부 상태를 확정할 수 없습니다.')}}</div></template>
        <div v-else class="empty">저장된 진단이 없습니다. 일반 보기에서 진단을 실행하세요.</div>
      </article>
    </div><p class="board-footnote">실기기와 공식 DHU를 이용한 개발자용 PoC · AI의 원인 후보는 추가 검증이 필요합니다.</p>
  </section>
  <section v-if="tab==='보고서'"><div class="section-head"><h2>테스트 보고서</h2><div class="section-actions"><button class="primary" @click="loadReport">보고서 갱신</button><button class="ghost" :disabled="!report" @click="download(report,'ivi-test-report.md')">다운로드</button></div></div><pre class="report">{{report}}</pre></section>
  </main>
</div>
</template>
