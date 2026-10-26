import MarkdownIt from 'markdown-it'
import katex from 'katex'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({ html: true, breaks: true })
const formulaPattern = () => /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)/g

export function normalizeMathSource(source:string) {
  // Convert before Markdown consumes the backslashes of \( and \[.
  return mathParts(source||'').map(part=>part.latex!==undefined
    ?(part.display?`$$${part.latex}$$`:`$${part.latex}$`)
    :repairLegacyMath(part.text||'')).join('')
}

function repairLegacyMath(text:string){
  return text.replace(/\(([^()\n]*\\[a-zA-Z]+[^()\n]*)\)/g,(_all,latex)=>`$${latex}$`)
    .replace(/\[\s*\n([^\]]*\\[a-zA-Z]+[^\]]*)\n\s*\]/g,(_all,latex)=>`$$${latex}$$`)
}

export function mathParts(source:string) {
  const parts:{text?:string;latex?:string;display?:boolean}[]=[]
  let start=0
  for(const match of source.matchAll(formulaPattern())){
    if(match.index!>start)parts.push({text:source.slice(start,match.index)})
    parts.push({latex:match[1]??match[2]??match[3]??match[4],display:match[1]!==undefined||match[3]!==undefined})
    start=match.index!+match[0].length
  }
  if(start<source.length)parts.push({text:source.slice(start)})
  return parts
}

const math = (latex:string, displayMode=false) => {
  try { return katex.renderToString(latex, { throwOnError: false, displayMode, trust:false, strict:false }) }
  catch { return `<code>${md.utils.escapeHtml(latex)}</code>` }
}

function renderWithMath(source:string, editable:boolean) {
  const formulas:string[]=[]
  const text=normalizeMathSource(source).replace(formulaPattern(),(_all,a,b,c,d)=>{
    const latex=a??b??c??d,display=a!==undefined||c!==undefined,id=formulas.length
    formulas.push(editable
      ?`<span data-type="math-inline" data-latex="${md.utils.escapeHtml(latex)}" data-display="${display}">${md.utils.escapeHtml(latex)}</span>`
      :math(latex,display))
    return `QEFORMULA${id}PLACEHOLDER`
  })
  let html=md.render(text)
  formulas.forEach((formula,index)=>{html=html.replace(`QEFORMULA${index}PLACEHOLDER`,()=>formula)})
  return blanks(html, editable)
}

function blanks(html:string, editable:boolean){
  return html.replace(/\{\{blank(?::(\d{1,3}))?\}\}/g,(_all,index)=>{
    // The rich editor drops unknown inline spans, so editable content keeps literal
    // underscores; the read-only preview uses a styled blank line instead.
    if(editable) return `${index?`${index}. `:''}____`
    const label=index?`<span class="cloze-index">${index}.</span> `:''
    return `<span class="cloze-blank">${label}<span class="cloze-line"></span></span>`
  })
}

function isolateImages(source:string){
  const imagePattern=/!\[[^\]]*\]\([^)]+\)/g
  return source.split('\n').map(line=>{
    if(!imagePattern.test(line))return line
    imagePattern.lastIndex=0
    const images=[...line.matchAll(imagePattern)]
    if(!images.length)return line
    let output='',cursor=0,pending=''
    const flush=()=>{if(pending){output+=pending;pending=''}}
    for(const match of images){
      const before=line.slice(cursor,match.index!)
      if(before.trim()){
        flush()
        output+=before.trimEnd()+'\n\n'
      }else if(pending&&before.length){pending+=' '}
      pending+=match[0]
      cursor=match.index!+match[0].length
    }
    const after=line.slice(cursor)
    if(after.trim()){
      if(pending){output+=pending+'\n\n';pending=''}
      output+=after.trimStart()
    }else flush()
    if(pending)output+=pending
    return output.trim()
  }).join('\n')
}

function captionText(meta:any){
  const list=Array.isArray(meta?.caption)?meta.caption:[meta?.caption]
  return list.map((item:any)=>typeof item==='string'?item:(item?.content||item?.text||'')).filter(Boolean).join(' ')
}

