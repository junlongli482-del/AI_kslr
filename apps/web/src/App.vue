<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { BookOpen, ScanLine, Library, Files, Plus, ArrowUpRight, ArrowLeft, ArrowRight, UploadCloud, FileText, Check, CheckCheck, Search, RefreshCw, Settings2, ChevronRight, CircleAlert, LoaderCircle, Save, Split, Merge, Trash2, PanelLeftClose, ClipboardCheck, X, ExternalLink, Grip } from 'lucide-vue-next'
import type { Task, Question, Result } from './types'
import { renderMarkdown } from './render'
import { prepareEditorDocument } from './render'
import { repairQuestionDraft } from './repair'
import QuestionEditor from './components/QuestionEditor.vue'
import SourceViewer from './components/SourceViewer.vue'
import ComparisonPanel from './components/ComparisonPanel.vue'
import QuestionPreview from './components/QuestionPreview.vue'

const api=axios.create({baseURL:'/api',timeout:120000})
const showMobileSource=ref(false)
const view=ref('tasks'),tasks=ref<Task[]>([]),busy=ref(false),task=ref<Task|null>(null)
const result=ref<Result|null>(null),revision=ref(0),selectedId=ref(''),tab=ref('content'),filter=ref('all'),paperFilter=ref(''),search=ref(''),saveState=ref('已保存'),answerDoc=ref('')
const createDialog=ref(false),newTitle=ref(''),newMode=ref('textbook'),generate=ref(false),policy=ref('deepseek'),questionFiles=ref<File[]>([]),answerFiles=ref<File[]>([])
const bank=ref<any[]>([]),bankSearch=ref(''),detail=ref<any|null>(null),detailDialog=ref(false),issuesDialog=ref(false),validationIssues=ref<any[]>([])
const concurrency=ref<{max_concurrency:number;running:number;queued:number}|null>(null)
const concurrencyUnlimited=ref(true),concurrencyLimit=ref(3),concurrencyBusy=ref(false),concurrencyError=ref('')
const concurrencyEdited=ref(false)
const comparison=ref<any>(null),clockNow=ref(Date.now())
const selected=computed(()=>result.value?.questions.find(q=>q.id===selectedId.value)||null)
const reviewed=computed(()=>result.value?.questions.filter(q=>q.review_status==='reviewed').length||0)
const shownQuestions=computed(()=>result.value?.questions.filter(q=>(!paperFilter.value||q.paper_id===paperFilter.value)&&(filter.value!=='pending'||q.review_status!=='reviewed')&&(!search.value||q.number.includes(search.value)||q.stem.includes(search.value)))||[])
const running=computed(()=>tasks.value.filter(t=>t.status==='running').length)
const ready=computed(()=>tasks.value.filter(t=>t.status==='ready').length)
let timer:ReturnType<typeof setInterval>|undefined,saveTimer:ReturnType<typeof setTimeout>|undefined,loadingDraft=false,dirty=false
let savePromise:Promise<void>|null=null
const modeName=(mode:string)=>({textbook:'教辅卷 / 作业',questions:'仅录题目',paper:'普通整卷'}[mode]||mode)
const statusName=(status:string)=>({running:'处理中',queued:'等待并发名额',pending:'正在准备',ready:'待审核',committed:'已入库',uploaded:'待处理',failed:'处理失败',interrupted:'待恢复'}[status]||status)
const formatDate=(s:string)=>s?.slice(5,16).replace('T',' ')
function error(e:any){
  const data=e.response?.data
  let issues=data?.issues
  if(!issues&&typeof data?.message==='string'){try{const parsed=JSON.parse(data.message);if(Array.isArray(parsed))issues=parsed}catch{}}
  if(Array.isArray(issues)){validationIssues.value=issues;issuesDialog.value=true;return}
  ElMessage.error(data?.message||e.message||'操作失败，请重试')
}
const fieldName=(field:string)=>({stem:'题干',options:'选项',subquestions:'小问',answer:'答案',analysis:'解析',editor_documents:'编辑内容'}[field]||field)
function issueLocation(issue:any){const q=result.value?.questions.find(q=>q.id===issue.question_id);return q?`第 ${q.number} 题`:'整份资料'}

