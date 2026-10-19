<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import { Node, mergeAttributes } from '@tiptap/core'
import { Bold, Italic, List, Sigma, ImagePlus, Table2, Code2, Undo2, Square, Superscript, Brackets, Grid2X2, Divide } from 'lucide-vue-next'
import { MathfieldElement } from 'mathlive'
import katex from 'katex'
import { prepareEditorDocument } from '../render'

const props=defineProps<{modelValue:string;document?:any;label?:string;taskId?:string;imageLayout?:Record<string,any>}>()
const emit=defineEmits(['update:modelValue','update:document','image-references','image-layout-change'])
const mathDialog=ref(false), formula=ref(''), mathfield=ref<HTMLElement|null>(null), keyboardHost=ref<HTMLElement|null>(null)
let selectedPosition:number|null=null, updating=false
MathfieldElement.fontsDirectory='/mathlive-fonts'
const MathNode=Node.create({
  name:'mathInline', group:'inline', inline:true, atom:true,
  addAttributes(){return {latex:{default:''},display:{default:false}}},
  parseHTML(){return [{tag:'span[data-type="math-inline"]',getAttrs:el=>({latex:(el as HTMLElement).dataset.latex||'',display:(el as HTMLElement).dataset.display==='true'})}]},
  renderHTML({HTMLAttributes}){return ['span',mergeAttributes(HTMLAttributes,{'data-type':'math-inline','data-latex':HTMLAttributes.latex,'data-display':String(HTMLAttributes.display)}),HTMLAttributes.latex]},
  addNodeView(){return ({node,getPos})=>{
    const dom=document.createElement('span');dom.className='editable-formula';dom.setAttribute('role','button');dom.setAttribute('tabindex','0');dom.title='点击编辑公式'
    dom.innerHTML=katex.renderToString(node.attrs.latex,{throwOnError:false,displayMode:!!node.attrs.display,trust:false})
    const edit=()=>{selectedPosition=typeof getPos==='function'?(getPos()??null):null;formula.value=node.attrs.latex;mathDialog.value=true}
    dom.addEventListener('click',edit);dom.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();edit()}})
    return {dom}
  }}
})
function serialize(node:any):string {
  if(node.type==='text'){let text=node.text||'';for(const mark of node.marks||[]){if(mark.type==='bold')text='**'+text+'**';if(mark.type==='italic')text='*'+text+'*';if(mark.type==='strike')text='~~'+text+'~~'}return text}
  if(node.type==='mathInline')return node.attrs.display?`$$${node.attrs.latex}$$`:`$${node.attrs.latex}$`
  if(node.type==='image')return `![${node.attrs.caption||''}](${node.attrs.src})`
  if(node.type==='hardBreak')return '\n'
  const inner=(node.content||[]).map(serialize).join('')
  if(node.type==='paragraph')return inner+'\n\n'
  if(node.type==='bulletList'||node.type==='orderedList')return inner+'\n'
  if(node.type==='listItem')return '- '+inner.trim()+'\n'
  if(node.type==='table')return '<table>'+inner+'</table>\n'
  if(node.type==='tableRow')return '<tr>'+inner+'</tr>'
  if(node.type==='tableCell')return '<td>'+inner+'</td>'
  if(node.type==='tableHeader')return '<th>'+inner+'</th>'
  return inner
}
const selectedImage=ref<any>(null)
let selectedImagePos:number|null=null
const LayoutImage=Image.extend({
  addAttributes(){return {...this.parent?.(),widthPct:{default:60,parseHTML:element=>Number(element.dataset.widthPct)||60,
    renderHTML:attributes=>({'data-width-pct':attributes.widthPct||60})},
    manualSize:{default:false},layoutVersion:{default:null},caption:{default:'',parseHTML:el=>el.dataset.caption||''}}},
  parseHTML(){return [{tag:'span[data-type="layout-image"]',getAttrs:el=>{
    const span=el as HTMLElement,img=span.querySelector('img');return {src:img?.getAttribute('src'),alt:img?.getAttribute('alt'),caption:img?.dataset.caption||img?.getAttribute('alt')||'',widthPct:Number(span.dataset.widthPct)||60}
  }},{tag:'img[src]',getAttrs:el=>({src:(el as HTMLElement).getAttribute('src'),alt:(el as HTMLElement).getAttribute('alt'),caption:(el as HTMLElement).dataset.caption||(el as HTMLElement).getAttribute('alt')||''})}]},
  renderHTML({HTMLAttributes}){return ['span',{'data-type':'layout-image',class:'image-figure',style:`width:${HTMLAttributes['data-width-pct']||60}%;`,'data-width-pct':HTMLAttributes['data-width-pct']},['img',mergeAttributes(HTMLAttributes,{style:'width:100%;height:auto;'})],['span',{class:'image-caption'},HTMLAttributes.caption||'']]},
  addNodeView(){return ({node,getPos,editor})=>{
    const dom=document.createElement('span');dom.className='image-figure';dom.contentEditable='false'
    dom.style.width=`${node.attrs.widthPct||60}%`;dom.dataset.widthPct=String(node.attrs.widthPct||60)
    const img=document.createElement('img');img.src=node.attrs.src;img.alt=node.attrs.alt||'题目图片';img.style.width='100%';img.style.height='auto';dom.append(img)
    if(node.attrs.caption){const cap=document.createElement('span');cap.className='image-caption';cap.textContent=node.attrs.caption;dom.append(cap)}
    const handle=document.createElement('button');handle.className='image-resize-handle';handle.type='button';handle.title='拖动调整图片大小';handle.setAttribute('aria-label','拖动调整图片大小');dom.append(handle)
    dom.addEventListener('click',()=>{selectedImage.value={...node.attrs};const p=getPos();if(typeof p==='number'){selectedImagePos=p;editor.commands.setNodeSelection(p)}})
    handle.addEventListener('pointerdown',event=>{
      event.preventDefault();event.stopPropagation();const start=event.clientX,width=dom.getBoundingClientRect().width,container=dom.closest('.question-prose')?.clientWidth||width
      let pct=node.attrs.widthPct||60;handle.setPointerCapture(event.pointerId)
      const move=(e:PointerEvent)=>{pct=Math.max(5,Math.min(100,(width+e.clientX-start)/container*100));dom.style.width=`${pct}%`}
    const up=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',up);handle.removeEventListener('pointercancel',up);const p=getPos();if(typeof p==='number'){selectedImagePos=p;selectedImage.value={...node.attrs,widthPct:pct,manualSize:true};editor.chain().setNodeSelection(p).updateAttributes('image',{widthPct:pct,manualSize:true}).run();emit('image-layout-change',{src:node.attrs.src,widthPct:pct,manual:true})}}
      handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',up);handle.addEventListener('pointercancel',up)
    })
    return {dom,stopEvent:event=>event.target===handle}
  }}
})
function resizeImage(value:number){if(!editor.value||!selectedImage.value||selectedImagePos===null)return;editor.value.chain().setNodeSelection(selectedImagePos).updateAttributes('image',{widthPct:value,manualSize:true}).run();selectedImage.value={...selectedImage.value,widthPct:value,manualSize:true};emit('image-layout-change',{src:selectedImage.value.src,widthPct:value,manual:true})}
function resetImage(){if(!editor.value||!selectedImage.value||selectedImagePos===null)return;const src=selectedImage.value.src;const value=props.imageLayout?.[src]?.render_width_pct||60;editor.value.chain().setNodeSelection(selectedImagePos).updateAttributes('image',{widthPct:value,manualSize:false}).run();selectedImage.value={...selectedImage.value,widthPct:value,manualSize:false};emit('image-layout-change',{src,widthPct:value,manual:false})}

