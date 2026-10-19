package cn.jinban.quickentry;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;

class TaskSyncTest {
    @Test void queuedTaskContinuesToReadyAndFailedTaskBecomesVisible()throws Exception{
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/tasks",exchange->{
            String path=exchange.getRequestURI().getPath();
            String response=path.endsWith("/result")?"{\"questions\":[]}":path.contains("failed")?
                "{\"status\":\"failed\",\"stage\":\"处理失败\",\"message\":\"HTTP 524 upstream timeout\"}":
                "{\"status\":\"ready\",\"stage\":\"待审核\",\"message\":\"done\"}";
            byte[] body=response.getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type","application/json");exchange.sendResponseHeaders(200,body.length);
            exchange.getResponseBody().write(body);exchange.close();
        });server.start();
        try{
            var store=mock(StoreMapper.class);
            var ready=new HashMap<String,Object>(Map.of("id","ready","status","queued","stage","等待资源","revision",0));
            var failed=new HashMap<String,Object>(Map.of("id","failed","status","queued","stage","等待资源","revision",0));
            when(store.tasks()).thenReturn(List.of(ready,failed));when(store.task("ready")).thenReturn(ready);
            var service=new TaskService(store,new ObjectMapper(),"../../data","http://127.0.0.1:"+server.getAddress().getPort());
            service.syncEnabled=true;service.sync();
            verify(store).state("ready","ready","待审核","done");
            verify(store).saveReview(eq("ready"),anyString(),eq(0));
            verify(store).state("failed","failed","处理失败","HTTP 524 upstream timeout");
        }finally{server.stop(0);}
    }
}
