<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, Plus, MousePointer2, Trash2 } from 'lucide-vue-next'
import type { Document, Question, Region } from '../types'
const props=defineProps<{documents:Document[];questions:Question[];selected:Question|null;answerDocumentId?:string;template?:any}>()
const emit=defineEmits(['select','change','template-change'])
const docId=ref(''),pageIndex=ref(0),zoom=ref(1),adding=ref(false),selectedRegion=ref(-1)
const layer=ref<'frames'|'blocks'|'template'>('frames')
const frameOnly=ref(false),blockKind=ref('all'),blockMissingOnly=ref(false),templateKind=ref('all'),templateLow=ref(false),templateUnbound=ref(false)
const selectedTemplate=ref<any>(null)
const layerPages=ref<Record<string,number>>({frames:0,blocks:0,template:0})
const layerZooms=ref<Record<string,number>>({frames:1,blocks:1,template:1})
const svg=ref<SVGSVGElement|null>(null)
const canvas=ref<HTMLElement|null>(null)
const doc=computed(()=>props.documents.find(d=>d.id===docId.value)||props.documents[0])
const page=computed(()=>doc.value?.pages[pageIndex.value])
const visible=computed(()=>props.questions.flatMap(q=>q.regions.map((r,i)=>({q,r,i}))).filter(x=>x.r.document_id===doc.value?.id&&x.r.page_index===pageIndex.value))
const pageBlocks=computed(()=>(doc.value?.blocks||[]).filter(b=>b.page_index===pageIndex.value))
const displayBlocks=computed(()=>pageBlocks.value.filter(b=>(blockKind.value==='all'||(b.kind||'text')===blockKind.value)&&(!blockMissingOnly.value||!referencedBlocks.value.has(b.id))))
const referencedBlocks=computed(()=>new Set(props.questions.flatMap(q=>[...(q.block_ids||[]),...(q.subquestions||[]).flatMap(s=>s.block_ids||[])])))
const pageZones=computed(()=>(props.template?.student_zones||[]).filter((z:any)=>z.document_id===doc.value?.id&&z.page_index===pageIndex.value))
const pageAnnotations=computed(()=>{
  const annotations=props.template?.annotations||{}
  return Object.entries(annotations).flatMap(([kind,list]:[string,any])=> (Array.isArray(list)?list:[])
    .filter((item:any)=>item.document_id===doc.value?.id&&item.page_index===pageIndex.value)
    .map((item:any)=>({kind,item})))
})
const displayAnnotations=computed(()=>pageAnnotations.value.filter(a=>a.kind==='brackets'&&(!templateLow.value||(a.item.score||0)<.6)&&(!templateUnbound.value||a.item.bound===false)))
const displayZones=computed(()=>pageZones.value.filter((zone:any)=>zone.role!=='backup'&&(templateKind.value==='all'||templateKind.value==='student')))
const filteredVisible=computed(()=>frameOnly.value&&props.selected?visible.value.filter(x=>x.q.id===props.selected!.id):visible.value)
const bracketFailed=computed(()=>(props.template as any)?.bracket_status==='failed')
const templateStats=computed(()=>{
  const brackets=(props.template?.annotations?.brackets||[])
  return {total:brackets.length,low:brackets.filter((b:any)=>(b.score||0)<.6).length,unbound:brackets.filter((b:any)=>!b.bound).length}
})
function annotationLabel(kind:string){return ({brackets:'括号',question_numbers:'题号',qr:'二维码',drop:'定位点',score_box:'得分框'}[kind]||kind)}
function switchLayer(next:'frames'|'blocks'|'template'){
  if(next===layer.value)return
  layerPages.value[layer.value]=pageIndex.value
  layerZooms.value[layer.value]=zoom.value
  layer.value=next
  pageIndex.value=Math.min(layerPages.value[next]||0,(doc.value?.pages.length||1)-1)
  zoom.value=layerZooms.value[next]||1
}
function blockQuestion(blockId:string){return props.questions.find(q=>[...(q.block_ids||[]),...(q.subquestions||[]).flatMap(s=>s.block_ids||[])].includes(blockId))||null}
function focusBlock(blockId:string){const q=blockQuestion(blockId);if(q){emit('select',q.id);layer.value='frames';pageIndex.value=q.regions[0]?.page_index??pageIndex.value}}
let zoneDrag:{zone:any;mode:string;start:number[];bbox:number[]}|null=null
function zonePoint(e:PointerEvent){const rect=svg.value!.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height))]}
function zoneDown(e:PointerEvent,zone:any,resize=false){e.preventDefault();e.stopPropagation();selectedTemplate.value=zone;svg.value?.setPointerCapture(e.pointerId);const start=zonePoint(e);zoneDrag={zone,mode:resize?'resize':'move',start,bbox:[...zone.bbox]};zone.source='manual'}
function zoneMove(e:PointerEvent){if(!zoneDrag)return;const p=zonePoint(e),dx=p[0]-zoneDrag.start[0],dy=p[1]-zoneDrag.start[1],b=zoneDrag.bbox;if(zoneDrag.mode==='move'){const x=Math.max(0,Math.min(1-(b[2]-b[0]),b[0]+dx)),y=Math.max(0,Math.min(1-(b[3]-b[1]),b[1]+dy));zoneDrag.zone.bbox=[x,y,x+b[2]-b[0],y+b[3]-b[1]]}else zoneDrag.zone.bbox=[b[0],b[1],Math.max(b[0]+.02,p[0]),Math.max(b[1]+.01,p[1])]}
function zoneUp(){if(zoneDrag){emit('template-change');zoneDrag=null}}
function addZone(){if(!props.template)return;props.template.student_zones=props.template.student_zones||[];const zone={id:'sz-manual-'+Date.now(),document_id:doc.value!.id,page_index:pageIndex.value,column:0,bbox:[.02,.01,.98,.11],source:'manual',role:'primary',fields:{name:'',class:'',student_id:''}};props.template.student_zones.push(zone);selectedTemplate.value=zone;emit('template-change')}
function removeZone(zone:any){if(!props.template?.student_zones)return;props.template.student_zones=props.template.student_zones.filter((item:any)=>item!==zone);emit('template-change')}
function deleteTemplateSelection(){
  const target=selectedTemplate.value;if(!target||!props.template)return
  if((props.template.student_zones||[]).includes(target))props.template.student_zones=props.template.student_zones.filter((z:any)=>z!==target)
  else for(const key of Object.keys(props.template.annotations||{}))props.template.annotations[key]=(props.template.annotations[key]||[]).filter((item:any)=>item!==target)
  selectedTemplate.value=null;emit('template-change')
}
function reassignSelected(event:Event){
  const target=selectedTemplate.value;if(!target||!props.template)return
  const questionId=(event.target as HTMLSelectElement).value||null
  target.question_id=questionId;target.bound=!!questionId
  const blank=(props.template.blanks||[]).find((b:any)=>b.blank_id===target.id)
  if(blank){blank.question_id=questionId;blank.bound=!!questionId;blank.bind_reason=questionId?'manual':'unbound'}
  emit('template-change')
}
watch(()=>props.documents,()=>{if(!docId.value&&props.documents.length)docId.value=props.documents[0].id},{immediate:true})
watch(()=>props.selected?.id,()=>{const r=props.selected?.regions[0];if(r){docId.value=r.document_id;pageIndex.value=r.page_index}selectedRegion.value=-1},{immediate:true})
watch(()=>props.answerDocumentId,id=>{if(id){docId.value=id;pageIndex.value=0}})
watch(docId,()=>{if(pageIndex.value>=(doc.value?.pages.length||0))pageIndex.value=0})
let drag:{mode:string;start:number[];bbox:number[];region:Region|null;question:Question|null}|null=null
function point(e:PointerEvent){const rect=svg.value!.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height))]}
function down(e:PointerEvent,r?:Region,q?:Question,index=-1,resize=false){
  if(!props.selected)return
  if(r&&q){if(q.id!==props.selected.id)emit('select',q.id);selectedRegion.value=index}
  if(!adding.value&&!r)return
  e.preventDefault();svg.value?.setPointerCapture(e.pointerId)
  const start=point(e);drag={mode:adding.value?'add':resize?'resize':'move',start,bbox:r?[...r.bbox]:[...start,...start],region:r||null,question:q||props.selected}
  if(adding.value){const nr:Region={document_id:doc.value!.id,page_index:pageIndex.value,bbox:[...start,...start],purpose:'content',order:props.selected.regions.length};props.selected.regions.push(nr);drag.region=nr;selectedRegion.value=props.selected.regions.length-1}
}
function move(e:PointerEvent){if(!drag?.region)return;const p=point(e),dx=p[0]-drag.start[0],dy=p[1]-drag.start[1],b=drag.bbox
  if(drag.mode==='move'){const x=Math.max(0,Math.min(1-(b[2]-b[0]),b[0]+dx)),y=Math.max(0,Math.min(1-(b[3]-b[1]),b[1]+dy));drag.region.bbox=[x,y,x+b[2]-b[0],y+b[3]-b[1]]}
  else if(drag.mode==='resize')drag.region.bbox=[b[0],b[1],Math.max(b[0]+.005,p[0]),Math.max(b[1]+.005,p[1])]
  else drag.region.bbox=[Math.min(drag.start[0],p[0]),Math.min(drag.start[1],p[1]),Math.max(drag.start[0],p[0]),Math.max(drag.start[1],p[1])]
}
function up(){if(drag){if(drag.mode==='add'&&drag.region&&(drag.region.bbox[2]-drag.region.bbox[0]<.004||drag.region.bbox[3]-drag.region.bbox[1]<.004))drag.question!.regions.splice(drag.question!.regions.indexOf(drag.region),1);emit('change');drag=null;adding.value=false}}
function remove(){if(props.selected&&selectedRegion.value>=0){props.selected.regions.splice(selectedRegion.value,1);selectedRegion.value=-1;emit('change')}}
async function focusQuestion(){const r=props.selected?.regions[0];if(!r)return;docId.value=r.document_id;pageIndex.value=r.page_index;zoom.value=Math.min(3,Math.max(1,.8/(r.bbox[2]-r.bbox[0])));await nextTick();if(canvas.value&&svg.value){const w=svg.value.clientWidth,h=svg.value.clientHeight;canvas.value.scrollTo({left:Math.max(0,r.bbox[0]*w-24),top:Math.max(0,r.bbox[1]*h-24),behavior:'smooth'})}}
</script>
<template>
  <section class="source-viewer">
    <div class="pane-heading"><span>原始资料</span><div class="layer-tabs"><button :class="{active:layer==='frames'}" @click="switchLayer('frames')">题框</button><button :class="{active:layer==='blocks'}" @click="switchLayer('blocks')">MinerU 识别块</button><button :class="{active:layer==='template'}" @click="switchLayer('template')">模板标注</button></div></div>
    <div class="source-tools"><select v-model="docId" aria-label="原卷文件"><option v-for="d in documents" :value="d.id" :key="d.id">{{d.name}}</option></select><button title="缩小" aria-label="缩小" @click="zoom=Math.max(.6,zoom-.2)"><ZoomOut :size="16"/></button><span>{{Math.round(zoom*100)}}%</span><button aria-label="定位本题" title="放大并定位本题" @click="focusQuestion">定位</button><button title="放大" aria-label="放大" @click="zoom=Math.min(3,zoom+.2)"><ZoomIn :size="16"/></button></div>
    <div v-if="layer==='template'" class="template-stats"><template v-if="bracketFailed">括号检测未完成（重新处理任务后再试）</template><template v-else>共 {{templateStats.total}} 个空 · 低置信度 {{templateStats.low}} 个 · 未绑定 {{templateStats.unbound}} 个</template></div>
    <div class="layer-filters" v-if="layer==='frames'"><label><input type="checkbox" v-model="frameOnly"/>只看当前题</label></div>
    <div class="layer-filters" v-else-if="layer==='blocks'"><select v-model="blockKind"><option value="all">全部类型</option><option value="text">文字</option><option value="header">页眉</option><option value="footer">页脚</option><option value="page_number">页码</option><option value="table">表格</option><option value="image">图片</option></select><label><input type="checkbox" v-model="blockMissingOnly"/>只看未引用</label></div>
    <div class="layer-filters" v-else><select v-model="templateKind"><option value="all">全部标注</option><option value="student">学生信息区</option><option value="brackets">括号</option></select><label><input type="checkbox" v-model="templateLow"/>只看低置信度</label><label><input type="checkbox" v-model="templateUnbound"/>只看未绑定</label><select v-if="selectedTemplate?.label" :value="selectedTemplate.question_id||''" @change="reassignSelected" aria-label="修改归属题目"><option value="">未绑定</option><option v-for="q in questions" :key="q.id" :value="q.id">第 {{q.number}} 题</option></select></div>
    <div ref="canvas" class="source-canvas"><div class="paper-image" v-if="page" :style="{width:`${zoom*100}%`}"><img :src="page.image_url" alt="原始试卷页面" draggable="false"/>
      <svg v-if="layer==='frames'" ref="svg" viewBox="0 0 1000 1000" preserveAspectRatio="none" @pointerdown="down($event)" @pointermove="move" @pointerup="up" @pointercancel="up" :class="{drawing:adding}">
        <g v-for="({q,r,i},index) in filteredVisible" :key="q.id+'-'+i" :class="{selected:q.id===selected?.id}">
          <rect :x="r.bbox[0]*1000" :y="r.bbox[1]*1000" :width="(r.bbox[2]-r.bbox[0])*1000" :height="(r.bbox[3]-r.bbox[1])*1000" @pointerdown.stop="down($event,r,q,i)"/>
          <text :x="r.bbox[0]*1000+4" :y="r.bbox[1]*1000+15">{{q.number}}</text>
          <rect v-if="q.id===selected?.id" class="resize-handle" :x="r.bbox[2]*1000-5" :y="r.bbox[3]*1000-5" width="10" height="10" @pointerdown.stop="down($event,r,q,i,true)"/>
        </g>
      </svg>
      <svg v-else-if="layer==='blocks'" ref="svg" viewBox="0 0 1000 1000" preserveAspectRatio="none" class="block-layer">
        <g v-for="block in displayBlocks" :key="block.id" :class="['block-rect',block.kind,{missing:!referencedBlocks.has(block.id)&&!['header','footer','page_number'].includes(block.kind||'text')}]" @click="focusBlock(block.id)">
          <rect :x="block.bbox[0]*1000" :y="block.bbox[1]*1000" :width="(block.bbox[2]-block.bbox[0])*1000" :height="(block.bbox[3]-block.bbox[1])*1000"><title>{{block.kind}} · {{(block.text||'').slice(0,40)}}</title></rect>
          <text :x="block.bbox[0]*1000+3" :y="block.bbox[1]*1000+12">{{block.kind}}</text>
        </g>
      </svg>
      <svg v-else ref="svg" viewBox="0 0 1000 1000" preserveAspectRatio="none" class="template-layer" @pointermove="zoneMove" @pointerup="zoneUp" @pointercancel="zoneUp">
        <g v-for="a in displayAnnotations" :key="a.item.id" :class="['annotation',a.kind,{low:(a.item.score||0)<.6,unbound:a.item.bound===false,selected:selectedTemplate===a.item}]">
          <rect :x="a.item.bbox[0]*1000" :y="a.item.bbox[1]*1000" :width="(a.item.bbox[2]-a.item.bbox[0])*1000" :height="(a.item.bbox[3]-a.item.bbox[1])*1000" @pointerdown.stop="zoneDown($event,a.item)"><title>括号 · 置信度 {{Math.round((a.item.score||0)*100)}}%{{a.item.bound===false?' · 未绑定':''}}</title></rect>
        </g>
        <g v-for="zone in displayZones" :key="zone.id" :class="{selected:selectedTemplate===zone}">
          <rect :x="zone.bbox[0]*1000" :y="zone.bbox[1]*1000" :width="(zone.bbox[2]-zone.bbox[0])*1000" :height="(zone.bbox[3]-zone.bbox[1])*1000" @pointerdown.stop="zoneDown($event,zone)"><title>{{zone.role==='backup'?'学生信息区（备用）':'学生信息区'}} · {{zone.source}}</title></rect>
          <text :x="zone.bbox[0]*1000+4" :y="zone.bbox[1]*1000+13">{{zone.role==='backup'?'姓名区·备用':'姓名区'}}</text>
          <rect class="zone-resize" :x="zone.bbox[2]*1000-8" :y="zone.bbox[3]*1000-8" width="10" height="10" @pointerdown.stop="zoneDown($event,zone,true)"/>
        </g>
      </svg>
    </div><div v-else class="empty-inline">暂无原卷页面</div></div>
    <div class="source-footer"><div class="region-tools" v-if="layer==='frames'"><button :class="{active:adding}" @click="adding=!adding" title="拖动新增题框"><Plus :size="15"/>补框</button><button @click="remove" :disabled="selectedRegion<0"><Trash2 :size="15"/>删框</button></div><div class="region-tools" v-else-if="layer==='template'"><button @click="addZone"><Plus :size="15"/>学生信息区</button><button @click="deleteTemplateSelection" :disabled="!selectedTemplate"><Trash2 :size="15"/>删除选中</button><span class="muted">拖动移动，右下角缩放</span></div><div class="region-tools" v-else><span class="muted">识别块只读，点击定位引用题目</span></div><div class="page-controls"><button aria-label="上一页" :disabled="pageIndex===0" @click="pageIndex--"><ChevronLeft :size="16"/></button><span>{{pageIndex+1}} / {{doc?.pages.length||0}} 页</span><button aria-label="下一页" :disabled="pageIndex+1>=(doc?.pages.length||0)" @click="pageIndex++"><ChevronRight :size="16"/></button></div></div>
    <p class="source-hint">{{layer==='frames'?'框选按 PDF 物理页定位；跨栏、跨页题可保留多个区域。':layer==='blocks'?'MinerU 段落块只读；未引用块高亮，点击定位题目。':'学生信息区按页保存，人工调整后不会被默认值覆盖。'}}</p>
  </section>
</template>