const uploading=ref(0),uploadError=ref('')
const editor=useEditor({extensions:[StarterKit,LayoutImage.configure({inline:true,allowBase64:false}),Table.configure({resizable:true}),TableRow,TableHeader,TableCell,MathNode],
  content:prepareEditorDocument(props.document,props.modelValue,props.imageLayout),
  onCreate:({editor})=>{
    const captionUpdates:{pos:number;caption:string}[]=[]
    editor.state.doc.descendants((node,pos)=>{
      if(node.type.name!=='image')return
      const meta=props.imageLayout?.[node.attrs.src]||{}
      const caption=Array.isArray(meta.caption)?meta.caption.join(' '):meta.caption||node.attrs.caption||node.attrs.alt||''
      if(caption&&caption!==node.attrs.caption)captionUpdates.push({pos,caption})
      if(selectedImagePos===null){selectedImagePos=pos;selectedImage.value={...node.attrs,caption}}
    })
    if(captionUpdates.length)editor.commands.command(({tr})=>{for(const update of captionUpdates){const node=tr.doc.nodeAt(update.pos);if(node)tr.setNodeMarkup(update.pos,undefined,{...node.attrs,caption:update.caption})}return true})
  },
  onSelectionUpdate:({editor})=>{if(editor.isActive('image')){selectedImage.value={...editor.getAttributes('image')};selectedImagePos=editor.state.selection.from}},
  editorProps:{attributes:{class:'question-prose',role:'textbox','aria-multiline':'true','aria-label':props.label||'题目内容编辑器'},
    handleClick:(view,pos,event)=>{
      const target=event.target as HTMLElement
      if(target.closest('.image-figure')){
        const imagePos=view.posAtCoords({left:event.clientX,top:event.clientY})?.pos
        if(imagePos!=null){const pos=view.state.doc.nodeAt(imagePos)?.type.name==='image'?imagePos:imagePos-1;const node=view.state.doc.nodeAt(pos);if(node?.type.name==='image'){selectedImage.value={...node.attrs};selectedImagePos=pos;editor.value?.commands.setNodeSelection(pos);return true}}
      }
      return false
    },
    handlePaste:(_view,event)=>{
      const files=Array.from(event.clipboardData?.files||[]).filter(f=>f.type.startsWith('image/'))
      if(!files.length)return false
      event.preventDefault();void uploadImages(files);return true
    },
    handleDrop:(view,event,moved)=>{
      if(moved)return false
      const files=Array.from(event.dataTransfer?.files||[]).filter(f=>f.type.startsWith('image/'))
      if(!files.length)return false
      event.preventDefault()
      const position=view.posAtCoords({left:event.clientX,top:event.clientY})
      if(position)editor.value?.commands.setTextSelection(position.pos)
      void uploadImages(files);return true
    }},
  onUpdate:({editor})=>{
    updating=true
    if(editor.isActive('image')){selectedImage.value={...editor.getAttributes('image')};selectedImagePos=editor.state.selection.from}
    const source=serialize(editor.getJSON()).trim()
    const images=(text:string)=>Array.from(text.matchAll(/!\[[^\]]*\]\((\/api\/assets\?key=[^)]+)\)/g),m=>m[1])
    const old=images(props.modelValue),current=images(source)
    emit('update:modelValue',source);emit('update:document',editor.getJSON())
    emit('image-references',{removed:old.filter(url=>!current.includes(url)),added:current.filter(url=>!old.includes(url))})
    updating=false
  }
})
watch(()=>[props.modelValue,props.document],()=>{if(!updating&&editor.value&&!editor.value.isFocused)editor.value.commands.setContent(prepareEditorDocument(props.document,props.modelValue,props.imageLayout),{emitUpdate:false})})
watch(mathDialog,async value=>{if(value){setTimeout(()=>{if(mathfield.value)(mathfield.value as MathfieldElement).value=formula.value},60)}})
watch(formula,value=>{const field=mathfield.value as MathfieldElement|null;if(field&&field.value!==value)field.value=value})
function formulaOpened(){
  const field=mathfield.value as MathfieldElement|null, keyboard=(window as any).mathVirtualKeyboard
  if(!field||!keyboardHost.value||!keyboard)return
  field.value=formula.value
  field.mathVirtualKeyboardPolicy='manual'
  keyboard.container=keyboardHost.value
  field.focus()
  keyboard.show({animate:false})
}
function closeKeyboard(){
  const keyboard=(window as any).mathVirtualKeyboard
  if(keyboard&&keyboardHost.value?.contains(document.querySelector('.ML__keyboard'))){
    keyboard.hide({animate:false})
    keyboard.container=null
  }
}
function onFormulaInput(event:Event){formula.value=(event.target as MathfieldElement).value}
function openFormula(){selectedPosition=null;formula.value='';mathDialog.value=true}
function applyFormula(){
  if(!editor.value)return
  if(selectedPosition!==null)editor.value.chain().focus().setNodeSelection(selectedPosition).updateAttributes('mathInline',{latex:formula.value}).run()
  else editor.value.chain().focus().insertContent({type:'mathInline',attrs:{latex:formula.value}}).run()
  mathDialog.value=false
}
function useTemplate(value:string){
  formula.value=value
  setTimeout(()=>{if(mathfield.value)(mathfield.value as MathfieldElement).value=formula.value},30)
}
const imageDialog=ref(false)
async function uploadImages(files:File[]){
  const target=editor.value,taskId=props.taskId
  if(!target||!files.length)return
  if(!taskId){ElMessage.error('当前题目没有任务信息，请重新打开审核页面');return}
  if(files.some(f=>f.size>20*1024*1024)){ElMessage.warning('单张图片不能超过20MB');return}
  let bookmark=target.state.selection.getBookmark()
  const map=({transaction}:any)=>{bookmark=bookmark.map(transaction.mapping)}
  target.on('transaction',map)
  uploading.value++;uploadError.value=''
  try{
    const uploaded=await Promise.all(files.map(async file=>{
      const form=new FormData();form.append('file',file)
      return (await axios.post(`/api/quick-entry/tasks/${taskId}/images`,form,{timeout:120000})).data
    }))
    if(target.isDestroyed)return
    const selection=bookmark.resolve(target.state.doc)
    target.chain().command(({tr})=>{tr.setSelection(selection);return true})
      .insertContent(uploaded.map(asset=>({type:'image',attrs:{src:asset.url,alt:asset.name||'补充图片',widthPct:60}}))).run()
    imageDialog.value=false
    ElMessage.success('图片已插入，随草稿保存')
  }catch(e:any){uploadError.value=e.response?.data?.message||e.message||'图片上传失败，请重试';ElMessage.error(uploadError.value)}
  finally{target.off('transaction',map);uploading.value--}
}
function chooseImages(event:Event){const input=event.target as HTMLInputElement;void uploadImages(Array.from(input.files||[]));input.value=''}
function dropImages(event:DragEvent){event.preventDefault();void uploadImages(Array.from(event.dataTransfer?.files||[]).filter(f=>f.type.startsWith('image/')))}
onBeforeUnmount(()=>editor.value?.destroy())
</script>

