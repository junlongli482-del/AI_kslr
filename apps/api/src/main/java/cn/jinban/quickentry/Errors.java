package cn.jinban.quickentry;

import java.util.Map;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class Errors {
    @ExceptionHandler(ValidationFailure.class)
    ResponseEntity<?> validation(ValidationFailure e){return ResponseEntity.unprocessableEntity().body(Map.of("message",e.getMessage(),"code","VALIDATION_FAILED","issues",e.issues));}
    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<?> status(ResponseStatusException e){return ResponseEntity.status(e.getStatusCode()).body(Map.of("message",e.getReason()==null?"请求失败":e.getReason(),"code",e.getStatusCode().value()));}
    @ExceptionHandler(org.springframework.web.client.ResourceAccessException.class)
    ResponseEntity<?> connection(org.springframework.web.client.ResourceAccessException e){
        return ResponseEntity.status(503).body(Map.of("message","无法连接AI处理服务，可能未启动、正在重启或请求超时。请查看Python服务窗口后重试。","code","AI_SERVICE_UNAVAILABLE"));
    }
    @ExceptionHandler(org.springframework.web.client.RestClientResponseException.class)
    ResponseEntity<?> downstream(org.springframework.web.client.RestClientResponseException e){
        String detail=e.getResponseBodyAsString().replaceAll("sk-[A-Za-z0-9_-]+","[已隐藏密钥]");
        detail=detail.substring(0,Math.min(detail.length(),1500));
        return ResponseEntity.status(502).body(Map.of("message","AI处理服务返回 HTTP "+e.getStatusCode().value()+"："+detail,"code","AI_SERVICE_ERROR"));
    }
    @ExceptionHandler(Exception.class)
    ResponseEntity<?> other(Exception e){org.slf4j.LoggerFactory.getLogger(Errors.class).error("Local operation failed: {}",e.getClass().getSimpleName(),e);return ResponseEntity.status(500).body(Map.of("message","操作未完成，请检查服务状态或重试","code","INTERNAL_ERROR","type",e.getClass().getSimpleName()));}
}
