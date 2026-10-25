package cn.jinban.quickentry;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;
import static org.springframework.http.HttpStatus.*;

@Service
public class TaskService {
    final StoreMapper store;
    final ObjectMapper json;
    final Path data;
    final RestClient ai;
    @Value("${quick-entry.sync-enabled:true}") boolean syncEnabled;

    public TaskService(StoreMapper store,ObjectMapper json,@Value("${quick-entry.data-dir}")String data,
                       @Value("${quick-entry.ai-url}")String aiUrl) {
        this.store=store;this.json=json;this.data=Path.of(data).toAbsolutePath().normalize();
        var factory=new SimpleClientHttpRequestFactory();factory.setConnectTimeout(Duration.ofSeconds(10));factory.setReadTimeout(Duration.ofSeconds(60));
        ai=RestClient.builder().baseUrl(aiUrl).requestFactory(factory).build();
    }
    JsonNode parse(Object s) {
        if(s==null)return json.nullNode();
        try{return json.readTree(s.toString());}catch(Exception e){throw new IllegalStateException("已保存数据无法解析",e);}
    }
    String encode(Object o){try{return json.writeValueAsString(o);}catch(Exception e){throw new IllegalArgumentException("数据无法编码");}}
    static String assetKey(String url){
        if(url==null||url.isBlank())return "";
        int at=url.indexOf("key=");
        if(at<0)return url;
        String key=url.substring(at+4);
        int amp=key.indexOf('&');if(amp>=0)key=key.substring(0,amp);
        return java.net.URLDecoder.decode(key,StandardCharsets.UTF_8);
    }
    static void addAsset(ArrayNode assets,Set<String> seen,String key){
        if(key==null||key.isBlank()||!seen.add(key))return;
        var asset=assets.addObject();asset.put("key",key);
        asset.put("url","/api/assets?key="+URLEncoder.encode(key,StandardCharsets.UTF_8));
    }
    public Path dataRoot(){return data;}
    RestClient aiClient(){return ai;}
    public Map<String,Object> require(String id){var t=store.task(id);if(t==null)throw new ResponseStatusException(NOT_FOUND,"任务不存在");return t;}
    Map<String,Object> cost(String id){

        var out=new HashMap<String,Object>(); out.put("currency","CNY"); out.put("mineru_amount",0.0); out.put("mineru_status","free_service");
        double total=0; int calls=0, cacheHits=0, unknown=0, estimated=0; var items=new ArrayList<Object>();
        var p=data.resolve("tasks").resolve(id).resolve("llm").resolve("calls.json");
        try{
            if(Files.isRegularFile(p)) for(JsonNode c:json.readTree(Files.readString(p))){
                calls++; if("cache_hit".equals(c.path("status").asText())) cacheHits++;
                var n=c.path("cost");
                String status=n.path("amount_status").asText("unknown");
                if(!"cache_hit".equals(c.path("status").asText()) && (!n.isObject()||n.path("amount").isNull()||"unknown".equals(status)))unknown++;
                if("estimated".equals(status))estimated++;
                if(n.isObject()){double amount=n.path("amount").asDouble(0); total+=amount; var item=n.deepCopy();if(item.isObject()){var o=(com.fasterxml.jackson.databind.node.ObjectNode)item;o.put("channel",c.path("channel").asText());o.put("operation",c.path("name").asText());o.put("call_id",c.path("call_id").asText());o.put("at",c.path("at").asText());o.put("status",c.path("status").asText());o.put("seconds",c.path("seconds").asDouble());o.put("model",c.path("model").asText());o.put("finish_reason",c.path("finish_reason").asText());o.set("usage",c.path("usage"));}items.add(item);} }
        }catch(Exception ignored){}
        out.put("llm_amount",total); out.put("total",total); out.put("status",unknown>0?"partial_unknown":estimated>0?"estimated":"calculated");out.put("unknown_calls",unknown);out.put("estimated_calls",estimated); out.put("calls",calls); out.put("cache_hits",cacheHits); out.put("items",items); return out;
    }
    public JsonNode costCall(String id,String callId){
        require(id);
        if(callId==null||!callId.matches("[A-Za-z0-9_-]{1,80}"))throw new ResponseStatusException(BAD_REQUEST,"调用ID无效");
        Path p=data.resolve("tasks").resolve(id).resolve("llm").resolve("calls").resolve(callId+".json");
        if(!Files.isRegularFile(p))throw new ResponseStatusException(NOT_FOUND,"该调用没有明细");
        try{return json.readTree(Files.readString(p));}catch(Exception e){throw new ResponseStatusException(INTERNAL_SERVER_ERROR,"调用明细无法读取",e);}
    }
    public Map<String,Object> task(String id){var t=require(id);t.remove("review");t.put("files",store.files(id));t.put("events",store.events(id));t.put("cost",cost(id));
        var state=data.resolve("tasks").resolve(id).resolve("state.json");
        try{if(Files.isRegularFile(state)){var saved=json.readTree(Files.readString(state));
            if(saved.has("error"))t.put("error",saved.get("error"));
            else if("failed".equals(saved.path("status").asText())){
                var detail=json.createObjectNode();detail.put("stage","原记录未保存失败阶段");detail.put("detail",saved.path("message").asText());
                detail.put("hint","已完成阶段可复用；ReadTimeout表示渠道响应超时，HTTP 524表示供应商网关等待上游超时。");
                var attempts=detail.putArray("attempts");var calls=data.resolve("tasks").resolve(id).resolve("llm/calls.json");
                if(Files.isRegularFile(calls)){
                    var rows=json.readTree(Files.readString(calls));
                    for(int index=Math.max(0,rows.size()-2);index<rows.size();index++){
                        var call=rows.get(index);if(!"failed".equals(call.path("status").asText()))continue;
                        var attempt=attempts.addObject();attempt.put("channel",call.path("channel").asText());attempt.put("operation",call.path("name").asText());
                        if(call.path("error").isObject())attempt.setAll((ObjectNode)call.path("error"));else attempt.put("detail",call.path("error").asText());
                    }
                }
                t.put("error",detail);
            }
        }}catch(Exception ignored){}
        return t;}
    public JsonNode review(String id){var t=require(id);if(t.get("review")==null)throw new ResponseStatusException(CONFLICT,"结果尚未准备好");return parse(t.get("review"));}
    public void restart(String id){
        var t=require(id);
        if("committed".equals(String.valueOf(t.get("status"))))throw new ResponseStatusException(BAD_REQUEST,"已入库的任务不能重跑");
        // 重跑就是重新来过：清掉旧草稿，让新结果成为审核稿，否则界面看到的还是旧内容。
        store.clearReview(id);
        start(id, true);
    }
    public void start(String id){ start(id,false); }
    public void start(String id, boolean refresh){
        var t=require(id);var files=store.files(id);
        if(files.stream().noneMatch(f->!"answer".equals(f.get("role"))))throw new ResponseStatusException(BAD_REQUEST,"请至少上传一个题目文件");
        var payload=new HashMap<String,Object>();payload.put("task_id",id);payload.put("files",files);payload.put("generate",t.get("generate_answers"));payload.put("channel_policy",t.get("channel_policy"));payload.put("refresh",refresh);
        ai.post().uri("/process").body(payload).retrieve().toBodilessEntity();
        store.state(id,"running","等待识别","正在准备文件");
        store.event(id,"等待识别","running","任务已提交");
    }
    private int aiFailures = 0;
    @Scheduled(fixedDelay=2500)
    public void sync(){
        if(!syncEnabled)return;
        try{
            int minutes=30;
            try{minutes=Integer.parseInt(System.getenv().getOrDefault("TASK_TIMEOUT_MINUTES","30"));}catch(NumberFormatException ignored){}
            int stale=store.timeoutStaleTasks(Math.max(5,minutes));
            if(stale>0)aiFailures=0;
        }catch(Exception ignored){}
        for(var t:store.tasks()){
            if(!Set.of("running","queued","pending").contains(t.get("status")))continue;
            String id=t.get("id").toString();
            try{
                JsonNode s=ai.get().uri("/tasks/{id}",id).retrieve().body(JsonNode.class);
                if(s==null)continue;
                aiFailures=0;
                String status=s.path("status").asText(),stage=s.path("stage").asText(),message=s.path("message").asText();
                if(!Set.of("queued","running","ready","failed","interrupted","pending").contains(status))continue;
                if(!stage.equals(t.get("stage"))||!status.equals(t.get("status")))store.event(id,stage,status,message);
                if(status.equals("ready")){
                    var latest=require(id);
                    // A completed rerun is an artifact; never silently replace a human draft.
                    if(latest.get("review")==null){
                        JsonNode result=ai.get().uri("/tasks/{id}/result",id).retrieve().body(JsonNode.class);
                        store.saveReview(id,encode(result),((Number)latest.get("revision")).intValue());
                    }else message="新处理结果已生成；现有人工稿保持不变";
                }
                store.state(id,status,stage,message);
            }catch(Exception ignored){
                // The AI service may be restarting; after a sustained outage mark work
                // interrupted instead of leaving it "running" forever.
                aiFailures++;
                if(aiFailures>=10){
                    for(var row:store.tasks()){
                        String taskId=String.valueOf(row.get("id"));
                        if(!Set.of("running","queued","pending").contains(row.get("status")))continue;
                        store.state(taskId,"interrupted","AI服务无响应","模型服务无响应，可稍后点击恢复处理");
                        store.event(taskId,"AI服务无响应","interrupted","连续探测失败，已标记为可恢复");
                    }
                    aiFailures=0;
                }
            }
        }
    }
    public JsonNode validate(String id,JsonNode draft){
        require(id);
        return ai.post().uri("/tasks/{id}/validate",id).body(draft).retrieve().body(JsonNode.class);
    }
    public JsonNode regionRecognize(String id,JsonNode request){
        require(id);
        return ai.post().uri("/region-recognize").body(request).retrieve().body(JsonNode.class);
    }
    public JsonNode questionRubric(String id,JsonNode request){
        require(id);
        return ai.post().uri("/question-rubric").body(request).retrieve().body(JsonNode.class);
    }
    public JsonNode studentZoneSettings(){
        return ai.get().uri("/settings/student-zones").retrieve().body(JsonNode.class);
    }
    public JsonNode saveStudentZoneSettings(JsonNode request){
        return ai.put().uri("/settings/student-zones").body(request).retrieve().body(JsonNode.class);
    }
    public List<Map<String,Object>> exportPapers(){
        var out=new ArrayList<Map<String,Object>>();
        for(var row:store.exportPapers()){
            JsonNode content=parse(row.get("content"));
            var item=new LinkedHashMap<String,Object>();
            item.put("paper_id",row.get("id"));
            item.put("task_id",row.get("task_id"));
            item.put("title",row.get("title"));
            item.put("mode",row.get("mode"));
            item.put("created_at",row.get("created_at"));
            item.put("attributes",content.path("attributes"));
            item.put("paper_type",content.path("paper_type"));
            item.put("exam",content.path("exam"));
            item.put("computed_total_score",content.path("computed_total_score"));
            item.put("declared_total_score",content.path("declared_total_score"));
            item.put("question_count",store.paperQuestions(String.valueOf(row.get("id"))).size());
            out.add(item);
        }
        return out;
    }
    public JsonNode exportPaper(String id){
        var row=store.paperDetail(id);
        if(row==null)throw new ResponseStatusException(NOT_FOUND,"试卷不存在");
        var task=require(String.valueOf(row.get("task_id")));
        if(!"committed".equals(String.valueOf(task.get("status"))))throw new ResponseStatusException(CONFLICT,"试卷尚未审核入库");
        JsonNode paper=parse(row.get("content"));
        var out=json.createObjectNode();
        var allFolders=store.folders();
        var folderId=task.get("folder_id")==null?null:String.valueOf(task.get("folder_id"));
        var folderPath=new java.util.ArrayList<String>();
        var cursor=folderId;
        while(cursor!=null&&folderPath.size()<20){
            String next=null;boolean found=false;
            for(var f:allFolders)if(cursor.equals(String.valueOf(f.get("id")))){folderPath.add(0,String.valueOf(f.get("name")));next=f.get("parent_id")==null?null:String.valueOf(f.get("parent_id"));found=true;break;}
            cursor=found?next:null;
        }
        out.put("folder_id",folderId==null?"":folderId);
        var folderPathNode=json.createArrayNode();
        folderPath.forEach(folderPathNode::add);
        out.set("folder_path",folderPathNode);
        out.put("schema_version","p1-export-v1");
        out.put("exported_at",java.time.Instant.now().toString());
        out.set("paper",paper);
        var questions=json.createArrayNode();
        for(var qrow:store.exportPaperQuestions(id)){
            var q=json.createObjectNode();
            q.put("id",String.valueOf(qrow.get("id")));
            q.put("sort_order",((Number)qrow.getOrDefault("sort_order",0)).intValue());
            if(qrow.get("score")!=null)q.put("score",((Number)qrow.get("score")).doubleValue());
            q.set("content",parse(qrow.get("content")));
            questions.add(q);
        }
        out.set("questions",questions);
        var templates=store.templates(id);
        if(!templates.isEmpty()){
            var trow=templates.get(0);
            var templateContent=parse(trow.get("content"));
            JsonNode template=templateContent.path("template");
            if(template.isObject() && template.path("student_zones").isArray()){
                var zones=(ArrayNode)template.path("student_zones");
                for(int i=zones.size()-1;i>=0;i--)if("backup".equals(zones.get(i).path("role").asText()))zones.remove(i);
            }
            out.set("template",template);
            var qIndex=new java.util.HashMap<String,JsonNode>();
            for(JsonNode q:questions){qIndex.put(q.path("id").asText(),q);qIndex.put(q.path("content").path("id").asText(),q);}
            if(template.isObject()&&template.path("blanks").isArray()){
                for(JsonNode blank:template.path("blanks")){
                    var node=(com.fasterxml.jackson.databind.node.ObjectNode)blank;
                    var question=qIndex.get(blank.path("question_id").asText());
                    var questionNumber=question==null?"":question.path("number").asText();
                    var subId=blank.path("sub_node_id").asText("");
                    var subNumber="";
                    if(question!=null&&!subId.isEmpty()){
                        for(JsonNode sub:question.path("subquestions")){
                            if(subId.equals(sub.path("subquestion_id").asText()))subNumber=sub.path("number").asText();
                        }
                    }
                    int index=blank.path("index_in_question").asInt(0);
                    // 题组的父题号是区间（如 3-4），括号归属必须落到具体小题的题号；
                    // 解答题的小问号形如 (1)，此时题号仍用父题号。
                    var effectiveNumber=questionNumber;
                    if(!subNumber.isEmpty()&&subNumber.matches("\\d+"))effectiveNumber=subNumber;
                    node.put("question_number",effectiveNumber);
                    node.put("paper_question_number",questionNumber);
                    node.put("subquestion_number",subNumber);
                    node.put("blank_index",index);
                    node.put("blank_label",effectiveNumber.isEmpty()?(""):(index>0?effectiveNumber+"-"+index:effectiveNumber));
                }
            }
            out.set("question_regions",templateContent.path("question_regions"));
            out.set("template_documents",templateContent.path("documents"));
            out.put("template_review_status",String.valueOf(trow.get("review_status")));
            out.put("scan_capability",String.valueOf(trow.get("scan_capability")));
        }else{
            out.set("template",json.createObjectNode());
            out.set("question_regions",json.createArrayNode());
        }
        var assets=json.createArrayNode();
        var seen=new LinkedHashSet<String>();
        for(JsonNode doc:paper.path("documents")){
            for(JsonNode page:doc.path("pages"))addAsset(assets,seen,page.path("image_key").asText(""));
            var metadata=doc.path("asset_metadata");
            var names=metadata.fieldNames();
            while(names.hasNext())addAsset(assets,seen,assetKey(names.next()));
        }
        out.set("assets",assets);
        out.put("task_id",String.valueOf(row.get("task_id")));
        out.put("task_status","committed");
        return out;
    }
    public JsonNode exportQuestion(String id){
        var row=store.exportQuestion(id);
        if(row==null)throw new ResponseStatusException(NOT_FOUND,"题目不存在或所属任务未入库");
        var out=json.createObjectNode();
        out.put("schema_version","p1-export-v1");
        out.put("exported_at",java.time.Instant.now().toString());
        out.put("question_id",String.valueOf(row.get("id")));
        out.put("paper_id",String.valueOf(row.get("paper_id")));
        out.put("task_id",String.valueOf(row.get("task_id")));
        out.put("sort_order",((Number)row.getOrDefault("sort_order",0)).intValue());
        if(row.get("score")!=null)out.put("score",((Number)row.get("score")).doubleValue());
        out.set("content",parse(row.get("content")));
        return out;
    }
    public Map<String,Object> saveReview(String id,int revision,JsonNode draft){
        var previous=require(id);
        try{if(previous.get("review")!=null){Path history=data.resolve("tasks").resolve(id).resolve("review-history");Files.createDirectories(history);Path snapshot=history.resolve("revision-"+revision+".json");if(!Files.exists(snapshot))Files.writeString(snapshot,previous.get("review").toString());}}catch(Exception e){throw new ResponseStatusException(INTERNAL_SERVER_ERROR,"旧审核稿备份失败，未覆盖，请重试");}
        if(!id.equals(draft.path("task_id").asText()))throw new ResponseStatusException(BAD_REQUEST,"审核稿不属于当前任务");
        if(store.saveReview(id,encode(draft),revision)!=1)throw new ResponseStatusException(CONFLICT,"草稿已更新，请刷新后重试");
        return Map.of("revision",revision+1,"saved",true);
    }
    static String digest(String value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}}

    @Transactional
    public Map<String,Object> deleteTask(String id){
        if(id==null||!id.matches("[A-Za-z0-9-]{1,80}"))throw new ResponseStatusException(BAD_REQUEST,"任务ID无效");
        var t=require(id);
        String status=String.valueOf(t.get("status"));
        if("committed".equals(status))throw new ResponseStatusException(CONFLICT,"审核通过的任务不能删除");
        if(Set.of("running","queued","pending").contains(status))throw new ResponseStatusException(CONFLICT,"任务正在处理，请等处理结束后再删除");
        var keys=new ArrayList<String>();
        for(var row:store.files(id))keys.add(String.valueOf(row.get("storage_key")));
        store.deleteEvents(id);
        store.deleteFiles(id);
        store.deletePaperQuestions(id);
        store.deleteTemplates(id);
        store.deletePapers(id);
        store.deleteQuestions(id);
        store.deleteTask(id);
        for(String key:keys)removePath(data.resolve(key));
        removePath(data.resolve("tasks").resolve(id));
        removePath(data.resolve("uploads").resolve(id));
        return Map.of("deleted",true,"id",id);
    }
    void removePath(Path path){
        Path target=path.toAbsolutePath().normalize();
        if(!target.startsWith(data)||target.equals(data))return;
        try{
            if(!Files.exists(target))return;
            try(var walk=Files.walk(target)){
                walk.sorted(Comparator.reverseOrder()).forEach(p->{try{Files.deleteIfExists(p);}catch(Exception ignored){}});
            }
        }catch(Exception ignored){}
    }
    @Transactional
    public Map<String,Object> commit(String id,int revision){
        var t=store.lock(id);if(t==null)throw new ResponseStatusException(NOT_FOUND,"任务不存在");
        if(((Number)t.get("revision")).intValue()!=revision)throw new ResponseStatusException(CONFLICT,"请先保存最新审核稿");
        JsonNode draft=parse(t.get("review"));
        JsonNode checked=validate(id,draft);
        if(!checked.path("valid").asBoolean())throw new ValidationFailure(checked.path("issues"));
        draft=checked.path("result");
        String prefix=id+"-r"+revision+"-";var questionIds=new HashMap<String,String>();
        for(JsonNode q:draft.path("questions")){
            String source=q.path("id").asText(),qid=prefix+source;
            String answer=q.path("answer").asText();
            boolean answered=!answer.isBlank();
            for(JsonNode sub:q.path("subquestions"))if(!sub.path("answer").path("value").asText("").isBlank())answered=true;
            store.question(qid,id+"-"+source,id,revision,source,q.path("number").asText(),q.path("stem").asText(),encode(q),digest(q.path("stem").asText().replaceAll("\\s+","")),answered?q.path("review_status").asText("pending"):"incomplete");
            questionIds.put(source,qid);
        }
        int papers=0;
        if(!"questions".equals(t.get("mode"))){
            for(JsonNode p:draft.path("papers")){
                String pid=prefix+p.path("id").asText();
                ObjectNode paper=p.deepCopy();paper.set("documents",draft.path("documents"));
                store.paper(pid,id,revision,p.path("title").asText(),t.get("mode").toString(),encode(paper));
                var regions=json.createArrayNode();int order=0;boolean confirmed=true;
                for(JsonNode q:draft.path("questions")){
                    if(!q.path("paper_id").asText().equals(p.path("id").asText()))continue;
                    var score=q.path("attributes").get("score");
                    store.paperQuestion(pid,questionIds.get(q.path("id").asText()),order++,score!=null&&score.isNumber()?score.decimalValue():null);
                    ObjectNode region=json.createObjectNode();region.put("question_id",questionIds.get(q.path("id").asText()));region.set("regions",q.path("regions"));regions.add(region);
                    if(!q.path("review_status").asText().equals("reviewed"))confirmed=false;
                }
                if("textbook".equals(t.get("mode"))){
                    var template=json.createObjectNode();template.set("documents",draft.path("documents"));template.set("question_regions",regions);template.set("template",draft.path("template"));
                    store.template(pid+"-template",pid,encode(template),confirmed?"reviewed":"pending");
                }
                papers++;
            }
        }
        store.committed(id,revision);
        return Map.of("questions",questionIds.size(),"papers",papers,"revision",revision,"idempotency_key",id+":"+revision);
    }
}
