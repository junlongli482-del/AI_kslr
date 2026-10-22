<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { BookOpen, ScanLine, Library, Files, Plus, ArrowUpRight, ArrowLeft, ArrowRight, UploadCloud, FileText, Check, CheckCheck, Search, RefreshCw, Settings2, ChevronRight, CircleAlert, LoaderCircle, Save, Split, Merge, Trash2, PanelLeftClose, ClipboardCheck, X, ExternalLink, Grip, Crop } from 'lucide-vue-next'
import type { Task, Question, Result, Paper, Region } from './types'
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
const paperOpen=ref(false)
const costTask=ref<any>(null),costDetail=ref<any>(null),costLoading=ref(false),costCallId=ref('')
const zoneLayout=ref<'A3-2'|'A3-3'|'A4-1'>('A3-2'),zoneDefaults=ref<Record<string,any>>({}),zonePreviewUrl=ref(''),zonePreviewBase64=ref(''),zonePreviewPdf=ref(false),zonePreviewName=ref(''),zoneBbox=ref<number[]>([.04,.015,.42,.068]),zoneSaving=ref(false),zoneDrag=ref<any>(null)
const createDialog=ref(false),newTitle=ref(''),newMode=ref('textbook'),generate=ref(false),policy=ref('deepseek'),questionFiles=ref<File[]>([]),answerFiles=ref<File[]>([])
const bank=ref<any[]>([]),bankSearch=ref(''),detail=ref<any|null>(null),detailDialog=ref(false),issuesDialog=ref(false),validationIssues=ref<any[]>([])
const concurrency=ref<{max_concurrency:number;running:number;queued:number}|null>(null)
const concurrencyUnlimited=ref(true),concurrencyLimit=ref(3),concurrencyBusy=ref(false),concurrencyError=ref('')
const concurrencyEdited=ref(false)
const comparison=ref<any>(null),clockNow=ref(Date.now())
const selected=computed(()=>result.value?.questions.find(q=>q.id===selectedId.value)||null)
const activePaper=computed(()=>result.value?.papers.find(p=>p.id===paperFilter.value)||result.value?.papers.find(p=>p.id===selected.value?.paper_id)||result.value?.papers[0]||null)
const paperForm=computed(()=>activePaper.value?ensurePaper(activePaper.value):null)
const reviewed=computed(()=>result.value?.questions.filter(q=>q.review_status==='reviewed').length||0)
const shownQuestions=computed(()=>result.value?.questions.filter(q=>(!paperFilter.value||q.paper_id===paperFilter.value)&&(filter.value!=='pending'||q.review_status!=='reviewed')&&(!search.value||q.number.includes(search.value)||q.stem.includes(search.value)))||[])
const running=computed(()=>tasks.value.filter(t=>t.status==='running').length)
const ready=computed(()=>tasks.value.filter(t=>t.status==='ready').length)
let timer:ReturnType<typeof setInterval>|undefined,saveTimer:ReturnType<typeof setTimeout>|undefined,loadingDraft=false,dirty=false
let savePromise:Promise<void>|null=null
const modeName=(mode:string)=>({textbook:'教辅卷 / 作业',questions:'仅录题目',paper:'普通整卷'}[mode]||mode)
const statusName=(status:string)=>({running:'处理中',queued:'等待并发名额',pending:'正在准备',ready:'待审核',committed:'已入库',uploaded:'待处理',failed:'处理失败',interrupted:'待恢复'}[status]||status)
const scoreSourceName=(source:string)=>({paper_declared:'卷面',ai_assigned:'AI分配',manual:'人工'}[source]||'')
const formatDate=(s:string)=>s?.slice(5,16).replace('T',' ')
const pretty=(value:any)=>value==null?'':typeof value==='string'?value:JSON.stringify(value,null,2)
const paperTypes=['同步练','单元测','月考','期中','期末','一模二模','真题','模拟','课时作业','竞赛','其他']
const paperInheritFields:[string,string][]=[['year','年份'],['semester','学期'],['region','地区'],['paper_type','试卷类型'],['textbook_version','教材版本'],['stage','学段'],['subject','学科'],['grade','年级']]
function ensurePaper(paper:any){
  paper.attributes??={};paper.exam??={};paper.source??={};paper.manual??={}
  paper.attributes.school_publisher??=''
  paper.paper_type??=''
  paper.exam.duration_min??=null;paper.exam.declared_total_score??=null;paper.exam.declared_question_count??=null
  paper.exam.candidate_notes??='';paper.exam.has_elective??=null;paper.exam.has_listening??=null;paper.exam.answers_at_end??=null
  paper.source.page_count??=null;paper.source.printed_page_numbers??=[];paper.source.columns??=[]
  paper.manual.quality_level??='';paper.manual.tags??=[]
  return paper
}
function openPaper(){if(activePaper.value){ensurePaper(activePaper.value);paperOpen.value=true}}
async function openCost(t:any){costDetail.value=null;costCallId.value='';costTask.value=t;try{if(!t.cost)costTask.value=(await api.get(`/quick-entry/tasks/${t.id}`)).data;view.value='cost'}catch(e){error(e)}}
async function inspectCost(item:any){if(!item?.call_id){ElMessage.info('这条调用是旧记录，没有原始输入输出');return}try{costLoading.value=true;costCallId.value=item.call_id;costDetail.value=(await api.get(`/quick-entry/tasks/${costTask.value.id}/cost/calls/${item.call_id}`)).data}catch(e){error(e)}finally{costLoading.value=false}}
function closeCost(){view.value='tasks';costDetail.value=null;costCallId.value=''}
const costRaw=(detail:any)=>pretty(detail?.response?.raw??detail?.response?.parsed??detail?.response??detail?.error??'')
async function copyPrompt(text:string){if(!text){ElMessage.info('没有可复制的内容');return}try{await navigator.clipboard.writeText(text);ElMessage.success('已复制')}catch{ElMessage.warning('复制失败，请手动选择文本复制')}}
function paperQuestions(paper:any){return result.value?.questions.filter(q=>q.paper_id===paper.id)||[]}
function paperTotal(paper:any){return paperQuestions(paper).reduce((sum,q)=>sum+Number(q.attributes.score||0),0)}
function paperDeclared(paper:any){const value=Number(paper.exam?.declared_total_score);return Number.isFinite(value)&&value>0?value:null}
function paperDiff(paper:any){const declared=paperDeclared(paper);return declared===null?null:paperTotal(paper)-declared}
function printedPagesText(paper:any){return (paper.source?.printed_page_numbers||[]).join('、')}
function setPrintedPages(paper:any,value:string){paper.source??={};paper.source.printed_page_numbers=String(value||'').split(/[,，、\s]+/).filter(Boolean);paperChanged()}
function paperChanged(){if(!activePaper.value)return;applyPaperInheritanceLocal(activePaper.value);markDirty()}
function applyPaperInheritanceLocal(paper:any){
  if(!result.value)return
  ensurePaper(paper)
  for(const q of paperQuestions(paper)){
    q.attribute_sources??={}
    for(const [field] of paperInheritFields){
      if(q.attribute_sources[field]==='manual')continue
      const value=field==='paper_type'?paper.paper_type:paper.attributes[field]
      if(value!==''&&value!=null){q.attributes[field]=value;q.attribute_sources[field]='paper'}
      else if(q.attribute_sources[field]==='paper')q.attribute_sources[field]='question'
    }
  }
}
function markAttributeManual(field:string){if(!selected.value)return;(selected.value.attribute_sources??={})[field]='manual';markDirty()}
const noticeIssues=computed(()=>{const list=selected.value?.issues||[];const hasCorrections=!!selected.value?.corrections?.length;return list.filter(issue=>!(hasCorrections&&/^AI修正/.test(issue)))})
function undoCorrection(target:any,index:number){
  const list=target?.corrections||[]
  const item=list[index]
  if(!item)return
  const field=String(item.field||'')
  const before=typeof item.before==='string'?item.before:''
  if(!before){ElMessage.warning('这条修正没有记录原文，无法一键撤销');return}
  if(field==='stem')target.stem=before
  else if(field==='answer')target.answer=before
  else if(field==='analysis')target.analysis=before
  else {ElMessage.warning('该字段暂不支持一键撤销，请按“原文”手动改回');return}
  if(target.editor_documents)target.editor_documents={...target.editor_documents}
  list.splice(index,1)
  markDirty()
  ElMessage.success('已撤销该处修正，请核对')
}
function markScoreManual(){if(!selected.value)return;selected.value.attributes.score_source='manual';markDirty()}
const rubricBusy=ref(false)
async function fillRubric(target?:any){
  if(!task.value||!selected.value||rubricBusy.value)return
  const subquestionId=target?.subquestion_id||null
  try{
    await ElMessageBox.confirm(subquestionId?'只调用一次 AI，补全当前小问的评分标准；不会生成或覆盖其他小问。':'只调用一次 AI，补全整题的评分标准；已有内容不会被覆盖。','补全评分标准',{confirmButtonText:'开始生成',cancelButtonText:'取消'})
    rubricBusy.value=true
    const response=await api.post(`/quick-entry/tasks/${task.value.id}/question-rubric`,{task_id:task.value.id,question:selected.value,subquestion_id:subquestionId})
    const scoring=response.data.scoring
    if(subquestionId){
      const sub=selected.value.subquestions.find(item=>item.subquestion_id===subquestionId)
      if(sub&&scoring){sub.scoring=scoring;markDirty()}
    }else if(scoring){
      selected.value.scoring=scoring
      if(response.data.auto)selected.value.grading_method='auto'
      markDirty()
    }
    if(response.data.auto)ElMessage.info(subquestionId?'AI 判定该小问为客观题（自动判分），无需得分点':'AI 判定该题为客观题（自动判分），无需得分点')
    else if(response.data.filled)ElMessage.success('已补全当前评分标准')
    else ElMessage.warning('AI 未返回可用的得分点，请重试或手动添加')
  }catch(e:any){if(e!=='cancel'&&e!=='close')error(e)}
  finally{rubricBusy.value=false}
}
function restoreInherited(field:string){
  if(!selected.value||!activePaper.value)return
  const value=field==='paper_type'?activePaper.value.paper_type:activePaper.value.attributes?.[field]
  selected.value.attributes[field]=value||''
  ;(selected.value.attribute_sources??={})[field]='paper'
  markDirty();ElMessage.success('已恢复为跟随试卷')
}
function canonicalType(value:string,q?:Question){
  const text=String(value||'')
  if(/题组|复合/.test(text)){
    const subs=q?.subquestions||[]
    if(subs.some(sub=>(sub.options||[]).length))return'选择题'
    return'综合题'
  }
  if(/多选/.test(text))return'多选题'
  if(/选择|单选/.test(text))return'单选题'
  if(/判断/.test(text))return'判断题'
  if(/填空/.test(text))return'填空题'
  if(/作文|写作/.test(text))return'作文题'
  if(/计算/.test(text))return'计算题'
  if(/证明/.test(text))return'证明题'
  if(/综合|材料/.test(text))return'综合题'
  if(/解答/.test(text))return'解答题'
  return text||'未分类'
}
function paperSections(paper:any){
  const rows:{type:string;items:Question[]}[]=[]
  for(const q of paperQuestions(paper)){
    const type=canonicalType(q.attributes.question_type,q)
    const last=rows[rows.length-1]
    if(!last||last.type!==type)rows.push({type,items:[q]});else last.items.push(q)
  }
  const numerals=['一','二','三','四','五','六','七','八','九','十']
  return rows.map((row,index)=>{
    const count=row.items.length,total=row.items.reduce((sum,q)=>sum+Number(q.attributes.score||0),0)
    const first=String(row.items[0]?.number||'').match(/\d+/)?.[0]||row.items[0]?.number||''
    const last=String(row.items[row.items.length-1]?.number||'').match(/\d+/)?.[0]||row.items[row.items.length-1]?.number||''
    const range=count===1?first:`${first}–${last}`
    const equal=row.items.every(q=>Number(q.attributes.score||0)===Number(row.items[0]?.attributes.score||0))
    const label=`${numerals[index]||index+1}、${row.type}`
    return{label,text:`${label}（第${range}题，共${count}题，${total}分${equal&&count>1?`，每题${Number(row.items[0]?.attributes.score||0)}分`:''}）`}
  })
}
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
async function navigate(next:string){if(view.value==='review'){await saveDraft();if(dirty)return}view.value=next;detail.value=null;if(next==='tasks')await loadTasks();else if(next==='questions'||next==='papers')await loadBank();else if(next==='student-zones')await loadStudentZoneSettings()}
const zoneSvg=ref<SVGSVGElement|null>(null)
function zonePoint(e:PointerEvent){const rect=zoneSvg.value!.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height))]}
function zonePointerDown(e:PointerEvent,resize=false){e.preventDefault();zoneSvg.value?.setPointerCapture(e.pointerId);const start=zonePoint(e);zoneDrag.value={mode:resize?'resize':'move',start,bbox:[...zoneBbox.value]}}
function zonePointerMove(e:PointerEvent){const drag=zoneDrag.value;if(!drag)return;const p=zonePoint(e),dx=p[0]-drag.start[0],dy=p[1]-drag.start[1],b=drag.bbox;if(drag.mode==='move'){const x=Math.max(0,Math.min(1-(b[2]-b[0]),b[0]+dx)),y=Math.max(0,Math.min(1-(b[3]-b[1]),b[1]+dy));zoneBbox.value=[x,y,x+b[2]-b[0],y+b[3]-b[1]]}else zoneBbox.value=[b[0],b[1],Math.max(b[0]+.02,p[0]),Math.max(b[1]+.01,p[1])]}
function zonePointerUp(){zoneDrag.value=null}
async function loadStudentZoneSettings(){try{zoneDefaults.value=(await api.get('/quick-entry/settings/student-zones')).data||{};selectZoneLayout(zoneLayout.value)}catch(e){error(e)}}
function selectZoneLayout(layout:'A3-2'|'A3-3'|'A4-1'){zoneLayout.value=layout;const entry=zoneDefaults.value[layout]||{};zoneBbox.value=[...(entry.bbox||[.04,.015,.42,.068])];zonePreviewUrl.value=entry.preview_url||'';zonePreviewBase64.value='';zonePreviewPdf.value=false;zonePreviewName.value=''}
function zonePreviewFile(event:Event){const file=(event.target as HTMLInputElement).files?.[0];if(!file)return;zonePreviewName.value=file.name;zonePreviewPdf.value=/\.pdf$/i.test(file.name)||file.type==='application/pdf';const reader=new FileReader();reader.onload=()=>{zonePreviewBase64.value=String(reader.result);zonePreviewUrl.value=zonePreviewPdf.value?'':String(reader.result)};reader.readAsDataURL(file)}
function resetStudentZone(){zoneBbox.value=[.04,.015,.42,.068]}
async function saveStudentZone(){if(zoneSaving.value)return;try{zoneSaving.value=true;const response=await api.put('/quick-entry/settings/student-zones',{layout:zoneLayout.value,bbox:zoneBbox.value,preview_base64:zonePreviewBase64.value||null});zoneDefaults.value[zoneLayout.value]=response.data.settings;zonePreviewUrl.value=response.data.settings.preview_url||zonePreviewUrl.value;zonePreviewBase64.value='';zonePreviewPdf.value=false;ElMessage.success('学生信息区默认值已保存，只影响后续新任务')}catch(e){error(e)}finally{zoneSaving.value=false}}
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
function canDelete(t:Task){return t.status!=='committed'&&!['running','queued','pending'].includes(t.status)}
async function deleteTask(t:Task){
  if(!canDelete(t))return
  try{
    await ElMessageBox.confirm(`删除任务「${t.title}」及其上传原图、识别结果、审核稿和成本记录，删除后不可恢复。`,'删除任务',{confirmButtonText:'删除',cancelButtonText:'取消',type:'warning'})
    await api.delete(`/quick-entry/tasks/${t.id}`)
    ElMessage.success('任务已删除')
    if(task.value?.id===t.id)task.value=null
    await loadTasks()
  }catch(e:any){if(e!=='cancel'&&e!=='close')error(e)}
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
    if(result.value && !result.value.template)result.value.template={version:'template-v2',student_zones:[],annotations:{},blanks:[]}
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
function syncSubScores(){
  if(!selected.value)return
  const subs=selected.value.subquestions||[]
  if(!subs.length||subs.some((sub:any)=>sub.score==null))return
  const total=subs.reduce((sum:number,sub:any)=>sum+Number(sub.score||0),0)
  if(Number(selected.value.attributes.score)!==total){selected.value.attributes.score=total;selected.value.attributes.score_source='manual';markDirty()}
}
function subScoresPartial(target:any){return (target?.subquestions||[]).some((sub:any)=>sub.score==null)}
function addOption(){
  if(!selected.value)return
  const options=selected.value.options
  if(!options.length){'ABCD'.split('').forEach(label=>options.push({label,content:''}))}
  else if(options.length<26){options.push({label:String.fromCharCode(65+options.length),content:''})}
  selected.value.issues=(selected.value.issues||[]).filter(issue=>!(issue.includes('选项')&&issue.includes('未识别到')))
  markDirty()
}
function removeSubquestion(index:number){
  if(!selected.value)return
  selected.value.subquestions.splice(index,1)
  syncSubScores()
  selected.value.review_status='pending';markDirty()
}
function ensureScoring(target:any){
  if(!target.scoring||target.scoring.method==='auto')target.scoring={method:'manual',type:'step',points:[],deductions:[],notes:''}
  if(!Array.isArray(target.scoring.points))target.scoring.points=[]
  return target.scoring
}
function addScoringPoint(target:any){const scoring=ensureScoring(target);scoring.points.push({pct:0,criterion:''});markDirty()}
function makeManualScoring(target:any){ensureScoring(target);markDirty()}
function removeScoringPoint(target:any,index:number){target.scoring?.points?.splice(index,1);markDirty()}
function scoringTotal(target:any){return Math.round((target.scoring?.points||[]).reduce((sum:number,point:any)=>sum+Number(point.pct||0),0))}
function matchSubAnswer(entryId:string,index:number){
  if(!selected.value||!result.value)return
  const sub=selected.value.subquestions[index];const entry=result.value.answer_entries.find(e=>e.id===entryId)
  if(!sub||!entry)return
  const other=result.value.questions.some(q=>q!==selected.value&&q.subquestions?.some(s=>s.answer_entry_id===entryId))
  if(other){ElMessage.warning('此答案已关联其他小问，请先解除原关联');return}
  sub.answer_entry_id=entryId;sub.answer={value:entry.answer||'',analysis:entry.analysis||'',scoring_criteria:entry.scoring_criteria??null,source:'answer_file'};entry.matched_question_id=selected.value.id;entry.matched_subquestion_id=sub.subquestion_id||sub.number;result.value.unmatched_answer_entry_ids=result.value.answer_entries.filter(e=>!e.matched_question_id).map(e=>e.id);selected.value.review_status='pending';markDirty()
}
const regionEditors=ref<Record<string,any>>({})
function regionKey(questionId:string,index:number){return questionId+'-'+index}
function setRegionEditor(key:string,editor:any){if(editor)regionEditors.value[key]=editor;else delete regionEditors.value[key]}
function categoryName(value?:string){return ({content:'题目内容',both:'内容与作答',reference_answer:'参考答案',recovered_visual:'原卷补图',generic:'通用'}[value||'']||'通用')}
function recognitionTime(value?:string){return value?value.slice(0,16).replace('T',' '):''}
async function recognizeRegion(region:Region,index:number){
  if(!task.value||!selected.value)return
  if(region.purpose==='recovered_visual'){
    region.recognition={category:'recovered_visual',image_only:true,markdown:'',created_at:new Date().toISOString(),model:''}
    markDirty();ElMessage.success('已保留原卷裁图，不调用模型');return
  }
  try{
    await ElMessageBox.confirm('将调用一次 DeepSeek 多模态识别，并产生一次模型费用。继续吗？','区域识别',{confirmButtonText:'开始识别',cancelButtonText:'取消'})
    const paper=activePaper.value
    const response=await api.post(`/quick-entry/tasks/${task.value.id}/region-recognize`,{
      question_id:selected.value.id,document_id:region.document_id,page_index:region.page_index,bbox:region.bbox,
      category:region.purpose||'',channel:'deepseek',
      context:{stage:selected.value.attributes.stage||paper?.attributes?.stage||'',subject:selected.value.attributes.subject||paper?.attributes?.subject||'',page:region.page_index+1},
    })
    const data=response.data
    region.recognition={category:data.category,markdown:data.markdown||'',editor_document:null,model:data.model,created_at:data.created_at,seconds:data.seconds,usage:data.usage,cost:data.cost,image_only:!!data.image_only}
    markDirty();ElMessage.success('识别完成，可复制到题目')
  }catch(e:any){
    if(e==='cancel'||e==='close')return
    const message=e.response?.data?.detail||e.message||'区域识别失败'
    region.recognition={...(region.recognition||{}),error:message,created_at:new Date().toISOString()}
    markDirty();ElMessage.error(message)
  }
}
function clearRecognition(region:Region){region.recognition=null;markDirty()}
async function copyRecognition(region:Region,index:number){
  if(!selected.value)return
  const editor=regionEditors.value[regionKey(selected.value.id,index)]
  if(editor?.copyAll){await editor.copyAll();return}
  if(region.recognition?.markdown){await navigator.clipboard.writeText(region.recognition.markdown);ElMessage.success('已复制')}
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
async function rebuildAllRegions(){
  if(!task.value||!result.value)return
  try{
    await ElMessageBox.confirm('按当前版式重算全部题框（多栏、主观题整栏、排除小节标题）。已手动调整过的题框会被覆盖，请核对后保存。','重建全部题框',{confirmButtonText:'开始重建',cancelButtonText:'取消'})
    busy.value=true
    const ids=result.value.questions.map(q=>q.id)
    const checked=(await api.post(`/quick-entry/tasks/${task.value.id}/validate`,{...result.value,rebuild_region_question_ids:ids})).data
    if(checked.result){result.value=checked.result;markDirty();ElMessage.success('全部题框已重建，请对照检查')}
  }catch(e:any){if(e!=='cancel'&&e!=='close')error(e)}finally{busy.value=false}
}
async function poll(){clockNow.value=Date.now();if(view.value==='tasks'){await loadTasks();if(!concurrencyEdited.value)await loadConcurrency()}if(view.value==='progress'&&task.value){try{task.value=(await api.get(`/quick-entry/tasks/${task.value.id}`)).data;comparison.value=(await api.get(`/quick-entry/tasks/${task.value!.id}/comparison`).catch(()=>({data:null}))).data;if(task.value?.status==='ready')await openTask(task.value)}catch{}}}
onMounted(()=>{loadTasks();loadConcurrency();timer=setInterval(poll,4000)})
onBeforeUnmount(()=>{if(timer)clearInterval(timer);if(saveTimer)clearTimeout(saveTimer)})
</script>

<template>
  <div class="app-shell" :class="{'review-mode':view==='review'}">
    <aside class="app-sidebar">
      <a class="brand" href="#" @click.prevent="navigate('tasks')"><span class="brand-mark"><BookOpen :size="23"/></span><span>金版<span class="brand-caption">智慧教学</span></span></a>
      <div class="workspace-label">内容工作空间</div>
      <nav><button :class="{active:['tasks','review','progress','cost'].includes(view)}" @click="navigate('tasks')"><ScanLine :size="19"/><span>快速录入</span><span class="nav-count" v-if="ready">{{ready}}</span></button><button :class="{active:view==='questions'}" @click="navigate('questions')"><Library :size="19"/><span>题库</span></button><button :class="{active:view==='papers'}" @click="navigate('papers')"><Files :size="19"/><span>试卷库</span></button><button :class="{active:view==='student-zones'}" @click="navigate('student-zones')"><Crop :size="19"/><span>学生信息区</span></button></nav>
      <div class="sidebar-bottom"><span class="local-dot"/>本地验证工作台<div class="sidebar-footnote">原始资料与处理结果留档</div></div>
    </aside>
    <main class="app-main">
      <header class="topbar"><div class="breadcrumb">内容管理 <ChevronRight :size="14"/><span>{{view==='questions'?'题库':view==='papers'?'试卷库':view==='student-zones'?'学生信息区':view==='review'?'快速录入 / 对照审核':view==='cost'?'快速录入 / 处理成本':'快速录入'}}</span></div><div class="topbar-right"><span class="workspace-badge">九年级数学 · 验证空间</span><span class="avatar">编</span></div></header>

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
          <div class="task-table-wrap"><table class="task-table"><thead><tr><th>资料名称</th><th>录入方式</th><th>状态</th><th>处理成本</th><th>创建时间</th><th class="align-right">操作</th></tr></thead><tbody><tr v-for="t in tasks" :key="t.id"><td><div class="document-name"><span class="file-icon"><FileText :size="20"/></span><div><strong>{{t.title}}</strong><small>{{t.stage}}{{['running','queued','failed','interrupted'].includes(t.status)?' · '+t.message:''}}</small></div></div></td><td>{{modeName(t.mode)}}</td><td><span :class="['status-pill',t.status]"><span class="status-dot"/>{{statusName(t.status)}}</span></td><td class="muted"><button v-if="t.cost" class="cost-link" @click.stop="openCost(t)">¥{{Number(t.cost.total||0).toFixed(6)}}<ChevronRight :size="12"/></button><span v-else>待计算</span><small v-if="t.cost?.mineru_status==='free_service'"> · MinerU免费</small></td><td class="muted">{{formatDate(t.created_at)}}</td><td class="align-right"><button class="icon-button row-delete" :disabled="!canDelete(t)" :title="canDelete(t)?'删除任务':'审核通过的任务不能删除'" :aria-label="canDelete(t)?'删除任务':'审核通过的任务不能删除'" @click.stop="canDelete(t)&&deleteTask(t)"><Trash2 :size="15"/></button><button class="text-button" @click="openTask(t)">{{['ready','committed'].includes(t.status)?'对照审核':'查看进度'}}<ArrowRight :size="15"/></button></td></tr><tr v-if="!tasks.length"><td colspan="6"><div class="empty-state"><Files :size="34"/><h3>还没有录入任务</h3><p>上传第一份资料，识别结果会保存在这里。</p><el-button @click="createDialog=true">新建录入</el-button></div></td></tr></tbody></table></div>
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
            </div><p class="cost-line">当前成本：¥{{Number(task.cost?.total||0).toFixed(6)}} · MinerU免费</p><el-button v-if="['failed','interrupted','uploaded'].includes(task.status)" type="primary" @click="retry" :loading="busy">恢复处理</el-button><div class="process-steps"><span v-for="step in ['格式准备','MinerU识别','数据整理','AI编排','答案匹配','待审核']" :class="{active:task.stage===step}">{{step}}</span></div></section><aside class="process-files"><h3>本次资料</h3><div v-for="f in task.files" class="process-file"><FileText :size="19"/><div>{{f.name}}<small>{{f.role==='answer'?'答案解析':'题目文件'}}</small></div></div><h3>处理成本</h3><p class="muted">LLM ¥{{Number(task.cost?.llm_amount||0).toFixed(6)}} · {{task.cost?.calls||0}} 次调用 · 缓存命中 {{task.cost?.cache_hits||0}} 次</p><h3>处理记录</h3><div class="timeline" v-for="e in task.events"><span class="status-dot"/><div><strong>{{e.stage}}</strong><small>{{e.message}}</small></div></div></aside></div>
        </div>
      </template>

      <template v-else-if="view==='review'&&result&&task">
        <div class="review-top"><button class="mobile-source-toggle" @click="showMobileSource=!showMobileSource">{{showMobileSource?'收起原卷':'对照原卷'}}</button><button class="back-button" @click="navigate('tasks')"><ArrowLeft :size="16"/></button><div class="review-title"><strong>{{task.title}}</strong><span>{{reviewed}} / {{result.questions.length}} 题已核对</span></div><span class="save-status" :class="{'save-error':saveState==='保存失败'}"><Check v-if="saveState==='已保存'" :size="14"/><LoaderCircle v-else-if="saveState==='保存中'" class="spin" :size="14"/>{{saveState}}</span><el-button @click="openPaper"><Files :size="15"/>试卷信息</el-button><el-button @click="saveNow"><Save :size="15"/>保存草稿</el-button><el-button @click="rebuildAllRegions" :loading="busy">重建全部题框</el-button><el-button @click="validate" :loading="busy">规则检查</el-button><el-button type="primary" @click="commit" :loading="busy">审核入库<ArrowUpRight :size="15"/></el-button></div>
        <ComparisonPanel :report="comparison" @choose="chooseCandidate"/><div class="review-workbench" :class="{'mobile-source-hidden':!showMobileSource}">
          <SourceViewer :documents="result.documents" :questions="result.questions" :selected="selected" :answer-document-id="answerDoc" :template="result.template" @select="select" @change="refreshRegions" @template-change="markDirty"/>
          <aside class="question-navigator"><div class="pane-heading"><span>题目</span><button class="icon-button" aria-label="新增漏题" title="新增漏题" @click="newQuestion"><Plus :size="16"/></button></div><div class="navigator-filters"><select v-model="paperFilter" aria-label="试卷筛选"><option value="">全部试卷</option><option v-for="p in result.papers" :value="p.id">{{p.title}}</option></select><div class="navigator-tabs"><button :class="{active:filter==='all'}" @click="filter='all'">全部</button><button :class="{active:filter==='pending'}" @click="filter='pending'">待核对</button></div></div><div class="question-nav-list"><button v-for="q in shownQuestions" :key="q.id" :class="{active:q.id===selectedId,reviewed:q.review_status==='reviewed'}" @click="select(q.id)"><span class="q-number">{{q.number}}</span><span class="q-nav-copy"><strong>{{q.attributes.question_type||'题目'}}</strong><small>{{q.attributes.score!=null?q.attributes.score+' 分':'分值未定'}} <span v-if="q.attributes.score_source" :class="['score-source',q.attributes.score_source]">{{scoreSourceName(q.attributes.score_source)}}</span> · {{q.regions.length}} 区域</small></span><Check v-if="q.review_status==='reviewed'" :size="14"/><span v-else-if="q.issues.length" class="issue-indicator"/></button></div><div class="navigator-bottom"><span class="legend-dot"/>待核对 <Check :size="12"/>已确认</div></aside>
          <section class="question-detail" v-if="selected" :key="selected.id"><div class="pane-heading"><span>第 {{selected.number}} 题 <span class="muted">{{result.papers.find(p=>p.id===selected!.paper_id)?.title}}</span></span><div class="question-actions"><button class="icon-button" title="上移题目" aria-label="上移题目" @click="reorder(-1)"><ArrowLeft class="rotate90" :size="15"/></button><button class="icon-button" title="下移题目" aria-label="下移题目" @click="reorder(1)"><ArrowRight class="rotate90" :size="15"/></button><el-dropdown trigger="click"><button class="icon-button" title="题目操作" aria-label="题目操作"><Settings2 :size="17"/></button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="mergeNext">合并下一题</el-dropdown-item><el-dropdown-item @click="splitQuestion">拆出最后区域</el-dropdown-item><el-dropdown-item @click="removeQuestion" divided>删除误识别题目</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div></div>
            <div class="detail-tabs"><button :class="{active:tab==='content'}" @click="tab='content'">题目内容</button><button :class="{active:tab==='attributes'}" @click="tab='attributes'">属性标签</button></div>
            <div class="detail-scroll"><div v-if="noticeIssues.length" class="review-notice"><CircleAlert :size="15"/><span>{{noticeIssues.join('；')}}</span></div>
              <div v-if="selected.corrections?.length" class="correction-panel">
                <details open>
                  <summary><strong>AI 修正 {{selected.corrections.length}} 处</strong><span class="muted">逐条核对；有误可撤销</span></summary>
                  <div v-for="(item,ci) in selected.corrections" :key="ci" class="correction-item">
                    <div class="correction-meta"><span class="correction-field">{{fieldName(item.field||'')}}</span><span class="muted">{{item.reason||'未记录依据'}}</span><button class="text-button" @click="undoCorrection(selected,ci)">撤销此修正</button></div>
                    <p class="correction-before"><em>原文</em>{{item.before||'（未记录）'}}</p>
                    <p class="correction-after"><em>改为</em>{{item.after||'（未记录）'}}</p>
                  </div>
                </details>
              </div>
              <template v-if="tab==='content'">
                <div class="field-heading"><label>题干</label><span>点击文字或公式即可编辑</span></div>
                <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'stem'" v-model="selected.stem" v-model:document="selected.editor_documents.stem" label="题干编辑器"/>
                <div class="field-heading"><label>选项</label><button class="text-button" @click="addOption"><Plus :size="13"/>新增选项</button></div>
                <p v-if="!selected.options.length" class="muted">未识别到选项，点击「新增选项」补齐 A–D，或从原卷补框后重新识别。</p>
                <template v-if="selected.options.length">
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
                  <div class="subquestion-actions"><button class="text-button" @click="sub.options.push({label:String.fromCharCode(65+sub.options.length),content:''})"><Plus :size="13"/>添加选项</button><label>分值 <el-input-number v-model="sub.score" :min="0" :max="1000" @change="syncSubScores"/></label><el-checkbox v-model="sub.requires_manual_drawing_review">需要人工看图</el-checkbox></div>
                  <div class="field-heading"><label>答案来源</label></div>
                  <el-select :model-value="sub.answer_entry_id||''" clearable filterable placeholder="选择小问答案" @change="(value:string)=>value&&matchSubAnswer(value,index)"><el-option v-for="entry in result.answer_entries" :key="entry.id" :value="entry.id" :label="entry.group+' · 第'+entry.number+'题'"/></el-select>
                  <div class="field-heading"><label>答案</label></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-sub-'+index+'-answer'" v-model="sub.answer.value" v-model:document="selected.editor_documents[`sub-${index}-answer`]" label="小问答案"/>
                  <div class="field-heading"><label>解析</label></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-sub-'+index+'-analysis'" v-model="sub.answer.analysis" v-model:document="selected.editor_documents[`sub-${index}-analysis`]" label="小问解析"/>
                  <div v-if="sub.corrections?.length" class="correction-panel compact"><details><summary><strong>AI 修正小问 {{sub.corrections.length}} 处</strong><span class="muted">按“原文”核对</span></summary><div v-for="(item,ci) in sub.corrections" :key="ci" class="correction-item"><div class="correction-meta"><span class="correction-field">{{fieldName(item.field||'')}}</span><span class="muted">{{item.reason||'未记录依据'}}</span></div><p class="correction-before"><em>原文</em>{{item.before||'（未记录）'}}</p><p class="correction-after"><em>改为</em>{{item.after||'（未记录）'}}</p></div></details></div>
                  <div class="field-heading"><label>评分标准</label><span v-if="sub.scoring?.method==='auto'">客观题自动判分</span><span v-else>得分点合计需为100%</span><button v-if="sub.scoring?.method!=='auto'" class="text-button" @click="fillRubric(sub)" :disabled="rubricBusy">{{rubricBusy?'生成中…':'补全评分标准'}}</button><button v-if="sub.scoring?.method==='auto'" class="text-button" @click="makeManualScoring(sub)">改为手动评分</button></div>
                  <p v-if="sub.scoring?.method==='auto'" class="muted">客观题：按标准答案自动判分</p>
                  <template v-else>
                    <div v-if="sub.scoring?.points?.length" class="rubric-list"><div v-for="(point,pi) in sub.scoring.points" :key="pi" class="rubric-item"><el-input-number v-model="point.pct" :min="0" :max="100" :step="5" controls-position="right" class="rubric-pct"/><div class="rubric-criterion"><QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-sub-'+index+'-score-'+pi" v-model="point.criterion" v-model:document="point.editor_document" label="得分点编辑器"/></div><button class="icon-button" aria-label="删除得分点" @click="removeScoringPoint(sub,pi)"><X :size="13"/></button></div></div>
                    <div class="rubric-actions"><button class="text-button" @click="addScoringPoint(sub)"><Plus :size="13"/>添加得分点</button><span :class="{'rubric-total-bad':scoringTotal(sub)!==100}">合计 {{scoringTotal(sub)}}%</span></div>
                    <el-input v-if="sub.scoring?.points?.length" v-model="sub.scoring.notes" placeholder="补充说明，例如其他等价解法参照给分" class="rubric-notes"/>
                  </template>
                </div>
                <template v-if="!selected.subquestions.length">
                  <div class="field-heading"><label>答案</label><span>与题干连续展示，可直接编辑</span></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-single-answer'" v-model="selected.answer" v-model:document="selected.editor_documents.answer" label="答案编辑器"/>
                  <div class="field-heading"><label>解析</label></div>
                  <QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-single-analysis'" v-model="selected.analysis" v-model:document="selected.editor_documents.analysis" label="解析编辑器"/>
                  <div class="field-heading"><label>评分标准</label><span v-if="selected.scoring?.method==='auto'">客观题自动判分</span><span v-else>得分点合计需为100%</span><button v-if="!selected.subquestions?.length && selected.scoring?.method!=='auto'" class="text-button" @click="fillRubric" :disabled="rubricBusy">{{rubricBusy?'生成中…':'补全评分标准'}}</button><button v-if="!selected.subquestions?.length && selected.scoring?.method==='auto'" class="text-button" @click="makeManualScoring(selected)">改为手动评分</button></div>
                  <p v-if="selected.scoring?.method==='auto'" class="muted">客观题：按标准答案自动判分</p>
                  <template v-else>
                    <div v-if="selected.scoring?.points?.length" class="rubric-list"><div v-for="(point,pi) in selected.scoring.points" :key="pi" class="rubric-item"><el-input-number v-model="point.pct" :min="0" :max="100" :step="5" controls-position="right" class="rubric-pct"/><div class="rubric-criterion"><QuestionEditor @image-references="updateImageReferences" @image-layout-change="updateImageLayout" :task-id="task.id" :image-layout="selected.image_layout" :key="selected.id+'-score-'+pi" v-model="point.criterion" v-model:document="point.editor_document" label="得分点编辑器"/></div><button class="icon-button" aria-label="删除得分点" @click="removeScoringPoint(selected,pi)"><X :size="13"/></button></div></div>
                    <div class="rubric-actions"><button class="text-button" @click="addScoringPoint(selected)"><Plus :size="13"/>添加得分点</button><span :class="{'rubric-total-bad':scoringTotal(selected)!==100}">合计 {{scoringTotal(selected)}}%</span></div>
                    <el-input v-if="selected.scoring?.points?.length" v-model="selected.scoring.notes" placeholder="补充说明，例如其他等价解法参照给分" class="rubric-notes"/>
                  </template>
                </template>
                <div class="field-heading"><label>原卷区域</label><button class="text-button" @click="rebuildRegions">重建本题题框与作答区</button><span>{{selected.regions.length}} 个区域，可在左侧拖动调整</span></div>
                <div class="region-preview-list"><div v-for="(r,index) in selected.regions" class="region-preview" :key="index"><img v-if="r.crop_url" :src="r.crop_url" :alt="'第'+selected.number+'题区域'+(index+1)"/><div class="region-caption"><span>区域 {{index+1}} · PDF第 {{r.page_index+1}} 页</span><button class="text-button" @click="recognizeRegion(r,index)">区域识别</button><button v-if="r.crop_url" class="text-button" @click="insertRegionImage(r.crop_url)"><Plus :size="13"/>插入题干</button><select v-model="r.purpose" @change="markDirty" aria-label="区域用途"><option value="">通用</option><option value="content">题目内容</option><option value="both">内容与作答</option><option value="reference_answer">参考答案</option><option value="recovered_visual">原卷补图</option></select></div><div v-if="r.recognition" class="recognition-panel"><div class="recognition-meta"><span>{{categoryName(r.recognition.category)}}</span><span v-if="r.recognition.created_at">{{recognitionTime(r.recognition.created_at)}}</span><span v-if="r.recognition.model">{{r.recognition.model}}</span></div><p v-if="r.recognition.error" class="recognition-error">{{r.recognition.error}}</p><template v-else-if="r.recognition.image_only"><img v-if="r.crop_url" :src="r.crop_url" :alt="'第'+selected.number+'题原卷补图'"/><p class="muted">原卷补图，不调用模型</p></template><QuestionEditor v-else :ref="el=>setRegionEditor(regionKey(selected?.id||'',index),el)" :readonly="true" :task-id="task.id" :image-layout="selected.image_layout" :model-value="r.recognition.markdown||''" v-model:document="r.recognition.editor_document" label="区域识别结果"/><div class="recognition-actions"><button class="text-button" @click="copyRecognition(r,index)">复制</button><button class="text-button" @click="recognizeRegion(r,index)">重新识别</button><button class="text-button" @click="clearRecognition(r)">清空</button></div></div></div></div>
              </template>
              <template v-else><div class="attribute-grid"><label>题号<el-input v-model="selected.number"/></label><label>分值<template v-if="selected.subquestions?.length"><span>{{selected.attributes.score ?? '—'}} 分</span><span class="muted">（小问分值合计）</span><span v-if="subScoresPartial(selected)" class="muted">，还有小问未填分值</span></template><el-input-number v-else v-model="selected.attributes.score" :min="0" :max="1000" @change="markScoreManual"/><span v-if="selected.attributes.score_source" class="score-source">{{scoreSourceName(selected.attributes.score_source)}}</span></label><label v-for="[key,label] in [['subject','学科'],['stage','学段'],['grade','年级'],['textbook_version','教材版本'],['question_type','题型'],['paper_type','试卷类型'],['year','年份'],['semester','学期'],['region','地区'],['source_type','来源类型']]" :key="key">{{label}}<span v-if="selected.attribute_sources?.[key]==='paper'" class="inherit-badge">继承</span><el-input v-model="selected.attributes[key]" placeholder="未识别" @change="markAttributeManual(key)"/></label><label>难度<el-select v-model="selected.attributes.difficulty" clearable><el-option v-for="(name,index) in ['简单','较易','中等','较难','困难']" :value="index+1" :label="name"/></el-select><span v-if="selected.attributes.difficulty_reason" class="muted">{{selected.attributes.difficulty_reason}}</span></label><label>审核状态<el-select v-model="selected.review_status"><el-option value="pending" label="待核对"/><el-option value="reviewed" label="已确认"/></el-select></label></div><div class="inherit-actions"><button v-for="[field,label] in paperInheritFields" :key="field" @click="restoreInherited(field)">跟随{{label}}</button></div><div class="field-heading"><label>知识点与教材章节</label><span class="neutral-badge">目录未配置</span></div><div class="catalog-empty">正式目录接入后自动分层匹配，并根据教材映射章节。当前不生成未经绑定的正式知识点。</div><div class="field-heading"><label>能力维度</label></div><el-select v-model="selected.attributes.ability_dimensions" multiple filterable allow-create default-first-option placeholder="输入或选择能力维度"><el-option v-for="label in ['理解','应用','分析','推理','建模','运算']" :value="label" :label="label"/></el-select><div class="field-heading"><label>作答形式</label></div><el-select v-model="selected.attributes.response_form" multiple filterable allow-create><el-option v-for="label in ['客观','主观','作图','填空','计算','证明']" :value="label" :label="label"/></el-select><div class="field-heading"><label>情景与背景</label></div><el-input v-model="selected.attributes.background" type="textarea" :rows="2"/><div class="field-heading"><label>扩展标签</label><button class="text-button" @click="(selected.attributes.extension_attributes ||= []).push({name:'',value:''})"><Plus :size="13"/>新增</button></div><div class="extension-row" v-for="(tag,index) in selected.attributes.extension_attributes"><el-input v-model="tag.name" placeholder="标签名称"/><el-input v-model="tag.value" placeholder="标签值"/><button class="icon-button" aria-label="删除标签" @click="selected.attributes.extension_attributes.splice(index,1)"><X :size="14"/></button></div><div class="field-heading"><label>授权与排序</label></div><p class="muted">授权尚未确认。重要程度算法未启用，不生成无依据的推荐分。</p></template>
            </div>
            <div class="detail-footer"><button class="text-button" @click="nextQuestion(-1)"><ArrowLeft :size="15"/>上一题</button><el-button type="primary" @click="confirmQuestion"><Check :size="15"/>确认并继续</el-button><button class="text-button" @click="nextQuestion(1)">下一题<ArrowRight :size="15"/></button></div>
          </section><div v-else class="empty-state"><h3>没有题目</h3><el-button @click="newQuestion">添加漏题</el-button></div>
        </div>
      </template>

      <template v-else-if="view==='cost'">
        <div class="page-content cost-page">
          <button class="text-button back-link" @click="closeCost"><ArrowLeft :size="14"/>返回快速录入</button>
          <div class="page-title-row"><div><h1>处理成本</h1><p class="page-description">{{costTask?.title}} · {{formatDate(costTask?.created_at)}} · 任务 {{costTask?.id}}</p></div></div>
          <template v-if="costTask?.cost">
            <div class="cost-summary">
              <div><span>总成本</span><strong>¥{{Number(costTask.cost.total||0).toFixed(6)}}</strong></div>
              <div><span>调用次数</span><strong>{{costTask.cost.calls||0}}</strong></div>
              <div><span>缓存命中</span><strong>{{costTask.cost.cache_hits||0}}</strong></div>
              <div><span>失败/未知</span><strong>{{costTask.cost.unknown_calls||0}}</strong></div>
            </div>
            <p class="muted">金额 = 本次调用 token × 官方单价；MinerU 免费。点击任意一行，查看该次调用的系统指令、用户内容、原始响应和计价过程。</p>
            <div class="cost-table-wrap"><table class="cost-table"><thead><tr><th>时间</th><th>阶段</th><th>模型</th><th>状态</th><th>输入 hit / miss</th><th>输出</th><th>金额</th></tr></thead><tbody>
              <tr v-for="item in costTask.cost.items" :key="item.call_id||item.at||item.operation" :class="{clickable:!!item.call_id,selected:costCallId===item.call_id}" @click="inspectCost(item)">
                <td class="muted">{{formatDate(item.at)}}</td>
                <td><strong>{{item.operation||'调用'}}</strong><small>{{item.channel||''}}</small></td>
                <td>{{item.model||'—'}}</td>
                <td><span :class="['status-pill',item.status==='failed'?'failed':'ready']">{{item.status||item.amount_status}}</span></td>
                <td class="mono">{{item.input_cache_hit_tokens??item.cached_read_tokens??0}} / {{item.input_cache_miss_tokens??(item.input_tokens?item.input_tokens-(item.cached_read_tokens||0):0)}}</td>
                <td class="mono">{{item.output_tokens||0}}</td>
                <td class="mono">¥{{Number(item.amount||0).toFixed(6)}}</td>
              </tr>
            </tbody></table></div>
            <section v-if="costLoading" class="cost-detail"><p class="muted">正在读取调用明细…</p></section>
            <section v-else-if="costDetail" class="cost-detail cost-call">
              <div class="cost-detail-head"><strong>{{costDetail.name}}</strong><span>{{formatDate(costDetail.started_at)}} · {{costDetail.model||'—'}} · {{costDetail.status||''}} · 用时 {{costDetail.seconds??'—'}}s</span><button class="text-button" @click="costDetail=null;costCallId=''">关闭明细</button></div>
              <p class="mono">{{costDetail.usage?.prompt_tokens||0}} 输入 = {{costDetail.usage?.prompt_cache_hit_tokens||0}} hit + {{costDetail.usage?.prompt_cache_miss_tokens||0}} miss · {{costDetail.usage?.completion_tokens||0}} 输出 · ¥{{Number(costDetail.cost?.amount||0).toFixed(8)}}</p>
              <p class="mono">hit×{{costDetail.cost?.unit_price_cny_per_million?.input_cache_hit}} + miss×{{costDetail.cost?.unit_price_cny_per_million?.input_cache_miss}} + output×{{costDetail.cost?.unit_price_cny_per_million?.output}} / 1,000,000</p>
              <div class="prompt-block"><div class="prompt-block-head"><strong>输入 · 系统指令</strong><span>{{(costDetail.system||'').length}} 字符</span><button class="text-button" @click="copyPrompt(costDetail.system)">复制</button></div><pre>{{costDetail.system||'（这次调用没有记录系统指令）'}}</pre></div>
              <div class="prompt-block"><div class="prompt-block-head"><strong>输入 · 用户内容</strong><span>{{(costDetail.user||'').length}} 字符</span><button class="text-button" @click="copyPrompt(costDetail.user)">复制</button></div><pre>{{costDetail.user||'（这次调用没有记录用户内容）'}}</pre></div>
              <div class="prompt-block"><div class="prompt-block-head"><strong>输出 · 原始响应</strong><span>{{costRaw(costDetail).length}} 字符</span><button class="text-button" @click="copyPrompt(costRaw(costDetail))">复制</button></div><pre>{{costRaw(costDetail)||'（这次调用没有记录原始响应）'}}</pre></div>
            </section>
            <div v-else class="cost-empty"><p class="muted">从上方列表选择一次调用，查看完整输入、输出和计价过程。</p></div>
          </template>
          <div v-else class="empty-state"><p>该任务还没有成本记录。</p></div>
        </div>
      </template>

      <template v-else-if="view==='student-zones'">
        <div class="page-content zone-settings-page">
          <div class="page-title-row"><div><h1>学生信息区</h1><p class="page-description">按版面维护学生姓名/班级/学号区域的默认位置，只影响后续新任务。</p></div></div>
          <div class="zone-settings-layout">
            <section class="zone-settings-panel">
              <div class="field-heading"><label>版面类型</label><span>当前只维护 A3 双栏和 A4 单栏</span></div>
              <div class="mode-options">
                <button v-for="item in [{id:'A3-2',title:'A3-2',desc:'A3 两栏'},{id:'A3-3',title:'A3-3',desc:'A3 三栏'},{id:'A4-1',title:'A4-1',desc:'A4 一栏'}]" :key="item.id" :class="{active:zoneLayout===item.id}" @click="selectZoneLayout(item.id as 'A3-2'|'A3-3'|'A4-1')"><strong>{{item.title}}</strong><span>{{item.desc}}</span><Check v-if="zoneLayout===item.id" :size="15"/></button>
              </div>
              <div class="field-heading"><label>预览页</label><span>上传该版面的真实页面</span></div>
              <label class="file-drop zone-upload"><UploadCloud :size="24"/><strong>选择预览文件</strong><span>PDF、PNG、JPG · PDF 取第一页</span><input type="file" accept=".pdf,application/pdf,image/png,image/jpeg,image/webp" @change="zonePreviewFile"/></label>
              <p class="muted">预览图只用于设置，不代表任务原卷。</p>
              <div class="zone-actions"><button class="text-button" @click="resetStudentZone">恢复默认</button><el-button type="primary" :loading="zoneSaving" @click="saveStudentZone">保存默认</el-button></div>
            </section>
            <section class="zone-preview-panel">
              <div v-if="zonePreviewUrl" class="zone-preview-canvas">
                <img :src="zonePreviewUrl" alt="学生信息区预览页" draggable="false"/>
                <svg ref="zoneSvg" viewBox="0 0 1000 1000" preserveAspectRatio="none" @pointermove="zonePointerMove" @pointerup="zonePointerUp" @pointercancel="zonePointerUp">
                  <g><rect :x="zoneBbox[0]*1000" :y="zoneBbox[1]*1000" :width="(zoneBbox[2]-zoneBbox[0])*1000" :height="(zoneBbox[3]-zoneBbox[1])*1000" @pointerdown.stop="zonePointerDown($event)"/><text :x="zoneBbox[0]*1000+4" :y="zoneBbox[1]*1000+13">姓名区</text><rect class="zone-resize" :x="zoneBbox[2]*1000-8" :y="zoneBbox[3]*1000-8" width="10" height="10" @pointerdown.stop="zonePointerDown($event,true)"/></g>
                </svg>
              </div>
              <div v-else-if="zonePreviewPdf" class="empty-state"><Crop :size="34"/><h3>PDF 已选择</h3><p>{{zonePreviewName}} · 点击「保存默认」后按第一页 300dpi 生成预览。</p></div>
              <div v-else class="empty-state"><Crop :size="34"/><h3>还没有预览页</h3><p>上传一张 A3-2 或 A4-1 的真实页面，然后在图上框出学生信息区。</p></div>
              <p class="muted">保存的是默认值；任务内仍可在「模板标注」层单独调整，不会反向修改这里的默认值。</p>
            </section>
          </div>
        </div>
      </template>
      <template v-else-if="view==='questions'||view==='papers'"><div class="page-content"><div class="page-title-row"><div><h1>{{view==='questions'?'题库':'试卷库'}}</h1><p class="page-description">{{view==='questions'?'已保存的题目，连同来源与审核版本一起保留。':'整卷结构、题目引用与原卷模板，统一管理。'}}</p></div><el-button type="primary" @click="createDialog=true"><Plus :size="16"/>录入资料</el-button></div><div class="bank-toolbar"><el-input v-model="bankSearch" placeholder="搜索题目内容" clearable @keyup.enter="loadBank"><template #prefix><Search :size="16"/></template></el-input><el-button @click="loadBank">搜索</el-button><span class="muted">{{bank.length}} 条资源</span></div><div class="bank-list"><button class="bank-item" v-for="item in bank" :key="item.id" @click="openDetail(item)"><template v-if="view==='questions'"><div class="bank-item-meta"><span class="q-number">{{item.number}}</span><span>{{item.content.attributes?.question_type||'题目'}}</span><span class="neutral-badge">{{item.content.attributes?.subject||'未分类'}}</span><span :class="['status-pill',item.status==='incomplete'?'uploaded':'committed']">{{item.status==='incomplete'?'待完善':'已保存'}}</span></div><div class="question-prose bank-question" v-html="renderMarkdown(item.content.stem)"/></template><template v-else><div class="bank-paper-icon"><Files :size="28"/></div><div><h3>{{item.title}}</h3><p>{{modeName(item.mode)}} · {{item.mode==='textbook'?'已保存原卷区域模板':'普通试卷，不启用原卷批阅'}}</p><small>{{formatDate(item.created_at)}}</small></div></template><ChevronRight :size="18" class="bank-chevron"/></button><div class="empty-state" v-if="!bank.length"><Library :size="36"/><h3>这里还没有资源</h3><p>完成审核并入库后，题目或试卷会出现在这里。</p><el-button @click="navigate('tasks')">前往快速录入</el-button></div></div></div></template>
    </main>

    <el-dialog v-model="createDialog" title="新建录入" width="min(760px, 95vw)" :close-on-click-modal="false"><div class="create-form"><label class="form-label">录入方式</label><div class="mode-options"><button v-for="m in [{id:'textbook',title:'教辅卷 / 作业',desc:'题库 + 试卷 + 原卷区域'},{id:'paper',title:'普通整卷',desc:'题库 + 试卷库'},{id:'questions',title:'仅录题目',desc:'只保存到题库'}]" :class="{active:newMode===m.id}" @click="newMode=m.id"><strong>{{m.title}}</strong><span>{{m.desc}}</span><Check v-if="newMode===m.id" :size="15"/></button></div><label class="form-label">任务名称 <span>可选</span></label><el-input v-model="newTitle" placeholder="默认使用首个文件名称"/><label class="form-label">题目文件</label><label class="file-drop" @dragover.prevent @drop="dropFiles"><UploadCloud :size="28"/><strong>点击选择，或拖入文件</strong><span>PDF、JPG、PNG、Word · 支持多个文件</span><input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" @change="chooseFiles($event,'question')"/></label><div class="selected-files" v-for="(file,index) in questionFiles"><FileText :size="15"/><span>{{file.name}}</span><button class="icon-button" aria-label="移除文件" @click="questionFiles.splice(index,1)"><X :size="14"/></button></div><div class="field-heading"><label>答案与解析文件 <span class="muted">可选，可包含其他试卷答案</span></label></div><label class="file-drop answer-file-drop" @dragover.prevent @drop.stop="dropFiles($event,'answer')"><UploadCloud :size="28"/><strong>点击选择，或拖入答案文件</strong><span>PDF、JPG、PNG、Word · 支持多个文件</span><input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" @change="chooseFiles($event,'answer')"/></label><div class="selected-files" v-for="(file,index) in answerFiles"><FileText :size="15"/><span>{{file.name}}</span><button class="icon-button" aria-label="移除答案文件" @click="answerFiles.splice(index,1)"><X :size="14"/></button></div><div class="answer-upload-note" v-if="!answerFiles.length">答案已在原卷中？无需重复上传，系统会自动提取匹配。</div><div class="create-options"><el-checkbox v-model="generate">对缺失的答案和解析使用 AI 生成</el-checkbox><el-select v-model="policy" aria-label="模型渠道策略"><el-option value="compare" label="多模型并行对比（各自计费）"/><el-option value="deepseek" label="DeepSeek Flash"/><el-option value="low_first" label="低价优先，稳定渠道备用"/><el-option value="stable_first" label="稳定渠道优先"/></el-select></div><p class="muted">原文件和识别结果保留。生成内容会标记为待审核，缺少知识点目录不影响录入。</p></div><template #footer><el-button @click="createDialog=false">取消</el-button><el-button type="primary" @click="createTask" :loading="busy">开始识别<ArrowRight :size="16"/></el-button></template></el-dialog>
    <el-dialog v-model="issuesDialog" title="规则检查" width="600px"><div class="check-success" v-if="!validationIssues.length"><CheckCheck :size="26"/>未发现结构性问题，请继续核对识别内容。</div><div class="validation-item" v-for="issue in validationIssues"><CircleAlert :size="17"/><div><strong>{{issueLocation(issue)}} · {{issue.severity==='error'?'阻止入库':'可保存提示'}}</strong><p>{{issue.message}}</p><small v-if="issue.fields">位置：{{issue.fields.map(fieldName).join('、')}}</small><p v-if="issue.hint" class="muted">{{issue.hint}}</p></div><button class="text-button" v-if="issue.question_id" @click="select(issue.question_id);issuesDialog=false">定位</button></div><p class="muted">规则检查通过不代表识别内容准确，仍需人工对照审核。</p></el-dialog>
    <el-drawer v-model="paperOpen" title="试卷信息" size="min(640px,96vw)">
      <template v-if="paperForm">
        <div class="paper-summary">
          <div><span>当前题目合计</span><strong>{{paperTotal(paperForm)}} 分</strong></div>
          <div><span>卷面声明总分</span><strong>{{paperDeclared(paperForm)??'未声明'}}</strong></div>
          <div v-if="paperDiff(paperForm)!==null" :class="{warn:paperDiff(paperForm)!==0}"><span>差额</span><strong>{{(paperDiff(paperForm)||0)>0?'+':''}}{{paperDiff(paperForm)}} 分</strong></div>
        </div>
        <div class="paper-form">
          <label class="wide">卷名<el-input v-model="paperForm.title" @change="paperChanged"/></label>
          <label>学段<el-input v-model="paperForm.attributes.stage" @change="paperChanged"/></label>
          <label>学科<el-input v-model="paperForm.attributes.subject" @change="paperChanged"/></label>
          <label>年级<el-input v-model="paperForm.attributes.grade" @change="paperChanged"/></label>
          <label>教材册次<el-input v-model="paperForm.attributes.textbook_volume" @change="paperChanged"/></label>
          <label>教材版本<el-input v-model="paperForm.attributes.textbook_version" @change="paperChanged"/></label>
          <label>年份<el-input v-model="paperForm.attributes.year" @change="paperChanged"/></label>
          <label>学期<el-input v-model="paperForm.attributes.semester" @change="paperChanged"/></label>
          <label>地区<el-input v-model="paperForm.attributes.region" @change="paperChanged"/></label>
          <label>学校/出版社<el-input v-model="paperForm.attributes.school_publisher" @change="paperChanged"/></label>
          <label>试卷类型<el-select v-model="paperForm.paper_type" clearable @change="paperChanged"><el-option v-for="type in paperTypes" :key="type" :value="type" :label="type"/></el-select></label>
        </div>
        <div class="field-heading"><label>卷面规格</label><span>总分只读，由题目分值合计</span></div>
        <div class="paper-form">
          <label>考试时长（分钟）<el-input-number v-model="paperForm.exam.duration_min" :min="0" :max="1000" @change="paperChanged"/></label>
          <label>卷面声明总分<el-input-number v-model="paperForm.exam.declared_total_score" :min="0" :max="1000" @change="paperChanged"/></label>
          <label>卷面声明题数<el-input-number v-model="paperForm.exam.declared_question_count" :min="0" :max="1000" @change="paperChanged"/></label>
          <label>是否含选做题<el-select v-model="paperForm.exam.has_elective" clearable @change="paperChanged"><el-option :value="true" label="是"/><el-option :value="false" label="否"/></el-select></label>
          <label>是否含听力<el-select v-model="paperForm.exam.has_listening" clearable @change="paperChanged"><el-option :value="true" label="是"/><el-option :value="false" label="否"/></el-select></label>
          <label>答案是否附卷后<el-select v-model="paperForm.exam.answers_at_end" clearable @change="paperChanged"><el-option :value="true" label="是"/><el-option :value="false" label="否"/></el-select></label>
          <label class="wide">考生须知<el-input v-model="paperForm.exam.candidate_notes" type="textarea" :rows="2" @change="paperChanged"/></label>
        </div>
        <div class="field-heading"><label>原卷信息</label><span>页数与栏数由原卷计算，可人工修正</span></div>
        <div class="paper-form">
          <label>物理页数<el-input-number v-model="paperForm.source.page_count" :min="0" :max="1000" @change="paperChanged"/></label>
          <label>印刷页码<el-input :model-value="printedPagesText(paperForm)" placeholder="如 1、2、3" @update:model-value="setPrintedPages(paperForm,$event)"/></label>
        </div>
        <div class="field-heading"><label>人工维护</label></div>
        <div class="paper-form">
          <label>质量等级<el-input v-model="paperForm.manual.quality_level" @change="paperChanged"/></label>
          <label class="wide">自定义标签<el-select v-model="paperForm.manual.tags" multiple filterable allow-create default-first-option placeholder="输入或选择标签" @change="paperChanged"/></label>
        </div>
        <div class="field-heading"><label>系统分节预览</label><span>按题型和题号生成，不写回原卷</span></div>
        <div class="section-preview"><div v-for="row in paperSections(paperForm)" :key="row.label">{{row.text}}</div><p v-if="!paperSections(paperForm).length" class="muted">还没有题目</p></div>
      </template>
    </el-drawer>
    <el-dialog v-model="detailDialog" :title="detail?.title||('题目 '+(detail?.number||''))" width="min(900px, 94vw)"><template v-if="detail"><div v-if="detail.questions" class="paper-detail-list"><div class="template-notice" v-if="detail.templates?.length"><ScanLine :size="17"/>原卷区域模板已保存 · 实际扫描配准尚未接入</div><article v-for="row in detail.questions"><h3>第 {{row.content.number}} 题</h3><QuestionPreview :question="row.content"/></article></div><article v-else><QuestionPreview :question="detail.content"/><div class="region-preview-list"><img v-for="r in detail.content.regions" :src="r.crop_url" alt="来源区域"/></div></article></template><template #footer><el-button @click="detailDialog=false">关闭</el-button><el-button type="primary" @click="detailDialog=false;openTask(tasks.find(t=>t.id===detail.task_id)||{id:detail.task_id,status:'committed'} as Task)">返回来源审核</el-button></template></el-dialog>
  </div>
</template>

<style>
.rubric-list{display:flex;flex-direction:column;gap:4px;margin:4px 0 10px}
.rubric-item{display:flex;gap:8px;align-items:flex-start;background:#f7faf5;border:1px solid #e3ebdd;border-radius:6px;padding:6px 8px;font-size:12px;line-height:1.5}
.rubric-item strong{color:#2d6a45;min-width:40px}
.rubric-item .el-input-number{width:96px;flex:none}
.rubric-item .el-input{flex:1}
.rubric-criterion{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.rubric-criterion .rich-editor{width:100%;min-width:0}
.rubric-item .tiptap{min-height:40px;padding:8px 12px}
.rubric-item .question-prose{min-height:24px}
.rubric-actions{display:flex;align-items:center;gap:12px;margin:6px 0 8px;font-size:12px}
.rubric-total-bad{color:#c45656;font-weight:600}
.rubric-notes{margin-top:6px}
.paper-summary{display:flex;flex-wrap:wrap;gap:10px;padding:12px;border:1px solid #e3ebdd;border-radius:8px;background:#f7faf5;margin-bottom:14px}
.paper-summary>div{display:flex;flex-direction:column;gap:2px;min-width:120px}
.paper-summary span{font-size:11px;color:#7b8a7b}
.paper-summary strong{font-size:15px;color:#2d6a45}
.paper-summary .warn strong{color:#b26a2e}
.paper-form{display:grid;grid-template-columns:1fr 1fr;gap:10px 12px;margin-bottom:14px}
.paper-form label{display:flex;flex-direction:column;gap:4px;font-size:11px;color:#687363}
.paper-form .wide{grid-column:1/-1}
.section-preview{display:flex;flex-direction:column;gap:5px;padding:10px 12px;border:1px solid #e3ebdd;border-radius:7px;background:#fbfcfa;font-size:12px;color:#40584b;margin-bottom:12px}
.inherit-badge{display:inline-block;margin-left:5px;padding:0 4px;border-radius:3px;background:#e8f1e6;color:#4f7259;font-size:10px;font-weight:400}
.inherit-actions{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.inherit-actions button{border:1px solid #dbe6d9;background:#f8fbf6;border-radius:4px;padding:3px 6px;font-size:11px;color:#526b5f}
.score-source{display:inline-block;margin-left:4px;padding:0 4px;border-radius:3px;background:#edf3ed;color:#4f7259;font-size:9px;font-style:normal;vertical-align:1px}
.score-source.ai_assigned{background:#fdf3e6;color:#9a6428}
.score-source.manual{background:#e9f0fa;color:#3c628f}
.recognition-panel{margin:6px 0 12px;border:1px solid #dbe6d9;border-radius:7px;background:#fbfcfa;padding:8px}
.recognition-meta{display:flex;flex-wrap:wrap;gap:8px;font-size:11px;color:#6b7d6b;margin-bottom:6px}
.recognition-meta span+span:before{content:'·';margin-right:8px;color:#b6c3b4}
.recognition-error{color:#a34732;background:#fcf4f0;border:1px solid #efd6cc;border-radius:5px;padding:6px 8px;font-size:12px}
.recognition-actions{display:flex;gap:10px;align-items:center;margin-top:6px}
.recognition-actions button{border:0;background:none;color:#3f7258;font-size:12px;padding:2px 0}
.recognition-panel img{max-width:100%;max-height:260px;display:block;margin:6px 0}
.rich-editor.readonly .tiptap{background:#fbfcfa}
.rich-editor.readonly .tiptap:focus{outline:none}
.cost-page{max-width:none}
.back-link{display:inline-flex;align-items:center;gap:4px;margin-bottom:8px}
.cost-table tbody tr.clickable{cursor:pointer}
.cost-table tbody tr.clickable:hover{background:#f7faf5}
.cost-table tbody tr.selected{background:#eef6ec}
.cost-empty{margin-top:16px;padding:18px;border:1px dashed #dbe5d7;border-radius:7px;text-align:center}
.cost-call{margin-top:16px}
.prompt-block{margin-top:12px;border:1px solid #e2e9df;border-radius:7px;background:#fff;overflow:hidden}
.prompt-block-head{display:flex;align-items:center;gap:10px;padding:8px 12px;background:#f5f8f2;border-bottom:1px solid #e8eee5}
.prompt-block-head strong{font-size:12px;color:#2f5d45}
.prompt-block-head span{font-size:11px;color:#8a998b}
.prompt-block-head button{margin-left:auto}
.cost-detail .prompt-block pre{margin:0;padding:12px;max-height:56vh;overflow:auto;white-space:pre-wrap;word-break:break-word;background:#fff;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;line-height:1.6}
.row-delete{margin-right:6px;color:#8a998b}
.row-delete:hover:not(:disabled){color:#b3452f;background:#fdf1ee}
.row-delete:disabled{opacity:.35;cursor:not-allowed}
.correction-panel{margin:0 0 10px;border:1px solid #f0e0c8;background:#fffaf0;border-radius:7px;padding:8px 10px;font-size:12px}
.correction-panel.compact{margin-top:8px;background:#fffdf7}
.correction-panel summary{cursor:pointer;display:flex;gap:8px;align-items:center;color:#8a6420}
.correction-panel summary strong{font-size:12px}
.correction-item{margin-top:8px;padding-top:8px;border-top:1px dashed #efe2cc}
.correction-item:first-of-type{border-top:0;padding-top:4px}
.correction-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px}
.correction-field{background:#f6ead2;color:#8a6420;border-radius:4px;padding:1px 6px;font-size:11px}
.correction-meta .text-button{margin-left:auto}
.correction-before,.correction-after{margin:2px 0;line-height:1.6;word-break:break-word}
.correction-before em,.correction-after em{font-style:normal;color:#9a8a6a;margin-right:6px;font-size:11px}
.correction-after{color:#3f6b45}
.cloze-blank{white-space:nowrap}
.cloze-index{font-size:0.92em;color:#4a5d4b}
.cloze-line{display:inline-block;min-width:4.2em;border-bottom:1px solid #4a5d4b;margin-left:2px;vertical-align:-2px}
</style>