<template>
  <div class="rich-editor" v-if="editor">
    <div class="editor-toolbar">
      <button title="加粗" aria-label="加粗" @click="editor.chain().focus().toggleBold().run()"><Bold :size="15"/></button>
      <button title="斜体" aria-label="斜体" @click="editor.chain().focus().toggleItalic().run()"><Italic :size="15"/></button>
      <button title="列表" aria-label="列表" @click="editor.chain().focus().toggleBulletList().run()"><List :size="15"/></button>
      <span class="toolbar-separator"/>
      <button title="插入公式" @click="openFormula"><Sigma :size="16"/><span>公式</span></button>
      <button title="插入图片，也可直接粘贴截图" aria-label="插入图片" @click="imageDialog=true"><ImagePlus :size="16"/></button>
      <button title="插入表格" aria-label="插入表格" @click="editor.chain().focus().insertTable({rows:2,cols:3,withHeaderRow:false}).run()"><Table2 :size="16"/></button>
      <button title="撤销" aria-label="撤销" @click="editor.chain().focus().undo().run()"><Undo2 :size="15"/></button>
    </div>
    <div class="image-size-controls" v-if="selectedImage"><label>图片宽度 <input aria-label="图片宽度百分比" type="range" min="5" max="100" :value="selectedImage.widthPct||60" @input="resizeImage(Number(($event.target as HTMLInputElement).value))"/></label><span>{{Math.round(selectedImage.widthPct||60)}}%</span><button class="text-button" @click="resetImage">恢复参考尺寸</button><span class="muted">保持比例，也可拖动图片右下角</span></div>
    <EditorContent :editor="editor" />
    <p v-if="uploading" class="editor-upload-status" role="status">正在上传 {{uploading}} 组图片，请稍候…</p>
    <p v-if="uploadError" class="editor-upload-error" role="alert">{{uploadError}}</p>
    <el-dialog v-model="mathDialog" title="编辑公式" width="min(760px, 96vw)" top="3vh" class="formula-dialog" append-to-body :close-on-click-modal="false" @opened="formulaOpened" @close="closeKeyboard" @close-auto-focus="closeKeyboard">
      <div class="formula-toolbar" aria-label="公式结构模板">
        <span>结构模板</span>
        <button title="分数" @click="useTemplate('\\frac{□}{□}')"><Divide :size="16"/><span>分数</span></button>
        <button title="上下标" @click="useTemplate('x^{□}_{□}')"><Superscript :size="16"/><span>上下标</span></button>
        <button title="根式" @click="useTemplate('\\sqrt{□}')"><Square :size="16"/><span>根式</span></button>
        <button title="括号" @click="useTemplate('\\left(□\\right)')"><Brackets :size="16"/><span>括号</span></button>
        <button title="矩阵" @click="useTemplate('\\begin{matrix}□&□\\\\□&□\\end{matrix}')"><Grid2X2 :size="16"/><span>矩阵</span></button>
      </div>
      <math-field ref="mathfield" class="formula-input" @input="onFormulaInput" math-virtual-keyboard-policy="manual"/>
      <label class="formula-label">LaTeX 源码</label>
      <el-input v-model="formula" type="textarea" :rows="2" placeholder="例如：\frac{-b\pm\sqrt{b^2-4ac}}{2a}"/>
      <div class="formula-preview" v-html="katex.renderToString(formula,{throwOnError:false,displayMode:true,trust:false})"/>
      <div ref="keyboardHost" class="formula-keyboard-host"/>
      <template #footer><el-button @click="mathDialog=false">取消</el-button><el-button type="primary" @click="applyFormula">插入公式</el-button></template>
    </el-dialog>
    <el-dialog v-model="imageDialog" title="插入图片" width="min(480px, 94vw)" append-to-body>
      <p>截图后关闭此窗口，在编辑器中按 Ctrl+V 即可插入。也可以选择或拖入图片。</p>
      <label class="file-drop image-file-drop" @dragover.prevent @drop="dropImages"><ImagePlus :size="28"/><strong>选择图片，或拖到这里</strong><span>PNG、JPEG、WebP · 单张不超过20MB</span><input type="file" multiple accept="image/png,image/jpeg,image/webp" @change="chooseImages" :disabled="!!uploading"/></label>
      <p v-if="uploading" role="status">正在上传图片…</p><p v-if="uploadError" class="editor-upload-error" role="alert">{{uploadError}}</p>
      <template #footer><el-button @click="imageDialog=false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<style>
.formula-toolbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.formula-toolbar>span{font-size:11px;color:#7b896f;margin-right:4px}
.formula-toolbar button{display:flex;align-items:center;gap:4px;border:1px solid #d8e2cf;background:#f7faf3;color:#4c6b3f;border-radius:4px;padding:5px 8px;font-size:11px}
.formula-label{display:block;font-size:11px;color:#6f7f63;margin:14px 0 6px}
.formula-keyboard-host{position:relative;height:310px;isolation:isolate;--keyboard-zindex:100;--keycap-height:42px;--keycap-font-size:20px}
.formula-keyboard-host .ML__keyboard{position:relative!important;inset:auto!important;width:100%!important;pointer-events:auto}
.formula-dialog{max-height:94vh;overflow:auto}
.formula-dialog .el-dialog__body{max-height:calc(94vh - 120px);overflow:auto}
</style>