async function loadTasks(){try{tasks.value=(await api.get('/quick-entry/tasks')).data}catch(e){error(e)}}
async function loadConcurrency(){
  try{concurrency.value=(await api.get('/quick-entry/settings/concurrency')).data;concurrencyError.value=''
    if(!concurrencyEdited.value){concurrencyUnlimited.value=concurrency.value!.max_concurrency===0;concurrencyLimit.value=concurrency.value!.max_concurrency||3}
  }catch{concurrencyError.value='无法读取并发设置，请确认处理服务已启动后重新加载'}
}
async function saveConcurrency(){
  if(!concurrencyUnlimited.value&&(!Number.isInteger(concurrencyLimit.value)||concurrencyLimit.value<1)){ElMessage.warning('请输入大于0的整数');return}
  concurrencyBusy.value=true
  try{concurrency.value=(await api.put('/quick-entry/settings/concurrency',{max_concurrency:concurrencyUnlimited.value?0:concurrencyLimit.value})).data;concurrencyEdited.value=false;concurrencyError.value='';ElMessage.success('并发设置已生效，等待中的任务会自动按新设置启动')}
  catch(e){error(e)}finally{concurrencyBusy.value=false}
}
async function navigate(next:string){if(view.value==='review'){await saveDraft();if(dirty)return}view.value=next;detail.value=null;if(next==='tasks')await loadTasks();else if(next==='questions'||next==='papers')await loadBank()}
async function loadBank(){try{bank.value=(await api.get(view.value==='papers'?'/paperbank/papers':'/questionbank/questions',{params:{query:bankSearch.value}})).data}catch(e){error(e)}}
function normalizeSubAnswers(r:Result){
  for(const q of r.questions){
    for(const sub of q.subquestions||[]){
      const raw:any=sub.answer
      if(!raw||typeof raw!=='object')sub.answer={value:String(raw||''),analysis:String((sub as any).analysis||''),scoring_criteria:null,source:String((sub as any).answer_source||'')}
      sub.answer.value??='';sub.answer.analysis??=''
    }
  }
}
async function openTask(t:Task){
  comparison.value=null
  if(t.status!=='ready'&&t.status!=='committed'){
    try{task.value=(await api.get(`/quick-entry/tasks/${t.id}`)).data;comparison.value=(await api.get(`/quick-entry/tasks/${t.id}/comparison`).catch(()=>({data:null}))).data;view.value='progress'}catch(e){error(e)}return
  }
  busy.value=true;loadingDraft=true
  let repaired=false
  try{const response=await api.get(`/quick-entry/tasks/${t.id}/review`);result.value=response.data.result;revision.value=response.data.revision;task.value=t;
    const prepared=await api.post(`/quick-entry/tasks/${t.id}/validate`,result.value);if(prepared.data.result){repaired=JSON.stringify(result.value)!==JSON.stringify(prepared.data.result);result.value=prepared.data.result}
    normalizeSubAnswers(result.value!)
    comparison.value=(await api.get(`/quick-entry/tasks/${t.id}/comparison`).catch(()=>({data:null}))).data;
    for(const q of result.value!.questions)if(repairQuestionDraft(q,result.value!.documents))repaired=true
    selectedId.value=result.value!.questions[0]?.id||'';paperFilter.value='';filter.value='all';view.value='review';saveState.value='已保存';dirty=false}
  catch(e){error(e)}finally{busy.value=false;setTimeout(()=>{loadingDraft=false;if(repaired)markDirty()},80)}
}
function addFiles(files:File[],role:string){
  const target=role==='answer'?answerFiles.value:questionFiles.value
  const valid=files.filter(f=>/\.(pdf|jpe?g|png|docx?)$/i.test(f.name))
  if(valid.length!==files.length)ElMessage.warning('仅支持 PDF、JPG、PNG、Word 文件')
  for(const file of valid)if(!target.some(f=>f.name===file.name&&f.size===file.size&&f.lastModified===file.lastModified))target.push(file)
}
function chooseFiles(event:Event,role:string){addFiles(Array.from((event.target as HTMLInputElement).files||[]),role);(event.target as HTMLInputElement).value=''}
function dropFiles(event:DragEvent,role='question'){event.preventDefault();addFiles(Array.from(event.dataTransfer?.files||[]),role)}
async function createTask(){
  if(!questionFiles.value.length){ElMessage.warning('请先添加题目文件');return}
  busy.value=true
  try{
    const response=await api.post('/quick-entry/tasks',{title:newTitle.value||questionFiles.value[0].name.replace(/\.[^.]+$/,''),mode:newMode.value,generate_answers:generate.value,channel_policy:policy.value})
    const id=response.data.id
    for(const [files,role] of [[questionFiles.value,'question'],[answerFiles.value,'answer']] as const){
      if(files.length){const form=new FormData();files.forEach(f=>form.append('files',f));form.append('role',role);await api.post(`/quick-entry/tasks/${id}/files`,form)}
    }
    await api.post(`/quick-entry/tasks/${id}/start`);createDialog.value=false;questionFiles.value=[];answerFiles.value=[];newTitle.value='';await loadTasks();await openTask(tasks.value.find(t=>t.id===id)!);ElMessage.success('任务已开始，可以离开页面，结果会自动保留')
  }catch(e){error(e)}finally{busy.value=false}
}
function markDirty(){if(loadingDraft||!result.value||view.value!=='review')return;dirty=true;saveState.value='待保存';if(saveTimer)clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveDraft(),1200)}
watch(result,markDirty,{deep:true})
async function saveDraft(){
  if(saveTimer){clearTimeout(saveTimer);saveTimer=undefined}
  if(savePromise){await savePromise;if(dirty&&saveState.value!=='保存失败')await saveDraft();return}
  if(!dirty||!result.value||!task.value)return
  savePromise=(async()=>{
    while(dirty&&result.value&&task.value){
      dirty=false;saveState.value='保存中'
      const id=task.value.id,snapshot=JSON.parse(JSON.stringify(result.value))
      try{const response=await api.put(`/quick-entry/tasks/${id}/review`,{expected_revision:revision.value,result:snapshot});revision.value=response.data.revision;saveState.value=dirty?'待保存':'已保存'}
      catch(e){dirty=true;saveState.value='保存失败';error(e);break}
    }
  })()
  try{await savePromise}finally{savePromise=null}
}
async function saveNow(){if(saveTimer)clearTimeout(saveTimer);await saveDraft();if(saveState.value==='已保存')ElMessage.success('草稿已保存')}
function select(id:string){selectedId.value=id;tab.value='content';answerDoc.value=''}
function nextQuestion(delta:number){const qs=result.value?.questions||[];const index=qs.findIndex(q=>q.id===selectedId.value);if(qs[index+delta])select(qs[index+delta].id)}
function confirmQuestion(){if(selected.value){selected.value.review_status='reviewed';nextQuestion(1)}}
function updateImageReferences(change:{removed:string[];added:string[]}){
  if(!selected.value)return
  const excluded=new Set(selected.value.excluded_image_urls||[])
  change.removed.forEach(url=>excluded.add(url));change.added.forEach(url=>excluded.delete(url))
  if(change.removed.length||change.added.length)selected.value.excluded_image_urls=[...excluded]
}
function updateImageLayout(change:{src:string;widthPct:number;manual:boolean}){
  if(!selected.value)return
  const layout=selected.value.image_layout??={}
  layout[change.src]??={}
  if(change.manual)layout[change.src].manual_width_pct=change.widthPct
  else delete layout[change.src].manual_width_pct
  markDirty()
}
function insertRegionImage(url?:string){
  if(!url||!selected.value)return
  const q=selected.value
  if(q.stem.includes(url)){ElMessage.info('这张区域图片已经在题干中');return}
  q.stem+=`\n\n![](${url})`
  if(q.editor_documents.stem)q.editor_documents.stem=prepareEditorDocument(q.editor_documents.stem,q.stem,q.image_layout)
  q.review_status='pending';markDirty();ElMessage.success('原卷区域已插入题干，可继续编辑')
}
function addSubquestion(){
  if(!selected.value)return
  const q=selected.value
  const next=q.subquestions.length+1
  q.subquestions.push({subquestion_id:`${q.id}-(${next})`,number:`(${next})`,stem:'',options:[],answer:{value:'',analysis:'',scoring_criteria:null,source:'missing'},answer_entry_id:null,score:null,requires_manual_drawing_review:false})
  q.attributes.question_type=q.attributes.question_type||'复合题'
  q.attributes.group_type=q.attributes.group_type||'material_question_group'
  q.review_status='pending';markDirty()
}
function removeSubquestion(index:number){
  if(!selected.value)return
  selected.value.subquestions.splice(index,1)
  selected.value.review_status='pending';markDirty()
}
function matchSubAnswer(entryId:string,index:number){
  if(!selected.value||!result.value)return
  const sub=selected.value.subquestions[index];const entry=result.value.answer_entries.find(e=>e.id===entryId)
  if(!sub||!entry)return
  const other=result.value.questions.some(q=>q!==selected.value&&q.subquestions?.some(s=>s.answer_entry_id===entryId))
  if(other){ElMessage.warning('此答案已关联其他小问，请先解除原关联');return}
  sub.answer_entry_id=entryId;sub.answer={value:entry.answer||'',analysis:entry.analysis||'',scoring_criteria:entry.scoring_criteria??null,source:'answer_file'};entry.matched_question_id=selected.value.id;entry.matched_subquestion_id=sub.subquestion_id||sub.number;result.value.unmatched_answer_entry_ids=result.value.answer_entries.filter(e=>!e.matched_question_id).map(e=>e.id);selected.value.review_status='pending';markDirty()
}
async function recognizeRegion(regionIndex:number, subquestionIndex:number|null=null){
  if(!task.value||!selected.value)return
  try{
    await saveDraft();if(dirty)return
    const response=await api.post(`/quick-entry/tasks/${task.value.id}/region-recognize`,{question_id:selected.value.id,region_index:regionIndex,channel:'deepseek',target:subquestionIndex==null?'stem':'subquestion',subquestion_index:subquestionIndex})
    const candidate=response.data.result||{}
    const target=subquestionIndex==null?selected.value:selected.value.subquestions[subquestionIndex]
    if(!target)return
    await ElMessageBox.confirm('模型已返回区域识别结果，确认写入当前编辑内容吗？','确认区域识别',{confirmButtonText:'写入',cancelButtonText:'取消'})
    if(candidate.stem)target.stem=candidate.stem
    if(candidate.options)target.options=candidate.options
    if(candidate.answer!==undefined){if(subquestionIndex!=null)(target as any).answer.value=candidate.answer;else (target as any).answer=candidate.answer}
    if(candidate.analysis!==undefined){if(subquestionIndex!=null)(target as any).answer.analysis=candidate.analysis;else (target as any).analysis=candidate.analysis}
    if(subquestionIndex!=null)(target as any).answer.source='manual';else{selected.value.answer_source='manual';selected.value.analysis_source='manual'}
    selected.value.review_status='pending';markDirty();ElMessage.success('区域识别结果已写入，请核对')
  }catch(e:any){if(e!=='cancel'&&e!=='close')error(e)}
}

