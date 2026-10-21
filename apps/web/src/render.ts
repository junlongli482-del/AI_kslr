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
  return html
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

function applyImageLayout(html:string, imageLayout:Record<string,any>) {  return html.replace(/<img src="([^"]+)"([^>]*)>/g,(_all,src,attrs)=>{
    const meta=imageLayout[src.replaceAll('&amp;','&')]
    const raw=Number(meta?.manual_width_pct??meta?.render_width_pct??meta?.width_pct)
    const width=Number.isFinite(raw)&&raw>0?Math.min(100,raw):60
    const caption=Array.isArray(meta?.caption)?meta.caption.join(' '):meta?.caption||''
    const safe=md.utils.escapeHtml(caption)
    return `<span data-type="layout-image" class="image-figure" style="width:${width}%;" data-width-pct="${width}"><img src="${src}"${attrs} data-caption="${safe}" data-width-pct="${width}" style="width:100%;height:auto;"/>${safe?`<span class="image-caption">${safe}</span>`:''}</span>`
  })
}

export function renderMarkdown(source:string, imageLayout:Record<string,any>={}) {
  return DOMPurify.sanitize(applyImageLayout(renderWithMath(isolateImages(source),false),imageLayout),{
    ADD_TAGS:['annotation','semantics'],ADD_ATTR:['encoding','xmlns','data-width-pct','data-caption','data-type']
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
  function splitImages(node:any){
    if(!node||typeof node!=='object')return
    if(Array.isArray(node.content)){
      node.content=node.content.flatMap((child:any)=>{
        if(child?.type==='paragraph'&&Array.isArray(child.content)){
          const hasImage=child.content.some((part:any)=>part?.type==='image')
          const hasOther=child.content.some((part:any)=>part?.type!=='image')
          if(hasImage&&hasOther){
            const groups:any[][]=[]
            let current:any[]=[],currentImage:boolean|null=null
            const blank=(part:any)=>part?.type==='text'&&!String(part.text||'').trim()&&!part.marks?.length
            for(const part of child.content){
              const image=part?.type==='image'
              if(current.length&&currentImage===true&&blank(part)){
                current.push(part);continue
              }
              if(current.length&&currentImage!==image){groups.push(current);current=[]}
              current.push(part);currentImage=image
            }
            if(current.length)groups.push(current)
            return groups.map(group=>({...child,content:group}))
          }
        }
        splitImages(child)
        return [child]
      })
    }
  }
  splitImages(clone)
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
      const caption=Array.isArray(meta.caption)?meta.caption.join(' '):meta.caption||''
      ;(clone.content??=[]).push({type:'paragraph',content:[{type:'image',attrs:{src:match[1],alt:'题目插图',widthPct:width??null,manualSize:meta.manual_width_pct!=null,caption}}]})
      urls.add(match[1])
    }
  }
  return clone
}
