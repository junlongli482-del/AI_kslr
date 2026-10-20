package cn.jinban.quickentry;

import com.fasterxml.jackson.databind.*;
import java.nio.file.*;
import java.util.*;
import org.springframework.core.io.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import static org.springframework.http.HttpStatus.*;

@RestController
@RequestMapping("/api")
public class QuickEntryController {
    final TaskService service;
    final StoreMapper store;
    public QuickEntryController(TaskService service,StoreMapper store){this.service=service;this.store=store;}
    @GetMapping("/health") public Object health(){return Map.of("status","ok","mode","local-single-operator","database","postgresql");}
    @GetMapping("/quick-entry/tasks") public Object tasks(){return store.tasks().stream().peek(t->t.put("cost",service.cost(t.get("id").toString()))).toList();}
    @PostMapping("/quick-entry/tasks") public Object create(@RequestBody Map<String,Object> body){
        String mode=body.getOrDefault("mode","textbook").toString();
        if(!Set.of("textbook","questions","paper").contains(mode))throw new ResponseStatusException(BAD_REQUEST,"未知录入模式");
        String id=UUID.randomUUID().toString();
        store.createTask(id,body.getOrDefault("title","新录入任务").toString(),mode,Boolean.TRUE.equals(body.get("generate_answers")),body.getOrDefault("channel_policy","deepseek").toString());
        return service.task(id);
    }
    @GetMapping("/quick-entry/tasks/{id}") public Object task(@PathVariable String id){return service.task(id);}
    @GetMapping("/quick-entry/tasks/{id}/comparison") public Object comparison(@PathVariable String id)throws Exception{
        service.require(id);Path p=service.dataRoot().resolve("tasks").resolve(id).resolve("comparison.json");
        return Files.isRegularFile(p)?service.parse(Files.readString(p)):Map.of("candidates",List.of());
    }
    @GetMapping("/quick-entry/tasks/{id}/candidates/{channel}") public Object candidate(@PathVariable String id,@PathVariable String channel)throws Exception{
        service.require(id);if(!Set.of("low","stable","deepseek","claude","gemini","minimax","glm").contains(channel))throw new ResponseStatusException(BAD_REQUEST,"未知候选渠道");
        Path p=service.dataRoot().resolve("tasks").resolve(id).resolve("candidates").resolve(channel).resolve("result.json");
        if(!Files.isRegularFile(p))throw new ResponseStatusException(CONFLICT,"该模型尚未完成");return service.parse(Files.readString(p));
    }
    @GetMapping("/quick-entry/settings/concurrency") public Object concurrency(){
        return service.aiClient().get().uri("/settings/concurrency").retrieve().body(JsonNode.class);
    }
    @PutMapping("/quick-entry/settings/concurrency") public Object concurrency(@RequestBody JsonNode body){
        var count=body.get("max_concurrency");
        if(count==null||!count.isIntegralNumber()||!count.canConvertToInt()||count.asInt()<0)
            throw new ResponseStatusException(BAD_REQUEST,"并发数必须是非负整数，0 表示无本地上限");
        return service.aiClient().put().uri("/settings/concurrency").body(body).retrieve().body(JsonNode.class);
    }
    @PostMapping("/quick-entry/tasks/{id}/images") public Object image(@PathVariable String id,@RequestParam("file")MultipartFile file)throws Exception{
        service.require(id);
        if(file.isEmpty())throw new ResponseStatusException(BAD_REQUEST,"图片为空，请重新选择或截图");
        if(file.getSize()>20*1024*1024)throw new ResponseStatusException(BAD_REQUEST,"单张图片不能超过20MB");
        byte[] bytes=file.getBytes();
        String ext;
        if(bytes.length>=8&&(bytes[0]&255)==137&&bytes[1]==80&&bytes[2]==78&&bytes[3]==71&&bytes[4]==13&&bytes[5]==10&&bytes[6]==26&&bytes[7]==10)ext=".png";
        else if(bytes.length>=3&&(bytes[0]&255)==255&&(bytes[1]&255)==216&&(bytes[2]&255)==255)ext=".jpg";
        else if(bytes.length>=12&&new String(bytes,0,4,java.nio.charset.StandardCharsets.US_ASCII).equals("RIFF")&&new String(bytes,8,4,java.nio.charset.StandardCharsets.US_ASCII).equals("WEBP"))ext=".webp";
        else throw new ResponseStatusException(BAD_REQUEST,"仅支持PNG、JPEG、WebP图片，请重新截图或另存为图片");
        var bitmap=javax.imageio.ImageIO.read(new java.io.ByteArrayInputStream(bytes));
        if(bitmap==null&&!ext.equals(".webp"))throw new ResponseStatusException(BAD_REQUEST,"图片损坏，无法读取");
        String key="tasks/"+id+"/manual-images/"+UUID.randomUUID()+ext;
        Path target=service.dataRoot().resolve(key);Files.createDirectories(target.getParent());Files.write(target,bytes);
        var response=new HashMap<String,Object>();response.put("url","/api/assets?key="+java.net.URLEncoder.encode(key,java.nio.charset.StandardCharsets.UTF_8));
        response.put("name",Optional.ofNullable(file.getOriginalFilename()).orElse("截图"));response.put("size",file.getSize());
        if(bitmap!=null){response.put("width_px",bitmap.getWidth());response.put("height_px",bitmap.getHeight());}
        return response;
    }
    @PostMapping("/quick-entry/tasks/{id}/files") public Object upload(@PathVariable String id,@RequestParam("files")List<MultipartFile> files,@RequestParam(defaultValue="question")String role)throws Exception{
        var task=service.require(id);
        if(!"uploaded".equals(task.get("status")))throw new ResponseStatusException(CONFLICT,"任务启动后不能修改源文件，请创建新任务");
        if(!Set.of("question","answer","mixed").contains(role))throw new ResponseStatusException(BAD_REQUEST,"未知文件用途");
        int order=store.files(id).size();
        for(var f:files){
            String name=Optional.ofNullable(f.getOriginalFilename()).orElse("file");
            String ext=name.contains(".")?name.substring(name.lastIndexOf('.')).toLowerCase(Locale.ROOT):"";
            if(!Set.of(".pdf",".png",".jpg",".jpeg",".doc",".docx").contains(ext))throw new ResponseStatusException(BAD_REQUEST,"仅支持PDF、图片和Word");
            if(f.isEmpty())throw new ResponseStatusException(BAD_REQUEST,"文件为空");
            String fid="d"+UUID.randomUUID().toString().replace("-","").substring(0,16);
            String key="uploads/"+id+"/"+fid+ext;Path target=service.dataRoot().resolve(key);Files.createDirectories(target.getParent());
            f.transferTo(target);
            byte[] content=Files.readAllBytes(target);
            String hash=HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(content));
            store.addFile(fid,id,name,role,key,hash,f.getSize(),order++);
        }
        return store.files(id);
    }
    @GetMapping("/quick-entry/settings/student-zones") public Object studentZoneSettings(){return service.studentZoneSettings();}
    @PutMapping("/quick-entry/settings/student-zones") public Object saveStudentZoneSettings(@RequestBody JsonNode body){return service.saveStudentZoneSettings(body);}
    @PostMapping("/quick-entry/tasks/{id}/start") public Object start(@PathVariable String id){service.start(id);return service.task(id);}
    @PostMapping("/quick-entry/tasks/{id}/retry") public Object retry(@PathVariable String id){service.start(id);return service.task(id);}
    @GetMapping("/quick-entry/tasks/{id}/review") public Object review(@PathVariable String id){return Map.of("result",service.review(id),"revision",service.require(id).get("revision"));}
    @PutMapping("/quick-entry/tasks/{id}/review") public Object save(@PathVariable String id,@RequestBody JsonNode body){return service.saveReview(id,body.path("expected_revision").asInt(-1),body.path("result"));}
    @PostMapping("/quick-entry/tasks/{id}/validate") public Object validate(@PathVariable String id,@RequestBody(required=false)JsonNode body){return service.validate(id,body==null?service.review(id):body);}
    @PostMapping("/quick-entry/tasks/{id}/region-recognize") public Object regionRecognize(@PathVariable String id,@RequestBody JsonNode body){
        var request=body.deepCopy();
        if(!request.isObject())throw new ResponseStatusException(BAD_REQUEST,"区域识别请求必须是JSON对象");
        ((com.fasterxml.jackson.databind.node.ObjectNode)request).put("task_id",id);
        return service.regionRecognize(id,request);
    }
    @PostMapping("/quick-entry/tasks/{id}/question-rubric") public Object questionRubric(@PathVariable String id,@RequestBody JsonNode body){
        var request=body.deepCopy();
        if(!request.isObject())throw new ResponseStatusException(BAD_REQUEST,"评分标准请求必须是JSON对象");
        ((com.fasterxml.jackson.databind.node.ObjectNode)request).put("task_id",id);
        return service.questionRubric(id,request);
    }
    @PostMapping("/quick-entry/tasks/{id}/commit") public Object commit(@PathVariable String id,@RequestBody JsonNode body){return service.commit(id,body.path("revision").asInt(-1));}
    @GetMapping("/assets") public ResponseEntity<Resource> asset(@RequestParam String key)throws Exception{
        Path path=service.dataRoot().resolve(key).normalize();
        if(!path.startsWith(service.dataRoot())||!Files.isRegularFile(path))throw new ResponseStatusException(NOT_FOUND,"文件不存在");
        String ext=path.getFileName().toString().toLowerCase(Locale.ROOT);
        if(!ext.matches(".*\\.(pdf|png|jpg|jpeg|webp)$"))throw new ResponseStatusException(FORBIDDEN,"此资产不可通过浏览器读取");
        String mime=Files.probeContentType(path);return ResponseEntity.ok().header("X-Content-Type-Options","nosniff").contentType(MediaType.parseMediaType(mime==null?"application/octet-stream":mime)).body(new FileSystemResource(path));
    }
    Map<String,Object> decoded(Map<String,Object> row){if(row==null)throw new ResponseStatusException(NOT_FOUND,"资源不存在");row.put("content",service.parse(row.get("content")));return row;}
    @GetMapping("/questionbank/questions") public Object questions(@RequestParam(defaultValue="")String query){return store.questions(query).stream().map(this::decoded).toList();}
    @GetMapping("/questionbank/questions/{id}") public Object question(@PathVariable String id){return decoded(store.questionDetail(id));}
    @GetMapping("/paperbank/papers") public Object papers(){return store.papers().stream().map(this::decoded).toList();}
    @GetMapping("/paperbank/papers/{id}") public Object paper(@PathVariable String id){var p=decoded(store.paperDetail(id));p.put("questions",store.paperQuestions(id).stream().map(this::decoded).toList());p.put("templates",store.templates(id).stream().map(this::decoded).toList());return p;}
    @GetMapping("/catalogs") public Object catalogs(){return Map.of("status","unconfigured","knowledge_points",List.of(),"chapters",List.of());}
}