function newQuestion(){if(!result.value)return;const q:Question={id:'manual-'+Date.now(),paper_id:paperFilter.value||result.value.papers[0]?.id||'',number:String(result.value.questions.length+1),stem:'',options:[],subquestions:[],regions:[],attributes:{knowledge_status:'unconfigured',knowledge_points:[],extension_attributes:[]},answer:'',analysis:'',answer_source:'missing',review_status:'pending',issues:[],editor_documents:{},block_ids:[]};result.value.questions.push(q);select(q.id)}
async function removeQuestion(){if(!selected.value||!result.value)return;try{await ElMessageBox.confirm('删除此识别题目及其题框关联？原始文件会保留。','删除误识别题目',{type:'warning'});const index=result.value.questions.findIndex(q=>q.id===selectedId.value);result.value.questions.splice(index,1);selectedId.value=result.value.questions[Math.min(index,result.value.questions.length-1)]?.id||''}catch{}}
function mergeNext(){if(!selected.value||!result.value)return;const index=result.value.questions.findIndex(q=>q.id===selectedId.value),next=result.value.questions[index+1];if(!next){ElMessage.info('没有下一道题');return}const q=selected.value;if(q.paper_id!==next.paper_id){ElMessage.warning('不同试卷题目不能合并');return}q.stem+='\n\n'+next.stem;q.regions.push(...next.regions);q.block_ids.push(...next.block_ids);q.subquestions.push(...next.subquestions);if(next.answer)q.answer+='\n'+next.answer;if(next.analysis)q.analysis+='\n'+next.analysis;q.editor_documents={};q.review_status='pending';result.value.questions.splice(index+1,1);ElMessage.success('已合并内容与区域，请核对答案')}
function splitQuestion(){if(!selected.value||!result.value)return;const q=selected.value;if(q.regions.length<2){ElMessage.info('至少两个区域才能按最后区域拆分，可先补框');return}const copy=structuredClone(JSON.parse(JSON.stringify(q))) as Question;copy.id='manual-'+Date.now();copy.number=q.number+'-2';copy.regions=[q.regions.pop()!];copy.stem='请从原题中剪切属于本题的内容';copy.options=[];copy.subquestions=[];copy.answer='';copy.analysis='';copy.answer_entry_id=undefined;copy.answer_source='missing';copy.analysis_source='missing';copy.attributes.score=null;copy.editor_documents={};copy.block_ids=[];copy.review_status='pending';q.review_status='pending';result.value.questions.splice(result.value.questions.indexOf(q)+1,0,copy);ElMessage.info('已拆出最后区域，请校对两题内容')}
function reorder(delta:number){if(!result.value||!selected.value)return;const qs=result.value.questions,index=qs.indexOf(selected.value);if(qs[index+delta]){[qs[index],qs[index+delta]]=[qs[index+delta],qs[index]]}}
function matchAnswer(entryId:string){if(!selected.value||!result.value)return;const q=selected.value;const old=result.value.answer_entries.find(e=>e.id===q.answer_entry_id);const entry=result.value.answer_entries.find(e=>e.id===entryId);if(entryId&&!entry)return;const other=result.value.questions.find(x=>x.id!==q.id&&x.answer_entry_id===entryId);if(entryId&&other){ElMessage.warning(`此答案已关联第 ${other.number} 题，请先解除原关联`);return}if(old)delete old.matched_question_id;q.answer_entry_id=entryId||undefined;q.answer=entry?.answer||'';q.analysis=entry?.analysis||'';q.answer_source=entry?(result.value.documents.find(d=>d.id===entry.document_id)?.role==='answer'?'answer_file':'original'):'missing';q.analysis_source=q.analysis?q.answer_source:'missing';if(entry)entry.matched_question_id=q.id;result.value.unmatched_answer_entry_ids=result.value.answer_entries.filter(e=>!e.matched_question_id).map(e=>e.id);q.editor_documents={...q.editor_documents,answer:undefined,analysis:undefined};q.review_status='pending';answerDoc.value=entry?.document_id||''}
async function validate(){if(!task.value||!result.value)return;await saveDraft();busy.value=true;try{const checked=(await api.post(`/quick-entry/tasks/${task.value.id}/validate`,result.value)).data;validationIssues.value=checked.issues;if(checked.result){result.value=checked.result;markDirty()}issuesDialog.value=true}catch(e){error(e)}finally{busy.value=false}}
async function refreshRegions(){
  markDirty();if(!task.value||!result.value)return
  const id=task.value.id,snapshot=JSON.parse(JSON.stringify(result.value))
  try{const response=await api.post(`/quick-entry/tasks/${id}/validate`,snapshot);if(task.value?.id!==id)return
    for(const q of result.value.questions){const checked=response.data.result?.questions.find((x:Question)=>x.id===q.id);if(checked&&JSON.stringify(q.regions.map(r=>r.bbox))===JSON.stringify(checked.regions.map((r: any)=>r.bbox)))q.regions=checked.regions}
  }catch(e){error(e)}
}
async function commit(){if(!task.value||!result.value)return;await saveDraft();if(saveState.value!=='已保存')return;try{await ElMessageBox.confirm(`将 ${result.value.questions.length} 道题${task.value.mode==='questions'?'':`、${result.value.papers.length} 份试卷`}保存到资源库。其中 ${result.value.questions.filter(q=>q.review_status!=='reviewed').length} 道仍待人工核对，保存后保留审核状态。缺少答案的题目标记为待完善。`,'确认入库',{confirmButtonText:'保存到资源库',cancelButtonText:'继续审核'});busy.value=true;const response=await api.post(`/quick-entry/tasks/${task.value.id}/commit`,{revision:revision.value});ElMessage.success(`已保存 ${response.data.questions} 道题、${response.data.papers} 份试卷`);task.value.status='committed';await loadTasks()}catch(e:any){if(e!=='cancel'&&e!=='close')error(e)}finally{busy.value=false}}
async function retry(){if(!task.value)return;busy.value=true;try{task.value=(await api.post(`/quick-entry/tasks/${task.value.id}/retry`)).data;ElMessage.success('正在恢复任务，已完成识别结果将复用')}catch(e){error(e)}finally{busy.value=false}}
async function openDetail(item:any){busy.value=true;try{detail.value=(await api.get(view.value==='papers'?`/paperbank/papers/${item.id}`:`/questionbank/questions/${item.id}`)).data;detailDialog.value=true}catch(e){error(e)}finally{busy.value=false}}
async function chooseCandidate(channel:string){
  if(!task.value)return
  try{await ElMessageBox.confirm('切换将用此模型的完整结果替换当前审核稿。当前稿会先保存并保留历史备份；人工修改不会合并到新候选。','选择模型结果');await saveDraft();if(dirty)return;const candidate=(await api.get(`/quick-entry/tasks/${task.value.id}/candidates/${channel}`)).data;const checked=(await api.post(`/quick-entry/tasks/${task.value.id}/validate`,candidate)).data;result.value=checked.result;selectedId.value=result.value!.questions[0]?.id||'';view.value='review';markDirty();await saveDraft()}catch(e:any){if(e!=='cancel'&&e!=='close')error(e)}
}
async function rebuildRegions(){if(!task.value||!selected.value||!result.value)return;try{await ElMessageBox.confirm('将按原始内容块重新生成本题内容框和作答区。已有手动题框会被替换，请核对后保存。','重建本题题框');const checked=(await api.post(`/quick-entry/tasks/${task.value.id}/validate`,{...result.value,rebuild_region_question_ids:[selected.value.id]})).data;result.value=checked.result;markDirty();ElMessage.success('本题题框已重建，请对照原卷核对')}catch(e:any){if(e!=='cancel'&&e!=='close')error(e)}}
async function poll(){clockNow.value=Date.now();if(view.value==='tasks'){await loadTasks();if(!concurrencyEdited.value)await loadConcurrency()}if(view.value==='progress'&&task.value){try{task.value=(await api.get(`/quick-entry/tasks/${task.value.id}`)).data;comparison.value=(await api.get(`/quick-entry/tasks/${task.value!.id}/comparison`).catch(()=>({data:null}))).data;if(task.value?.status==='ready')await openTask(task.value)}catch{}}}
onMounted(()=>{loadTasks();loadConcurrency();timer=setInterval(poll,4000)})
onBeforeUnmount(()=>{if(timer)clearInterval(timer);if(saveTimer)clearTimeout(saveTimer)})
</script>

