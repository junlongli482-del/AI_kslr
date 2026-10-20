package cn.jinban.quickentry;

import java.util.*;
import org.apache.ibatis.annotations.*;

@Mapper
public interface StoreMapper {
    @Select("SELECT id,title,mode,generate_answers,channel_policy,status,stage,message,revision,committed_revision,created_at::text,updated_at::text FROM jinban.qe_task ORDER BY created_at DESC")
    List<Map<String,Object>> tasks();
    @Select("SELECT id,title,mode,generate_answers,channel_policy,status,stage,message,revision,committed_revision,review::text,created_at::text,updated_at::text FROM jinban.qe_task WHERE id=#{id}")
    Map<String,Object> task(String id);
    @Insert("INSERT INTO jinban.qe_task(id,title,mode,generate_answers,channel_policy) VALUES(#{id},#{title},#{mode},#{generate},#{policy})")
    void createTask(@Param("id") String id,@Param("title") String title,@Param("mode") String mode,@Param("generate") boolean generate,@Param("policy") String policy);
    @Select("SELECT id,name,role,storage_key,sha256,size,sort_order FROM jinban.qe_file WHERE task_id=#{id} ORDER BY sort_order,created_at")
    List<Map<String,Object>> files(String id);
    @Insert("INSERT INTO jinban.qe_file(id,task_id,name,role,storage_key,sha256,size,sort_order) VALUES(#{id},#{taskId},#{name},#{role},#{key},#{hash},#{size},#{order})")
    void addFile(@Param("id")String id,@Param("taskId")String taskId,@Param("name")String name,@Param("role")String role,@Param("key")String key,@Param("hash")String hash,@Param("size")long size,@Param("order")int order);
    @Update("UPDATE jinban.qe_task SET status=#{status},stage=#{stage},message=#{message},updated_at=now() WHERE id=#{id}")
    void state(@Param("id")String id,@Param("status")String status,@Param("stage")String stage,@Param("message")String message);
    @Update("UPDATE jinban.qe_task SET review=CAST(#{json} AS jsonb),revision=revision+1,updated_at=now() WHERE id=#{id} AND revision=#{revision}")
    int saveReview(@Param("id")String id,@Param("json")String json,@Param("revision")int revision);
    @Select("SELECT id,title,mode,revision,review::text FROM jinban.qe_task WHERE id=#{id} FOR UPDATE")
    Map<String,Object> lock(String id);
    @Update("UPDATE jinban.qe_task SET committed_revision=#{revision},status='committed',stage='已入库',message='审核结果已保存至资源库',updated_at=now() WHERE id=#{id}")
    void committed(@Param("id")String id,@Param("revision")int revision);
    @Insert("INSERT INTO jinban.qe_stage_event(task_id,stage,status,message) VALUES(#{id},#{stage},#{status},#{message})")
    void event(@Param("id")String id,@Param("stage")String stage,@Param("status")String status,@Param("message")String message);
    @Select("SELECT stage,status,message,created_at::text FROM jinban.qe_stage_event WHERE task_id=#{id} ORDER BY id")
    List<Map<String,Object>> events(String id);
    @Insert("INSERT INTO jinban.question_revision(id,logical_id,task_id,review_revision,source_question_id,number,stem,content,content_hash,status) VALUES(#{id},#{logical},#{task},#{revision},#{source},#{number},#{stem},CAST(#{json} AS jsonb),#{hash},#{status}) ON CONFLICT DO NOTHING")
    void question(@Param("id")String id,@Param("logical")String logical,@Param("task")String task,@Param("revision")int revision,@Param("source")String source,@Param("number")String number,@Param("stem")String stem,@Param("json")String json,@Param("hash")String hash,@Param("status")String status);
    @Insert("INSERT INTO jinban.paper_revision(id,task_id,review_revision,title,mode,content) VALUES(#{id},#{task},#{revision},#{title},#{mode},CAST(#{json} AS jsonb)) ON CONFLICT DO NOTHING")
    void paper(@Param("id")String id,@Param("task")String task,@Param("revision")int revision,@Param("title")String title,@Param("mode")String mode,@Param("json")String json);
    @Insert("INSERT INTO jinban.paper_question(paper_id,question_id,sort_order,score) VALUES(#{paper},#{question},#{order},#{score}) ON CONFLICT DO NOTHING")
    void paperQuestion(@Param("paper")String paper,@Param("question")String question,@Param("order")int order,@Param("score")java.math.BigDecimal score);
    @Insert("INSERT INTO jinban.source_template(id,paper_id,content,review_status) VALUES(#{id},#{paper},CAST(#{json} AS jsonb),#{status}) ON CONFLICT DO NOTHING")
    void template(@Param("id")String id,@Param("paper")String paper,@Param("json")String json,@Param("status")String status);
    @Select("SELECT id,number,stem,status,content::text,created_at::text,task_id FROM jinban.question_revision q WHERE review_revision=(SELECT max(v.review_revision) FROM jinban.question_revision v WHERE v.logical_id=q.logical_id) AND (#{query}='' OR stem ILIKE '%'||#{query}||'%') ORDER BY created_at DESC LIMIT 200")
    List<Map<String,Object>> questions(@Param("query")String query);
    @Select("SELECT id,title,mode,content::text,task_id,created_at::text FROM jinban.paper_revision p WHERE review_revision=(SELECT max(v.review_revision) FROM jinban.paper_revision v WHERE v.task_id=p.task_id AND v.content->>'id'=p.content->>'id') ORDER BY created_at DESC LIMIT 200")
    List<Map<String,Object>> papers();
    @Select("SELECT p.id,p.title,p.mode,p.task_id,p.content::text,p.created_at::text FROM jinban.paper_revision p JOIN jinban.qe_task t ON t.id=p.task_id WHERE t.status='committed' AND p.review_revision=(SELECT max(v.review_revision) FROM jinban.paper_revision v WHERE v.task_id=p.task_id AND v.content->>'id'=p.content->>'id') ORDER BY p.created_at DESC LIMIT 200")
    List<Map<String,Object>> exportPapers();
    @Select("SELECT q.id,q.content::text,pq.sort_order,pq.score FROM jinban.paper_question pq JOIN jinban.question_revision q ON q.id=pq.question_id WHERE pq.paper_id=#{id} ORDER BY pq.sort_order")
    List<Map<String,Object>> exportPaperQuestions(String id);
    @Select("SELECT q.id,q.content::text,q.task_id,pq.paper_id,pq.sort_order,pq.score FROM jinban.question_revision q JOIN jinban.paper_question pq ON pq.question_id=q.id JOIN jinban.qe_task t ON t.id=q.task_id WHERE q.id=#{id} AND t.status='committed' LIMIT 1")
    Map<String,Object> exportQuestion(String id);
    @Select("SELECT id,number,stem,status,content::text,task_id FROM jinban.question_revision WHERE id=#{id}")
    Map<String,Object> questionDetail(String id);
    @Select("SELECT id,title,mode,content::text,task_id FROM jinban.paper_revision WHERE id=#{id}")
    Map<String,Object> paperDetail(String id);
    @Select("SELECT q.id,q.content::text FROM jinban.paper_question pq JOIN jinban.question_revision q ON q.id=pq.question_id WHERE pq.paper_id=#{id} ORDER BY pq.sort_order")
    List<Map<String,Object>> paperQuestions(String id);
    @Select("SELECT id,content::text,review_status,scan_capability FROM jinban.source_template WHERE paper_id=#{id}")
    List<Map<String,Object>> templates(String id);
}