function applyImageLayout(html:string, imageLayout:Record<string,any>) {  return html.replace(/<img src="([^"]+)"([^>]*)>/g,(_all,src,attrs)=>{
    const meta=imageLayout[src.replaceAll('&amp;','&')]
    const raw=Number(meta?.manual_width_pct??meta?.render_width_pct??meta?.width_pct)
    const width=Number.isFinite(raw)&&raw>0?Math.min(100,raw):60
    const caption=captionText(meta)
    const safe=md.utils.escapeHtml(caption)
    return `<span data-type="layout-image" class="image-figure" style="width:${width}%;" data-width-pct="${width}"><img src="${src}"${attrs} data-caption="${safe}" data-width-pct="${width}" style="width:100%;height:auto;"/>${safe?`<span class="image-caption">${safe}</span>`:''}</span>`
  })
}

export function renderMarkdown(source:string, imageLayout:Record<string,any>={}) {
  return DOMPurify.sanitize(applyImageLayout(renderWithMath(isolateImages(source),false),imageLayout),{
    ADD_TAGS:['annotation','semantics'],ADD_ATTR:['encoding','xmlns','data-width-pct','data-caption','data-type']
  })
}

/** 粘贴进来的公式常被剥掉反斜杠（\mathrm → mathrm），只在 $...$ 内做保守修复。 */
export function repairPastedLatex(text: string): string {
  if (!text || !text.includes('$')) return text
  return text.replace(/\$([^$]+)\$/g, (_match, body: string) => {
    const fixed = body.replace(/(^|[^\\])\b(mathrm|mathbf|mathit|frac|dfrac|sqrt|times|cdot|leq|geq|neq|approx|left|right|text|sum|int|lim|log|ln|sin|cos|tan|Delta|alpha|beta|theta|pi|infty|rightarrow)\b/g,
      (_m, prefix: string, command: string) => `${prefix}\\${command}`)
    return `$${fixed}$`
  })
}

export function markdownToEditable(source:string, imageLayout:Record<string,any>={}) {
  return DOMPurify.sanitize(applyImageLayout(renderWithMath(isolateImages(source),true),imageLayout),{
    ADD_ATTR:['data-type','data-latex','data-display','data-width-pct','data-caption','data-type']
  })
}