<template>
  <div class="app-shell" :class="{'review-mode':view==='review'}">
    <aside class="app-sidebar">
      <a class="brand" href="#" @click.prevent="navigate('tasks')"><span class="brand-mark"><BookOpen :size="23"/></span><span>金版<span class="brand-caption">智慧教学</span></span></a>
      <div class="workspace-label">内容工作空间</div>
      <nav><button :class="{active:['tasks','review','progress'].includes(view)}" @click="navigate('tasks')"><ScanLine :size="19"/><span>快速录入</span><span class="nav-count" v-if="ready">{{ready}}</span></button><button :class="{active:view==='questions'}" @click="navigate('questions')"><Library :size="19"/><span>题库</span></button><button :class="{active:view==='papers'}" @click="navigate('papers')"><Files :size="19"/><span>试卷库</span></button></nav>
      <div class="sidebar-bottom"><span class="local-dot"/>本地验证工作台<div class="sidebar-footnote">原始资料与处理结果留档</div></div>
    </aside>
    <main class="app-main">
      <header class="topbar"><div class="breadcrumb">内容管理 <ChevronRight :size="14"/><span>{{view==='questions'?'题库':view==='papers'?'试卷库':view==='review'?'快速录入 / 对照审核':'快速录入'}}</span></div><div class="topbar-right"><span class="workspace-badge">九年级数学 · 验证空间</span><span class="avatar">编</span></div></header>

      <template v-if="view==='tasks'">
        <div class="page-content">
          <div class="page-title-row"><div><h1>快速录入</h1><p class="page-description">把手里的资料，变成可以复用的好题。</p></div><el-button type="primary" size="large" @click="createDialog=true"><Plus :size="17"/>新建录入</el-button></div>
          <section class="upload-entry" @dragover.prevent @drop="dropFiles($event);createDialog=true"><div class="upload-illustration"><FileText :size="35" :stroke-width="1.3"/><span class="illustration-check"><Check :size="15"/></span></div><div><h2>从一份资料开始</h2><p>上传试卷或教辅，自动整理题目、匹配答案。最后一步，由你把关。</p><div class="format-list"><span>PDF</span><span>图片</span><span>Word</span><i/>支持多页、多文件及独立答案</div></div><button class="entry-action" @click="createDialog=true">选择文件<ArrowUpRight :size="19"/></button></section>
          <div class="concurrency-controls">
            <div class="concurrency-current"><strong>并行处理</strong><span v-if="concurrency">当前设置：{{concurrency.max_concurrency===0?'无本地上限':concurrency.max_concurrency+' 个'}} · 运行 {{concurrency.running}} 个 · 等待 {{concurrency.queued}} 个</span><span v-else>正在读取设置</span></div>
            <div class="concurrency-edit"><el-checkbox v-model="concurrencyUnlimited" @change="concurrencyEdited=true">无本地上限</el-checkbox><label v-if="!concurrencyUnlimited">最多同时处理 <el-input-number v-model="concurrencyLimit" :min="1" :step="1" :precision="0" controls-position="right" aria-label="最多并行任务数" @change="concurrencyEdited=true"/> 个</label><el-button @click="saveConcurrency" :loading="concurrencyBusy" :disabled="!concurrency">应用设置</el-button></div>
            <p>无本地上限表示所有任务可同时启动；供应商仍可能限流。设置立即生效，降低并发不会中断正在处理的任务。</p>
            <p v-if="concurrencyError" role="alert">{{concurrencyError}} <button class="text-button" @click="loadConcurrency">重新加载</button></p>
          </div>
          <div class="section-title-row"><h2>录入任务 <span class="muted">{{tasks.length}}</span></h2><div class="task-summary"><span v-if="running"><span class="status-dot working"/>{{running}} 个处理中</span><span v-if="ready"><span class="status-dot pending"/>{{ready}} 个待审核</span><button class="icon-button" title="刷新任务" aria-label="刷新任务" @click="loadTasks"><RefreshCw :size="16"/></button></div></div>
          <div class="task-table-wrap"><table class="task-table"><thead><tr><th>资料名称</th><th>录入方式</th><th>状态</th><th>处理成本</th><th>创建时间</th><th class="align-right">操作</th></tr></thead><tbody><tr v-for="t in tasks" :key="t.id"><td><div class="document-name"><span class="file-icon"><FileText :size="20"/></span><div><strong>{{t.title}}</strong><small>{{t.stage}}{{['running','queued','failed','interrupted'].includes(t.status)?' · '+t.message:''}}</small></div></div></td><td>{{modeName(t.mode)}}</td><td><span :class="['status-pill',t.status]"><span class="status-dot"/>{{statusName(t.status)}}</span></td><td class="muted"><span v-if="t.cost">¥{{Number(t.cost.total||0).toFixed(4)}}</span><span v-else>待计算</span><small v-if="t.cost?.mineru_status==='free_service'"> · MinerU免费</small></td><td class="muted">{{formatDate(t.created_at)}}</td><td class="align-right"><button class="text-button" @click="openTask(t)">{{['ready','committed'].includes(t.status)?'对照审核':'查看进度'}}<ArrowRight :size="15"/></button></td></tr><tr v-if="!tasks.length"><td colspan="6"><div class="empty-state"><Files :size="34"/><h3>还没有录入任务</h3><p>上传第一份资料，识别结果会保存在这里。</p><el-button @click="createDialog=true">新建录入</el-button></div></td></tr></tbody></table></div>
          <div class="quiet-note"><ClipboardCheck :size="17"/><span>机器先整理，人工再确认。缺失或不确定的内容会在审核时提示。</span></div>
        </div>
      </template>

      <template v-else-if="view==='progress'&&task">
        <div class="page-content"><button class="back-button" @click="navigate('tasks')"><ArrowLeft :size="16"/>全部任务</button><div class="page-title-row"><div><h1>{{task.title}}</h1><p class="page-description">原文件与已完成阶段自动保留，离开页面不会丢失任务。</p></div><span :class="['status-pill',task.status]">{{statusName(task.status)}}</span></div>
          <div class="progress-layout"><section class="processing-state"><LoaderCircle v-if="['running','queued'].includes(task.status)" class="spin" :size="40"/><CircleAlert v-else :size="40"/><h2>{{task.stage}}</h2><p class="task-message">{{task.message}}</p><p v-if="['running','queued'].includes(task.status)" class="muted">任务已持续 {{Math.max(0,Math.floor((clockNow-new Date(task.created_at).getTime())/1000))}} 秒 · 模型读取等待上限默认30分钟</p><ComparisonPanel :report="comparison" @choose="chooseCandidate"/>
            <div v-if="task.status==='failed'" class="failure-details" role="alert"><h3>失败原因</h3>
              <template v-if="task.error"><p>失败阶段：{{task.error.stage}}<span v-if="task.error.operation"> · {{task.error.operation}}</span></p><p>{{task.error.detail}}</p>
                <article v-for="(attempt,index) in task.error.attempts" :key="index"><strong>{{attempt.channel==='stable'?'稳定渠道':attempt.channel==='low'?'低价渠道':attempt.service}} · {{attempt.operation}}</strong><p>{{attempt.detail}}</p><p>{{attempt.hint}}</p></article><p>{{task.error.hint}}</p></template>
              <p v-else>上方为此前记录的失败原因；恢复处理后的新错误会保留失败阶段、渠道和供应商详情。</p>
            </div><p class="cost-line">当前成本：¥{{Number(task.cost?.total||0).toFixed(4)}} · MinerU免费</p><el-button v-if="['failed','interrupted','uploaded'].includes(task.status)" type="primary" @click="retry" :loading="busy">恢复处理</el-button><div class="process-steps"><span v-for="step in ['格式准备','MinerU识别','数据整理','AI编排','答案匹配','待审核']" :class="{active:task.stage===step}">{{step}}</span></div></section><aside class="process-files"><h3>本次资料</h3><div v-for="f in task.files" class="process-file"><FileText :size="19"/><div>{{f.name}}<small>{{f.role==='answer'?'答案解析':'题目文件'}}</small></div></div><h3>处理成本</h3><p class="muted">LLM ¥{{Number(task.cost?.llm_amount||0).toFixed(4)}} · {{task.cost?.calls||0}} 次调用 · 缓存命中 {{task.cost?.cache_hits||0}} 次</p><h3>处理记录</h3><div class="timeline" v-for="e in task.events"><span class="status-dot"/><div><strong>{{e.stage}}</strong><small>{{e.message}}</small></div></div></aside></div>
        </div>
      </template>

      <template v-else-if="view==='review'&&result&&task">
        <div class="review-top"><button class="mobile-source-toggle" @click="showMobileSource=!showMobileSource">{{showMobileSource?'收起原卷':'对照原卷'}}</button><button class="back-button" @click="navigate('tasks')"><ArrowLeft :size="16"/></button><div class="review-title"><strong>{{task.title}}</strong><span>{{reviewed}} / {{result.questions.length}} 题已核对</span></div><span class="save-status" :class="{'save-error':saveState==='保存失败'}"><Check v-if="saveState==='已保存'" :size="14"/><LoaderCircle v-else-if="saveState==='保存中'" class="spin" :size="14"/>{{saveState}}</span><el-button @click="saveNow"><Save :size="15"/>保存草稿</el-button><el-button @click="validate" :loading="busy">规则检查</el-button><el-button type="primary" @click="commit" :loading="busy">审核入库<ArrowUpRight :size="15"/></el-button></div>
        <ComparisonPanel :report="comparison" @choose="chooseCandidate"/><div class="review-workbench" :class="{'mobile-source-hidden':!showMobileSource}">
          <SourceViewer :documents="result.documents" :questions="result.questions" :selected="selected" :answer-document-id="answerDoc" @select="select" @change="refreshRegions"/>
          <aside class="question-navigator"><div class="pane-heading"><span>题目</span><button class="icon-button" aria-label="新增漏题" title="新增漏题" @click="newQuestion"><Plus :size="16"/></button></div><div class="navigator-filters"><select v-model="paperFilter" aria-label="试卷筛选"><option value="">全部试卷</option><option v-for="p in result.papers" :value="p.id">{{p.title}}</option></select><div class="navigator-tabs"><button :class="{active:filter==='all'}" @click="filter='all'">全部</button><button :class="{active:filter==='pending'}" @click="filter='pending'">待核对</button></div></div><div class="question-nav-list"><button v-for="q in shownQuestions" :key="q.id" :class="{active:q.id===selectedId,reviewed:q.review_status==='reviewed'}" @click="select(q.id)"><span class="q-number">{{q.number}}</span><span class="q-nav-copy"><strong>{{q.attributes.question_type||'题目'}}</strong><small>{{q.attributes.score!=null?q.attributes.score+' 分':'分值未定'}} · {{q.regions.length}} 区域</small></span><Check v-if="q.review_status==='reviewed'" :size="14"/><span v-else-if="q.issues.length" class="issue-indicator"/></button></div><div class="navigator-bottom"><span class="legend-dot"/>待核对 <Check :size="12"/>已确认</div></aside>
          <section class="question-detail" v-if="selected" :key="selected.id"><div class="pane-heading"><span>第 {{selected.number}} 题 <span class="muted">{{result.papers.find(p=>p.id===selected!.paper_id)?.title}}</span></span><div class="question-actions"><button class="icon-button" title="上移题目" aria-label="上移题目" @click="reorder(-1)"><ArrowLeft class="rotate90" :size="15"/></button><button class="icon-button" title="下移题目" aria-label="下移题目" @click="reorder(1)"><ArrowRight class="rotate90" :size="15"/></button><el-dropdown trigger="click"><button class="icon-button" title="题目操作" aria-label="题目操作"><Settings2 :size="17"/></button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="mergeNext">合并下一题</el-dropdown-item><el-dropdown-item @click="splitQuestion">拆出最后区域</el-dropdown-item><el-dropdown-item @click="removeQuestion" divided>删除误识别题目</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div></div>
            <div class="detail-tabs"><button :class="{active:tab==='content'}" @click="tab='content'">题目内容</button><button :class="{active:tab==='attributes'}" @click="tab='attributes'">属性标签</button></div>
            <div class="detail-scroll"><div v-if="selected.issues.length" class="review-notice"><CircleAlert :size="15"/><span>{{selected.issues.join('；')}}</span></div>
              <template v-if="tab==='content'">
                <div class="field-heading"><label>题干</label><span>点击文字或公式即可编辑</span></div>
                <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'stem'" v-model="selected.stem" v-model:document="selected.editor_documents.stem" label="题干编辑器"/>
                <template v-if="selected.options.length">
                  <div class="field-heading"><label>选项</label><button class="text-button" @click="selected.options.push({label:String.fromCharCode(65+selected.options.length),content:''})"><Plus :size="13"/>添加</button></div>
                  <div class="option-editor" :style="selected.options_layout?.columns?{display:'inline-flex',width:`${100/selected.options_layout.columns}%`,verticalAlign:'top'}:undefined" :class="{'image-option':!!selected.options_layout?.columns}" v-for="(option,index) in selected.options" :key="index"><span class="option-label">{{option.label}}</span><QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" v-model="option.content" v-model:document="selected.editor_documents['option-'+index]" :label="'选项'+option.label"/><button class="icon-button option-delete" aria-label="删除选项" @click="selected.options.splice(index,1)"><X :size="13"/></button></div>
                </template>
                <template v-if="selected.subquestions.length && (selected.answer || selected.analysis)">
                  <div class="field-heading"><label>整题答案</label><span>父题级内容，通常用于材料题组</span></div>
                  <QuestionEditor v-if="selected.answer" @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" v-model="selected.answer" v-model:document="selected.editor_documents.answer" label="整题答案"/>
                  <div class="field-heading"><label>整题解析</label></div>
                  <QuestionEditor v-if="selected.analysis" @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" v-model="selected.analysis" v-model:document="selected.editor_documents.analysis" label="整题解析"/>
                </template>
                <div class="field-heading"><label>小问</label><button class="text-button" @click="addSubquestion"><Plus :size="13"/>新增小问</button><span>{{selected.subquestions.length}} 个小问，可手动补录漏识别内容</span></div>
                <div v-for="(sub,index) in selected.subquestions" :key="sub.subquestion_id||index" class="subquestion">
                  <div class="subquestion-heading"><label>小问</label><el-input v-model="sub.number" class="subquestion-number"/><button class="icon-button" aria-label="删除小问" title="删除小问" @click="removeSubquestion(index)"><Trash2 :size="14"/></button></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-sub-'+index" v-model="sub.stem" v-model:document="selected.editor_documents['sub-'+index]" label="小问题干"/>
                  <div class="subquestion-options" v-if="sub.options.length">
                    <div v-for="(option,oi) in sub.options" :key="oi" class="subquestion-option"><span>{{option.label}}</span><QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" v-model="option.content" v-model:document="selected.editor_documents[`sub-${index}-option-${oi}`]" :label="'小问选项'+option.label"/><button class="icon-button" aria-label="删除小问选项" @click="sub.options.splice(oi,1)"><X :size="13"/></button></div>
                  </div>
                  <div class="subquestion-actions"><button class="text-button" @click="sub.options.push({label:String.fromCharCode(65+sub.options.length),content:''})"><Plus :size="13"/>添加选项</button><label>分值 <el-input-number v-model="sub.score" :min="0" :max="1000"/></label><el-checkbox v-model="sub.requires_manual_drawing_review">需要人工看图</el-checkbox></div>
                  <div class="field-heading"><label>答案来源</label></div>
                  <el-select :model-value="sub.answer_entry_id||''" clearable filterable placeholder="选择小问答案" @change="(value:string)=>value&&matchSubAnswer(value,index)"><el-option v-for="entry in result.answer_entries" :key="entry.id" :value="entry.id" :label="entry.group+' · 第'+entry.number+'题'"/></el-select>
                  <div class="field-heading"><label>答案</label></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-sub-'+index+'-answer'" v-model="sub.answer.value" v-model:document="selected.editor_documents[`sub-${index}-answer`]" label="小问答案"/>
                  <div class="field-heading"><label>解析</label></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-sub-'+index+'-analysis'" v-model="sub.answer.analysis" v-model:document="selected.editor_documents[`sub-${index}-analysis`]" label="小问解析"/>
                  <div class="field-heading"><label>评分标准</label><span>主观题可填，未提供留空</span></div>
                  <el-input v-model="sub.answer.scoring_criteria" type="textarea" :rows="2" placeholder="未提供可留空，不自动编造步骤分"/>
                </div>
                <template v-if="!selected.subquestions.length">
                  <div class="field-heading"><label>答案</label><span>与题干连续展示，可直接编辑</span></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-single-answer'" v-model="selected.answer" v-model:document="selected.editor_documents.answer" label="答案编辑器"/>
                  <div class="field-heading"><label>解析</label></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-single-analysis'" v-model="selected.analysis" v-model:document="selected.editor_documents.analysis" label="解析编辑器"/>
                  <div class="field-heading"><label>评分标准</label><span>主观题可填，未提供留空</span></div>
                  <el-input v-model="selected.attributes.scoring_criteria" type="textarea" :rows="2" placeholder="未提供可留空，不自动编造步骤分"/>
                </template>
                <div class="field-heading"><label>原卷区域</label><button class="text-button" @click="rebuildRegions">重建本题题框与作答区</button><span>{{selected.regions.length}} 个区域，可在左侧拖动调整</span></div>
                <div class="region-preview-list"><div v-for="(r,index) in selected.regions" class="region-preview"><img v-if="r.crop_url" :src="r.crop_url" :alt="'第'+selected.number+'题区域'+(index+1)"/><div class="region-caption"><span>区域 {{index+1}} · PDF第 {{r.page_index+1}} 页</span><button class="text-button" @click="recognizeRegion(index)">区域识别</button><button v-if="r.crop_url" class="text-button" @click="insertRegionImage(r.crop_url)"><Plus :size="13"/>插入题干</button><select v-model="r.purpose" @change="markDirty" aria-label="区域用途"><option value="content">题目内容</option><option value="both">内容与作答</option><option value="recovered_visual">原卷补图</option></select></div></div></div>
              </template>
              <template v-else><div class="attribute-grid"><label>题号<el-input v-model="selected.number"/></label><label>分值<el-input-number v-model="selected.attributes.score" :min="0" :max="1000"/></label><label v-for="[key,label] in [['subject','学科'],['stage','学段'],['grade','年级'],['textbook','教材版本'],['question_type','题型'],['year','年份'],['region','地区'],['source_type','来源类型']]" :key="key">{{label}}<el-input v-model="selected.attributes[key]" placeholder="未识别"/></label><label>难度<el-select v-model="selected.attributes.difficulty" clearable><el-option v-for="(name,index) in ['简单','较易','中等','较难','困难']" :value="index+1" :label="name"/></el-select></label><label>审核状态<el-select v-model="selected.review_status"><el-option value="pending" label="待核对"/><el-option value="reviewed" label="已确认"/></el-select></label></div><div class="field-heading"><label>知识点与教材章节</label><span class="neutral-badge">目录未配置</span></div><div class="catalog-empty">正式目录接入后自动分层匹配，并根据教材映射章节。当前不生成未经绑定的正式知识点。</div><div class="field-heading"><label>能力维度</label></div><el-select v-model="selected.attributes.ability_dimensions" multiple filterable allow-create default-first-option placeholder="输入或选择能力维度"><el-option v-for="label in ['理解','应用','分析','推理','建模','运算']" :value="label" :label="label"/></el-select><div class="field-heading"><label>作答形式</label></div><el-select v-model="selected.attributes.response_form" multiple filterable allow-create><el-option v-for="label in ['客观','主观','作图','填空','计算','证明']" :value="label" :label="label"/></el-select><div class="field-heading"><label>情景与背景</label></div><el-input v-model="selected.attributes.background" type="textarea" :rows="2"/><div class="field-heading"><label>扩展标签</label><button class="text-button" @click="(selected.attributes.extension_attributes ||= []).push({name:'',value:''})"><Plus :size="13"/>新增</button></div><div class="extension-row" v-for="(tag,index) in selected.attributes.extension_attributes"><el-input v-model="tag.name" placeholder="标签名称"/><el-input v-model="tag.value" placeholder="标签值"/><button class="icon-button" aria-label="删除标签" @click="selected.attributes.extension_attributes.splice(index,1)"><X :size="14"/></button></div><div class="field-heading"><label>授权与排序</label></div><p class="muted">授权尚未确认。重要程度算法未启用，不生成无依据的推荐分。</p></template>
            </div>
            <div class="detail-footer"><button class="text-button" @click="nextQuestion(-1)"><ArrowLeft :size="15"/>上一题</button><el-button type="primary" @click="confirmQuestion"><Check :size="15"/>确认并继续</el-button><button class="text-button" @click="nextQuestion(1)">下一题<ArrowRight :size="15"/></button></div>
          </section><div v-else class="empty-state"><h3>没有题目</h3><el-button @click="newQuestion">添加漏题</el-button></div>
        </div>
      </template>

      <template v-else-if="view==='questions'||view==='papers'"><div class="page-content"><div class="page-title-row"><div><h1>{{view==='questions'?'题库':'试卷库'}}</h1><p class="page-description">{{view==='questions'?'已保存的题目，连同来源与审核版本一起保留。':'整卷结构、题目引用与原卷模板，统一管理。'}}</p></div><el-button type="primary" @click="createDialog=true"><Plus :size="16"/>录入资料</el-button></div><div class="bank-toolbar"><el-input v-model="bankSearch" placeholder="搜索题目内容" clearable @keyup.enter="loadBank"><template #prefix><Search :size="16"/></template></el-input><el-button @click="loadBank">搜索</el-button><span class="muted">{{bank.length}} 条资源</span></div><div class="bank-list"><button class="bank-item" v-for="item in bank" :key="item.id" @click="openDetail(item)"><template v-if="view==='questions'"><div class="bank-item-meta"><span class="q-number">{{item.number}}</span><span>{{item.content.attributes?.question_type||'题目'}}</span><span class="neutral-badge">{{item.content.attributes?.subject||'未分类'}}</span><span :class="['status-pill',item.status==='incomplete'?'uploaded':'committed']">{{item.status==='incomplete'?'待完善':'已保存'}}</span></div><div class="question-prose bank-question" v-html="renderMarkdown(item.content.stem)"/></template><template v-else><div class="bank-paper-icon"><Files :size="28"/></div><div><h3>{{item.title}}</h3><p>{{modeName(item.mode)}} · {{item.mode==='textbook'?'已保存原卷区域模板':'普通试卷，不启用原卷批阅'}}</p><small>{{formatDate(item.created_at)}}</small></div></template><ChevronRight :size="18" class="bank-chevron"/></button><div class="empty-state" v-if="!bank.length"><Library :size="36"/><h3>这里还没有资源</h3><p>完成审核并入库后，题目或试卷会出现在这里。</p><el-button @click="navigate('tasks')">前往快速录入</el-button></div></div></div></template>
    </main>

    <el-dialog v-model="createDialog" title="新建录入" width="min(760px, 95vw)" :close-on-click-modal="false"><div class="create-form"><label class="form-label">录入方式</label><div class="mode-options"><button v-for="m in [{id:'textbook',title:'教辅卷 / 作业',desc:'题库 + 试卷 + 原卷区域'},{id:'paper',title:'普通整卷',desc:'题库 + 试卷库'},{id:'questions',title:'仅录题目',desc:'只保存到题库'}]" :class="{active:newMode===m.id}" @click="newMode=m.id"><strong>{{m.title}}</strong><span>{{m.desc}}</span><Check v-if="newMode===m.id" :size="15"/></button></div><label class="form-label">任务名称 <span>可选</span></label><el-input v-model="newTitle" placeholder="默认使用首个文件名称"/><label class="form-label">题目文件</label><label class="file-drop" @dragover.prevent @drop="dropFiles"><UploadCloud :size="28"/><strong>点击选择，或拖入文件</strong><span>PDF、JPG、PNG、Word · 支持多个文件</span><input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" @change="chooseFiles($event,'question')"/></label><div class="selected-files" v-for="(file,index) in questionFiles"><FileText :size="15"/><span>{{file.name}}</span><button class="icon-button" aria-label="移除文件" @click="questionFiles.splice(index,1)"><X :size="14"/></button></div><div class="field-heading"><label>答案与解析文件 <span class="muted">可选，可包含其他试卷答案</span></label></div><label class="file-drop answer-file-drop" @dragover.prevent @drop.stop="dropFiles($event,'answer')"><UploadCloud :size="28"/><strong>点击选择，或拖入答案文件</strong><span>PDF、JPG、PNG、Word · 支持多个文件</span><input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" @change="chooseFiles($event,'answer')"/></label><div class="selected-files" v-for="(file,index) in answerFiles"><FileText :size="15"/><span>{{file.name}}</span><button class="icon-button" aria-label="移除答案文件" @click="answerFiles.splice(index,1)"><X :size="14"/></button></div><div class="answer-upload-note" v-if="!answerFiles.length">答案已在原卷中？无需重复上传，系统会自动提取匹配。</div><div class="create-options"><el-checkbox v-model="generate">对缺失的答案和解析使用 AI 生成</el-checkbox><el-select v-model="policy" aria-label="模型渠道策略"><el-option value="compare" label="多模型并行对比（各自计费）"/><el-option value="deepseek" label="DeepSeek Flash"/><el-option value="low_first" label="低价优先，稳定渠道备用"/><el-option value="stable_first" label="稳定渠道优先"/></el-select></div><p class="muted">原文件和识别结果保留。生成内容会标记为待审核，缺少知识点目录不影响录入。</p></div><template #footer><el-button @click="createDialog=false">取消</el-button><el-button type="primary" @click="createTask" :loading="busy">开始识别<ArrowRight :size="16"/></el-button></template></el-dialog>
    <el-dialog v-model="issuesDialog" title="规则检查" width="600px"><div class="check-success" v-if="!validationIssues.length"><CheckCheck :size="26"/>未发现结构性问题，请继续核对识别内容。</div><div class="validation-item" v-for="issue in validationIssues"><CircleAlert :size="17"/><div><strong>{{issueLocation(issue)}} · {{issue.severity==='error'?'阻止入库':'可保存提示'}}</strong><p>{{issue.message}}</p><small v-if="issue.fields">位置：{{issue.fields.map(fieldName).join('、')}}</small><p v-if="issue.hint" class="muted">{{issue.hint}}</p></div><button class="text-button" v-if="issue.question_id" @click="select(issue.question_id);issuesDialog=false">定位</button></div><p class="muted">规则检查通过不代表识别内容准确，仍需人工对照审核。</p></el-dialog>
    <el-dialog v-model="detailDialog" :title="detail?.title||('题目 '+(detail?.number||''))" width="min(900px, 94vw)"><template v-if="detail"><div v-if="detail.questions" class="paper-detail-list"><div class="template-notice" v-if="detail.templates?.length"><ScanLine :size="17"/>原卷区域模板已保存 · 实际扫描配准尚未接入</div><article v-for="row in detail.questions"><h3>第 {{row.content.number}} 题</h3><QuestionPreview :question="row.content"/></article></div><article v-else><QuestionPreview :question="detail.content"/><div class="region-preview-list"><img v-for="r in detail.content.regions" :src="r.crop_url" alt="来源区域"/></div></article></template><template #footer><el-button @click="detailDialog=false">关闭</el-button><el-button type="primary" @click="detailDialog=false;openTask(tasks.find(t=>t.id===detail.task_id)||{id:detail.task_id,status:'committed'} as Task)">返回来源审核</el-button></template></el-dialog>
  </div>
</template>

