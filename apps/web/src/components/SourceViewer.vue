<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, Plus, MousePointer2, Trash2 } from 'lucide-vue-next'
import type { Document, Question, Region } from '../types'
const props=defineProps<{documents:Document[];questions:Question[];selected:Question|null;answerDocumentId?:string}>()
const emit=defineEmits(['select','change'])
const docId=ref(''),pageIndex=ref(0),zoom=ref(1),adding=ref(false),selectedRegion=ref(-1)
const svg=ref<SVGSVGElement|null>(null)
const canvas=ref<HTMLElement|null>(null)
const doc=computed(()=>props.documents.find(d=>d.id===docId.value)||props.documents[0])
const page=computed(()=>doc.value?.pages[pageIndex.value])
const visible=computed(()=>props.questions.flatMap(q=>q.regions.map((r,i)=>({q,r,i}))).filter(x=>x.r.document_id===doc.value?.id&&x.r.page_index===pageIndex.value))
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
    <div class="pane-heading"><span>原始资料</span><span class="subtle">题框与原卷对照</span></div>
    <div class="source-tools"><select v-model="docId" aria-label="原卷文件"><option v-for="d in documents" :value="d.id" :key="d.id">{{d.name}}</option></select><button title="缩小" aria-label="缩小" @click="zoom=Math.max(.6,zoom-.2)"><ZoomOut :size="16"/></button><span>{{Math.round(zoom*100)}}%</span><button aria-label="定位本题" title="放大并定位本题" @click="focusQuestion">定位</button><button title="放大" aria-label="放大" @click="zoom=Math.min(3,zoom+.2)"><ZoomIn :size="16"/></button></div>
    <div ref="canvas" class="source-canvas"><div class="paper-image" v-if="page" :style="{width:`${zoom*100}%`}"><img :src="page.image_url" alt="原始试卷页面" draggable="false"/><svg ref="svg" viewBox="0 0 1000 1000" preserveAspectRatio="none" @pointerdown="down($event)" @pointermove="move" @pointerup="up" @pointercancel="up" :class="{drawing:adding}">
      <g v-for="({q,r,i},index) in visible" :key="q.id+'-'+i" :class="{selected:q.id===selected?.id}">
        <rect :x="r.bbox[0]*1000" :y="r.bbox[1]*1000" :width="(r.bbox[2]-r.bbox[0])*1000" :height="(r.bbox[3]-r.bbox[1])*1000" @pointerdown.stop="down($event,r,q,i)"/>
        <text :x="r.bbox[0]*1000+4" :y="r.bbox[1]*1000+15">{{q.number}}</text>
        <rect v-if="q.id===selected?.id" class="resize-handle" :x="r.bbox[2]*1000-5" :y="r.bbox[3]*1000-5" width="10" height="10" @pointerdown.stop="down($event,r,q,i,true)"/>
      </g>
    </svg></div><div v-else class="empty-inline">暂无原卷页面</div></div>
    <div class="source-footer"><div class="region-tools"><button :class="{active:adding}" @click="adding=!adding" title="拖动新增题框"><Plus :size="15"/>补框</button><button @click="remove" :disabled="selectedRegion<0"><Trash2 :size="15"/>删框</button></div><div class="page-controls"><button aria-label="上一页" :disabled="pageIndex===0" @click="pageIndex--"><ChevronLeft :size="16"/></button><span>{{pageIndex+1}} / {{doc?.pages.length||0}} 页</span><button aria-label="下一页" :disabled="pageIndex+1>=(doc?.pages.length||0)" @click="pageIndex++"><ChevronRight :size="16"/></button></div></div>
    <p class="source-hint">框选按 PDF 物理页定位；跨栏、跨页题可保留多个区域。</p>
  </section>
</template>
