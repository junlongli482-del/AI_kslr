import type {Question,Document} from './types'
import {normalizeMathSource,prepareEditorDocument} from './render'

// Use existing block ownership to recover omitted pictures; do not invent an image.
export function repairQuestionDraft(q:Question, documents:Document[]) {
  const before=JSON.stringify(q)
  q.image_layout??={}
  for(const key of ['stem','answer','analysis'] as const)q[key]=normalizeMathSource(q[key])
  q.options.forEach(o=>o.content=normalizeMathSource(o.content))
  q.subquestions.forEach(s=>s.stem=normalizeMathSource(s.stem))
  // Geometry and asset correction are centralized in the processing service.
  // Never derive display size from editable grading regions here.
  q.editor_documents??={}
  const fields:[string,string][]=[['stem',q.stem],['answer',q.answer],['analysis',q.analysis],
    ...q.options.map((o,i)=>[`option-${i}`,o.content] as [string,string]),
    ...q.subquestions.map((s,i)=>[`sub-${i}`,s.stem] as [string,string])]
  for(const [field,source] of fields){
    if(q.editor_documents[field])q.editor_documents[field]=prepareEditorDocument(q.editor_documents[field],source,q.image_layout)
  }
  return JSON.stringify(q)!==before
}
