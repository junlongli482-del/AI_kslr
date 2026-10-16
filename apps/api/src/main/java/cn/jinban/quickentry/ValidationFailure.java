package cn.jinban.quickentry;

import com.fasterxml.jackson.databind.JsonNode;

public class ValidationFailure extends RuntimeException {
    final JsonNode issues;
    ValidationFailure(JsonNode issues){super("存在需要修复的内容，请查看检查结果");this.issues=issues;}
}