export function prepareEditorDocument(document:any,source:string,imageLayout:Record<string,any>={}) {
  if(!document)return markdownToEditable(source,imageLayout)
  // A saved document without math nodes must not hide LaTeX that is present in
  // the current markdown (older fields were plain textareas).
  if(/\$[^$\n]+\$|\\\(|\\\[/.test(source||'')&&!JSON.stringify(document).includes('mathInline'))
    return markdownToEditable(source,imageLayout)
  const clone=JSON.parse(JSON.stringify(document))
  const paragraphText=(node:any):string|null=>node.type==='paragraph'&&(node.content||[]).every((child:any)=>
    (child.type==='text'&&!child.marks?.length)||child.type==='hardBreak')
    ?(node.content||[]).map((child:any)=>child.type==='hardBreak'?'\n':child.text||'').join(''):null
  // Old saved display formulas can occupy three separate paragraphs: [, LaTeX, ].
  if(clone.type==='doc'&&clone.content){
    const blocks=[]
    for(let i=0;i<clone.content.length;i++){
      const first=paragraphText(clone.content[i])
      if(first?.trim()==='['||first?.trim()==='\\['){
        const body:string[]=[];let end=i+1
        for(;end<clone.content.length;end++){
          const text=paragraphText(clone.content[end]);if(text===null)break
          if(text.trim()===']'||text.trim()==='\\]')break
          body.push(text)
        }
        const last=end<clone.content.length?paragraphText(clone.content[end])?.trim():null
        if((last===']'||last==='\\]')&&/\\[A-Za-z]+/.test(body.join('\n'))){
          blocks.push({type:'paragraph',content:[{type:'mathInline',attrs:{latex:body.join('\n'),display:true}}]});i=end;continue
        }
      }
      blocks.push(clone.content[i])
    }
    clone.content=blocks
  }
  function regroupImages(node:any,layout:Record<string,any>){
    if(!node||typeof node!=='object')return
    if(!Array.isArray(node.content))return
    const imageKey=(part:any)=>{
      const meta=layout[part?.attrs?.src]||{}
      if(meta.group_id)return `g:${meta.group_id}`
      if(meta.row!=null)return `r:${meta.document_id||''}:${meta.page_index??0}:${meta.row}`
      const bbox=meta.bbox
      if(Array.isArray(bbox)&&bbox.length===4)return `y:${meta.document_id||''}:${meta.page_index??0}:${Math.round(Number(bbox[1])/.04)}`
      return null
    }
    const isBlank=(part:any)=>part?.type==='text'&&!String(part.text||'').trim()&&!part.marks?.length
    const arrange=(paragraph:any)=>{
      const blocks:any[]=[];let text:any[]=[],group:any[]|null=null,key:any=null
      const flushText=()=>{if(text.length){blocks.push({...paragraph,content:text});text=[]}}
      const flushGroup=()=>{if(group){blocks.push({...paragraph,content:group});group=null;key=null}}
      for(const part of paragraph.content||[]){
        if(part?.type==='image'){
          const nextKey=imageKey(part)
          if(group&&nextKey===key){group.push(part);continue}
          if(group&&nextKey===null&&key===null){group.push(part);continue}
          flushText();flushGroup()
          group=[part];key=nextKey
          continue
        }
        if(group&&isBlank(part)){group.push(part);continue}
        flushGroup();text.push(part)
      }
      flushText();flushGroup()
      return blocks
    }
    node.content=node.content.flatMap((child:any)=>{
      if(child?.type==='paragraph'&&Array.isArray(child.content)&&child.content.some((part:any)=>part?.type==='image'))return arrange(child)
      regroupImages(child,layout)
      return [child]
    })
  }
  regroupImages(clone,imageLayout)
  function visit(node:any):any[] {
    const text=paragraphText(node)
    if(text!==null&&text&&node.content?.length>1&&mathParts(normalizeMathSource(text)).some(part=>part.latex!==undefined)){
      node.content=[{type:'text',text}]
    }
    if(node.type==='text'&&!node.marks?.some((mark:any)=>mark.type==='code')){
      // Old Markdown parsing may already have consumed delimiter backslashes.
      const text=normalizeMathSource(node.text||'')
      return mathParts(text).map(part=>part.latex!==undefined
        ?{type:'mathInline',attrs:{latex:part.latex,display:part.display}}
        :{...node,text:part.text})
    }
    if(node.type==='image'){
      const meta=imageLayout[node.attrs?.src]||{}
      const width=Number(meta.manual_width_pct??meta.render_width_pct??meta.width_pct)
      if(!node.attrs?.manualSize&&Number.isFinite(width)&&width>0)node.attrs={...node.attrs,widthPct:Math.min(100,width)}
      if(meta.caption?.length)node.attrs={...node.attrs,caption:Array.isArray(meta.caption)?meta.caption.join(' '):meta.caption}
    }
    if(node.content&&node.type!=='codeBlock')node.content=node.content.flatMap(visit)
    return [node]
  }
  visit(clone)
  const urls=new Set<string>()
  function collect(node:any){if(node.type==='image')urls.add(node.attrs.src);node.content?.forEach(collect)}
  collect(clone)
  for(const match of source.matchAll(/!\[[^\]]*\]\((\/api\/assets\?key=[^)]+)\)/g)){
    if(!urls.has(match[1])){
      const meta=imageLayout[match[1]]||{}
      const width=meta.manual_width_pct??meta.render_width_pct??meta.width_pct
      const caption=captionText(meta)
      ;(clone.content??=[]).push({type:'paragraph',content:[{type:'image',attrs:{src:match[1],alt:'题目插图',widthPct:width??null,manualSize:meta.manual_width_pct!=null,caption}}]})
      urls.add(match[1])
    }
  }
  return clone
}
