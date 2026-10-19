package cn.jinban.quickentry;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
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
                if(n.isObject()){double amount=n.path("amount").asDouble(0); total+=amount; var item=n.deepCopy();if(item.isObject()){((com.fasterxml.jackson.databind.node.ObjectNode)item).put("channel",c.path("channel").asText());((com.fasterxml.jackson.databind.node.ObjectNode)item).put("operation",c.path("name").asText());}items.add(item);} }
        }catch(Exception ignored){}
        out.put("llm_amount",total); out.put("total",total); out.put("status",unknown>0?"partial_unknown":estimated>0?"estimated":"calculated");out.put("unknown_calls",unknown);out.put("estimated_calls",estimated); out.put("calls",calls); out.put("cache_hits",cacheHits); out.put("items",items); return out;
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
    public void start(String id){
        var t=require(id);var files=store.files(id);
        if(files.stream().noneMatch(f->!"answer".equals(f.get("role"))))throw new ResponseStatusException(BAD_REQUEST,"请至少上传一个题目文件");
        var payload=new HashMap<String,Object>();payload.put("task_id",id);payload.put("files",files);payload.put("generate",t.get("generate_answers"));payload.put("channel_policy",t.get("channel_policy"));
        ai.post().uri("/process").body(payload).retrieve().toBodilessEntity();
        store.state(id,"running","等待识别","正在准备文件");
        store.event(id,"等待识别","running","任务已提交");
    }
    @Scheduled(fixedDelay=2500)
    public void sync(){
        if(!syncEnabled)return;
        for(var t:store.tasks()){
            if(!Set.of("running","queued","pending").contains(t.get("status")))continue;
            String id=t.get("id").toString();
            try{
                JsonNode s=ai.get().uri("/tasks/{id}",id).retrieve().body(JsonNode.class);
                if(s==null)continue;
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
            }catch(Exception ignored){/* Keep durable state; next sync retries without resubmitting OCR. */}
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
    public Map<String,Object> saveReview(String id,int revision,JsonNode draft){
        var previous=require(id);
        try{if(previous.get("review")!=null){Path history=data.resolve("tasks").resolve(id).resolve("review-history");Files.createDirectories(history);Path snapshot=history.resolve("revision-"+revision+".json");if(!Files.exists(snapshot))Files.writeString(snapshot,previous.get("review").toString());}}catch(Exception e){throw new ResponseStatusException(INTERNAL_SERVER_ERROR,"旧审核稿备份失败，未覆盖，请重试");}
        if(!id.equals(draft.path("task_id").asText()))throw new ResponseStatusException(BAD_REQUEST,"审核稿不属于当前任务");
        if(store.saveReview(id,encode(draft),revision)!=1)throw new ResponseStatusException(CONFLICT,"草稿已更新，请刷新后重试");
        return Map.of("revision",revision+1,"saved",true);
    }
    static String digest(String value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}}

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
            store.question(qid,id+"-"+source,id,revision,source,q.path("number").asText(),q.path("stem").asText(),encode(q),digest(q.path("stem").asText().replaceAll("\\s+","")),answer.isBlank()?"incomplete":q.path("review_status").asText("pending"));
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
                    var template=json.createObjectNode();template.set("documents",draft.path("documents"));template.set("question_regions",regions);
                    store.template(pid+"-template",pid,encode(template),confirmed?"reviewed":"pending");
                }
                papers++;
            }
        }
        store.committed(id,revision);
        return Map.of("questions",questionIds.size(),"papers",papers,"revision",revision,"idempotency_key",id+":"+revision);
    }
}
