"""Grounded asset references and a page-column layout independent of grading crops."""
import copy
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse, quote

URL = re.compile(r'/api/assets\?key=[^\s)"<>]+')
IMAGE = re.compile(r'!\[([^\]]*)\]\((/api/assets\?key=[^)]+)\)')
VERSION = 'source-layout-v2'


def key_of(url):
    return parse_qs(urlparse(url).query).get('key', [''])[0]


def canonical(key):
    return '/api/assets?key=' + quote(key, safe='')


def one_edit(a, b):
    if abs(len(a)-len(b)) > 1 or min(len(a),len(b)) < 24: return False
    if len(a)==len(b): return sum(x!=y for x,y in zip(a,b))==1
    short,long=(a,b) if len(a)<len(b) else (b,a)
    return any(long[:i]+long[i+1:]==short for i in range(len(long)))


def _page_geometry(doc, page_index):
    pages = doc.get('pages') or []
    page = pages[page_index] if page_index < len(pages) else {}
    wide = page.get('width_px', 1) > page.get('height_px', 1) * 1.15
    blocks = [b for b in doc.get('blocks', []) if b.get('page_index') == page_index and len(b.get('bbox', [])) == 4]
    return wide, blocks


def _cluster_centers(values, count, iterations=12):
    values = sorted(values)
    if not values or count <= 1:
        return [values[len(values)//2]] if values else []
    count = min(count, len(values))
    centers = [values[min(len(values)-1, int((i+.5)*len(values)/count))] for i in range(count)]
    for _ in range(iterations):
        groups = [[] for _ in centers]
        for value in values:
            groups[min(range(len(centers)), key=lambda i: abs(value - centers[i]))].append(value)
        updated = [sum(g)/len(g) if g else centers[i] for i, g in enumerate(groups)]
        if all(abs(a-b) < 1e-4 for a, b in zip(updated, centers)):
            break
        centers = updated
    return sorted(centers)


def _infer_column_count(blocks, bins=2000):
    """Count columns from vertical whitespace gutters, not from centre-point gaps."""
    usable = [b for b in blocks if b['bbox'][2]-b['bbox'][0] <= .55 and b['bbox'][3]-b['bbox'][1] < .6]
    if not usable:
        return 1
    cover = [0] * bins
    for b in usable:
        for i in range(max(0, int(b['bbox'][0]*bins)), min(bins, int(b['bbox'][2]*bins))):
            cover[i] = 1
    gutters, start = 0, None
    for i, value in enumerate(cover):
        if value == 0 and start is None:
            start = i
        elif value == 1 and start is not None:
            if .08 <= (start + i) / 2 / bins <= .92 and (i - start) / bins >= .015:
                gutters += 1
            start = None
    return min(4, max(1, gutters + 1))


def detected_columns(doc, page_index):
    """Gutter-based column count for one page (used as a cross-check for model output)."""
    blocks = [b for b in doc.get('blocks', []) if b.get('page_index') == page_index and len(b.get('bbox', [])) == 4]
    return _infer_column_count(blocks)


def page_cells(doc, page_index):
    """Structural column cells for a page: equal split with a small gutter (supports 1/2/3/4 栏)."""
    wide, blocks = _page_geometry(doc, page_index)
    if not wide:
        return [{'x0': .04, 'x1': .96}]
    declared = None
    columns = doc.get('columns')
    if isinstance(columns, list) and page_index < len(columns):
        try:
            declared = int(columns[page_index]) if columns[page_index] else None
        except (TypeError, ValueError):
            declared = None
    usable = [b for b in blocks if b['bbox'][2]-b['bbox'][0] >= .06 and b['bbox'][3] > .03 and b['bbox'][1] < .97]
    count = declared if declared and 1 <= declared <= 4 else (_infer_column_count(usable) if usable else 0)
    if not count or count <= 0:
        count = 2
    if count <= 1:
        return [{'x0': .04, 'x1': .96}]
    left, right, gap = .04, .96, .02
    span = (right - left - gap * (count - 1)) / count
    return [{'x0': left + i * (span + gap), 'x1': left + i * (span + gap) + span} for i in range(count)]


def column_index(doc, page_index, bbox):
    cells = page_cells(doc, page_index)
    center = (bbox[0] + bbox[2]) / 2
    return min(range(len(cells)), key=lambda i: abs(center - (cells[i]['x0'] + cells[i]['x1']) / 2))


def column_bounds(doc, page_index, bbox):
    cells = page_cells(doc, page_index)
    index = column_index(doc, page_index, bbox)
    cell = cells[index]
    candidates = []
    for b in doc.get('blocks', []):
        a = b.get('bbox', [])
        if b.get('page_index') != page_index or len(a) != 4 or a[2] - a[0] < .18:
            continue
        if column_index(doc, page_index, a) != index:
            continue
        if a[1] < .035 or a[3] > .98:
            continue
        candidates.append(a)
    if candidates:
        left = min(b[0] for b in candidates)
        right = max(b[2] for b in candidates)
        return [max(cell['x0'], left), min(cell['x1'], right)]
    return [cell['x0'], cell['x1']]


def repair_assets(question, documents, data, task_id):
    """Only unique task-owned, existing source assets can correct a fabricated URL."""
    root=Path(data).resolve(); folder=root/'tasks'/task_id
    source={u:m for d in documents for u,m in d.get('asset_metadata',{}).items()}
    candidates={}
    for u in source:
        key=key_of(u);p=(root/key).resolve()
        if p.is_relative_to(folder.resolve()) and p.is_file():candidates[key]=canonical(key)
    if folder.exists():
        for group in ['crops','manual-images','recovered']:
            for p in (folder/group).glob('*'):
                if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
                    key=p.relative_to(root).as_posix();candidates[key]=canonical(key)
    replacements={};removed=set();audit=[]
    raw=json.dumps({k:question.get(k) for k in ('stem','answer','analysis','options','subquestions','editor_documents')},ensure_ascii=False)
    excluded={key_of(u) for u in question.get('excluded_image_urls',[])}
    for u in set(URL.findall(raw)):
        key=key_of(u);p=(root/key).resolve()
        if p.is_relative_to(root) and p.is_file():continue
        name=Path(key).name
        matches=[k for k in candidates if Path(k).name==name]
        if not matches:
            matches=[k for k in candidates if Path(k).suffix==Path(name).suffix and one_edit(Path(k).stem,Path(name).stem)]
        if len(matches)!=1:continue
        target=matches[0]
        if target in excluded:removed.add(u)
        else:replacements[u]=candidates[target]
        audit.append({'from':u,'to':candidates[target],'action':'remove_excluded' if target in excluded else 'repair'})
    def text(s):
        for old in removed:s=re.sub(r'!\[[^\]]*\]\('+re.escape(old)+r'\)', '',s)
        for old,new in replacements.items():s=s.replace(old,new)
        # Remove a duplicate fallback picture, retain the first in-place reference.
        seen=set()
        def picture(m):
            key=key_of(m[2])
            if key in seen:return ''
            seen.add(key);return m[0]
        return IMAGE.sub(picture,s)
    for field in ['stem','answer','analysis']:question[field]=text(question.get(field) or '')
    for item in question.get('options',[]):item['content']=text(item.get('content',''))
    for item in question.get('subquestions',[]):
        item['stem']=text(item.get('stem',''))
        answer=item.get('answer')
        if isinstance(answer,dict):
            for key in ('value','analysis','scoring_criteria'):
                if answer.get(key):answer[key]=text(answer.get(key))
    editor_seen=set()
    targets=set(replacements.values())
    def visit(node):
        if not isinstance(node,dict):return node
        if node.get('type')=='image':
            u=node.get('attrs',{}).get('src','')
            if u in removed:return None
            if u in replacements:node['attrs']['src']=replacements[u]
            src=node.get('attrs',{}).get('src','')
            if src in targets and src in editor_seen:return None
            editor_seen.add(src)
        if isinstance(node.get('content'),list):
            content=[];seen=set()
            for child in node['content']:
                child=visit(child)
                if child is None:continue
                content.append(child)
            node['content']=content
        return node
    for node in question.get('editor_documents',{}).values():
        editor_seen.clear();visit(node)
    if audit:
        question.setdefault('asset_repairs',[]).extend(audit)
        question.setdefault('issues',[]).append(f'已依据本任务真实资产修正{len(audit)}处图片引用，请核对')
    return audit


def apply_layout(question, documents):
    # Structured tables are authoritative; remove their original table images,
    # including when the model omitted asset_key and only left a block reference.
    sources = set()
    docs = {d['id']: d for d in documents}
    for table in question.get('tables', []) or []:
        if table.get('structure_status') != 'structured':
            continue
        for key in ('url', 'image_url', 'asset_url', 'source_image_url'):
            if table.get(key):
                sources.add(table[key])
        if table.get('asset_key'):
            sources.add(canonical(table['asset_key']))
        block_id = table.get('block_id') or table.get('source_block_id')
        if block_id:
            for doc in documents:
                block = next((b for b in doc.get('blocks', []) if b.get('id') == block_id), None)
                if not block:
                    continue
                for url, meta in doc.get('asset_metadata', {}).items():
                    bbox, mbox = block.get('bbox'), meta.get('bbox')
                    if (meta.get('page_index') == block.get('page_index') and bbox and mbox and len(bbox) == 4 == len(mbox)
                            and all(abs(a - b) < .012 for a, b in zip(bbox, mbox))):
                        sources.add(url)
    source_keys = {canonical(key_of(url)) for url in sources if key_of(url)}

    def clean(text):
        text = str(text or '')
        for url in sources:
            text = re.sub(r'!\[[^\]]*\]\(' + re.escape(url) + r'\)', '', text)
        return text

    if sources:
        for field in ('stem', 'answer', 'analysis'):
            question[field] = clean(question.get(field))
        for item in question.get('options', []):
            item['content'] = clean(item.get('content'))
        for sub in question.get('subquestions', []):
            sub['stem'] = clean(sub.get('stem'))
            answer = sub.get('answer')
            if isinstance(answer, dict):
                for field in ('value', 'analysis', 'scoring_criteria'):
                    if answer.get(field):
                        answer[field] = clean(answer[field])
        def strip_images(node):
            if not isinstance(node, dict):
                return node
            if node.get('type') == 'image':
                src = str((node.get('attrs') or {}).get('src') or '')
                if src in sources or (key_of(src) and canonical(key_of(src)) in source_keys):
                    return None
            if isinstance(node.get('content'), list):
                node['content'] = [child for child in (strip_images(child) for child in node['content']) if child is not None]
            return node
        for document in question.get('editor_documents', {}).values():
            strip_images(document)

    metadata={u:{**m,'document_id':d['id']} for d in documents for u,m in d.get('asset_metadata',{}).items()}
    docs={d['id']:d for d in documents}
    layout=question.setdefault('image_layout',{})
    used=set(URL.findall(json.dumps({k:question.get(k) for k in ('stem','answer','analysis','options','subquestions','editor_documents')},ensure_ascii=False)))
    # Region crops also have source geometry, but are not source geometry containers.
    for r in question.get('regions',[]):
        if r.get('crop_url'):metadata[r['crop_url']]={'bbox':r['bbox'],'document_id':r['document_id'],'page_index':r['page_index']}
    for u,m in metadata.items():
        if u not in used:continue
        if not m.get('bbox') or m.get('document_id') not in docs:continue
        old=layout.get(u,{})
        b=m['bbox'];bounds=column_bounds(docs[m['document_id']],m.get('page_index',0),b)
        pct=100*(b[2]-b[0])/max(bounds[1]-bounds[0],.01)
        layout[u]={**m,**{k:v for k,v in old.items() if k in ('manual_width_pct','caption','group_id','row','column')},
                   'render_width_pct':round(min(100,max(2,pct)),3),
                   'reference_width':bounds[1]-bounds[0], 'layout_version':VERSION,'layout_source':'original_column',
                   'caption':old.get('caption',m.get('caption',[]))}
    # Preserve caption ownership in the document, remove only standalone source captions.
    for field in ['stem','answer','analysis']:
        s=question.get(field,'')
        def caption(m):
            meta=layout.get(m[2],{});c=meta.get('caption',[])
            c=' '.join(str(x) for x in c if x) if isinstance(c,list) else str(c or '')
            return f'![{c}]({m[2]})' if c and not m[1] else m[0]
        s=IMAGE.sub(caption,s)
        for u,m in layout.items():
            c=m.get('caption',[]);c=' '.join(str(x) for x in c if x) if isinstance(c,list) else str(c or '')
            if c and u in s:s=re.sub(r'(?m)^\s*'+re.escape(c)+r'\s*$', '',s)
        # Adjacent figure groups retain row order. Text in between remains untouched.
        matches=list(IMAGE.finditer(s))
        for a,b in reversed(list(zip(matches,matches[1:]))):
            x,y=layout.get(a[2],{}),layout.get(b[2],{})
            if s[a.end():b.start()].strip():continue
            if x.get('document_id')==y.get('document_id') and x.get('page_index')==y.get('page_index') and x.get('bbox') and y.get('bbox') and abs(x['bbox'][1]-y['bbox'][1])<.04:
                s=s[:a.end()]+' '+s[b.start():]
        question[field]=s
    refs=[]
    for o in question.get('options',[]):
        matches=IMAGE.findall(o.get('content',''));refs.append(layout.get(matches[0][1],{}) if matches else {})
    if refs and all(x.get('bbox') for x in refs):
        rows=[]
        for m in refs:
            row=next((r for r in rows if abs(r[0]-m['bbox'][1])<.045),None)
            if row is None:rows.append([m['bbox'][1],1])
            else:row[1]+=1
        cols=max(r[1] for r in rows)
        question['options_layout']={'columns':cols,'source':'original_rows','version':VERSION}
    else:cols=question.get('options_layout',{}).get('columns',1) or 1
    converted=set()
    for o in question.get('options',[]):
        for _,u in IMAGE.findall(o.get('content','')):
            if u in layout and u not in converted:
                if layout[u].get('render_width_pct') is not None:layout[u]['render_width_pct']=min(100,layout[u]['render_width_pct']*cols)
                converted.add(u)
    def editor(node):
        if not isinstance(node,dict):return
        if node.get('type')=='image':
            attrs=node.setdefault('attrs',{});m=layout.get(attrs.get('src'),{})
            if m.get('manual_width_pct'):
                attrs['widthPct']=m['manual_width_pct'];attrs['manualSize']=True
            if not attrs.get('manualSize') and m.get('render_width_pct'):
                attrs['widthPct']=m['render_width_pct'];attrs['layoutVersion']=VERSION
            c=m.get('caption',[])
            if c:attrs['caption']=' '.join(str(x) for x in c if x) if isinstance(c,list) else c
        for child in node.get('content',[]):editor(child)
    for doc in question.get('editor_documents',{}).values():editor(doc)


def repair_result(result, data, task_id):
    for q in result.get('questions',[]):
        repair_assets(q,result.get('documents',[]),data,task_id)
        apply_layout(q,result.get('documents',[]))
    return result
