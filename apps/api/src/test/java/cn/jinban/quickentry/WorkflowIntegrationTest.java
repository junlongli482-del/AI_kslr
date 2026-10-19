package cn.jinban.quickentry;

import com.fasterxml.jackson.databind.*;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

/** Real PostgreSQL; only the external AI validation boundary is isolated. */
@SpringBootTest(properties="quick-entry.sync-enabled=false")
@Transactional
class WorkflowIntegrationTest {
    static final ObjectMapper JSON=new ObjectMapper();
    static final HttpServer AI;
    static {
        try {
            AI=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            AI.createContext("/tasks",exchange->{
                var input=JSON.readTree(exchange.getRequestBody());
                byte[] body=JSON.writeValueAsBytes(Map.of("valid",true,"issues",List.of(),"result",input));
                exchange.getResponseHeaders().add("Content-Type","application/json");exchange.sendResponseHeaders(200,body.length);
                exchange.getResponseBody().write(body);exchange.close();
            });AI.start();
        }catch(Exception e){throw new ExceptionInInitializerError(e);}
    }
    @DynamicPropertySource static void config(DynamicPropertyRegistry r){r.add("quick-entry.ai-url",()->"http://127.0.0.1:"+AI.getAddress().getPort());}
    @AfterAll static void close(){AI.stop(0);}
    @Autowired TaskService service;
    @Autowired StoreMapper store;
    String fixture(String mode)throws Exception{
        String id=UUID.randomUUID().toString();store.createTask(id,"Integration fixture",mode,false,"low_first");
        var root=JSON.createObjectNode();root.put("task_id",id);root.put("schema_version","quick-entry-v1");
        root.set("documents",JSON.createArrayNode());
        var p=root.putArray("papers").addObject();p.put("id","p1");p.put("title","Test paper");
        var q=root.putArray("questions").addObject();q.put("id","q1");q.put("paper_id","p1");q.put("number","1");q.put("stem","Question");q.put("answer","");q.put("review_status","pending");q.putArray("regions");q.putObject("attributes").put("score",3);
        service.saveReview(id,0,root);return id;
    }
    @Test void questionOnlyCreatesNoPaperAndRepeatCommitIsIdempotent()throws Exception{
        String id=fixture("questions");var first=service.commit(id,1);var second=service.commit(id,1);
        assertEquals(first,second);assertEquals(0,first.get("papers"));
        assertEquals(1,store.questions("").stream().filter(q->id.equals(q.get("task_id"))).count());
        assertEquals(0,store.papers().stream().filter(p->id.equals(p.get("task_id"))).count());
    }
    @Test void textbookStoresTemplateButDoesNotClaimScanningIsIntegrated()throws Exception{
        String id=fixture("textbook");service.commit(id,1);var templates=store.templates(id+"-r1-p1");
        assertEquals(1,templates.size());assertEquals("not_integrated",templates.getFirst().get("scan_capability"));
        assertEquals("pending",templates.getFirst().get("review_status"));
    }
    @Test void ordinaryPaperDoesNotCreateScanTemplate()throws Exception{
        String id=fixture("paper");service.commit(id,1);assertTrue(store.templates(id+"-r1-p1").isEmpty());
    }
    @Test void staleDraftCannotOverwriteNewerRevision()throws Exception{
        String id=fixture("paper");var draft=service.review(id);
        assertThrows(ResponseStatusException.class,()->service.saveReview(id,0,draft));
        assertEquals(1,((Number)store.task(id).get("revision")).intValue());
    }
    @Test void commitRequiresCurrentSavedRevision()throws Exception{
        String id=fixture("paper");assertThrows(ResponseStatusException.class,()->service.commit(id,0));
        assertTrue(store.papers().stream().noneMatch(p->id.equals(p.get("task_id"))));
    }
}
