package cn.jinban.quickentry;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** 教辅分组：不限层级；仅空目录可删除。 */
@RestController
public class FolderController {
    private final JdbcTemplate jdbc;

    public FolderController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/folders")
    public List<Map<String, Object>> folders() {
        return jdbc.queryForList("SELECT id,parent_id,name,sort_order FROM jinban.qe_folder ORDER BY sort_order,name");
    }

    @PostMapping("/folders")
    public Map<String, Object> create(@RequestBody Map<String, Object> body) {
        String parent = body.get("parent_id") == null ? null : String.valueOf(body.get("parent_id"));
        String name = String.valueOf(body.getOrDefault("name", "")).trim();
        if (name.isEmpty()) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "名称不能为空");
        if (parent != null && !parent.isEmpty()) {
            Integer exists = jdbc.queryForObject("SELECT count(*) FROM jinban.qe_folder WHERE id=?", Integer.class, parent);
            if (exists == null || exists == 0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "父目录不存在");
        } else {
            parent = null;
        }
        String id = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO jinban.qe_folder(id,parent_id,name) VALUES(?,?,?)", id, parent, name);
        return Map.of("id", id, "parent_id", parent == null ? "" : parent, "name", name);
    }

    @PutMapping("/folders/{id}")
    public Map<String, Object> update(@PathVariable String id, @RequestBody Map<String, Object> body) {
        Map<String, Object> row = jdbc.queryForMap("SELECT id,parent_id,name FROM jinban.qe_folder WHERE id=?", id);
        String name = body.containsKey("name") ? String.valueOf(body.get("name")).trim() : String.valueOf(row.get("name"));
        String parent = body.containsKey("parent_id")
                ? (body.get("parent_id") == null || String.valueOf(body.get("parent_id")).isEmpty() ? null : String.valueOf(body.get("parent_id")))
                : (row.get("parent_id") == null ? null : String.valueOf(row.get("parent_id")));
        if (name.isEmpty()) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "名称不能为空");
        if (parent != null) {
            if (parent.equals(id)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "不能移到自己下面");
            List<Map<String, Object>> all = jdbc.queryForList("SELECT id,parent_id FROM jinban.qe_folder");
            String cursor = parent;
            while (cursor != null) {
                if (cursor.equals(id)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "不能移到自己的子目录下");
                String next = null;
                for (Map<String, Object> item : all) {
                    if (cursor.equals(String.valueOf(item.get("id")))) {
                        next = item.get("parent_id") == null ? null : String.valueOf(item.get("parent_id"));
                        break;
                    }
                }
                cursor = next;
            }
        }
        jdbc.update("UPDATE jinban.qe_folder SET name=?,parent_id=? WHERE id=?", name, parent, id);
        return Map.of("id", id, "parent_id", parent == null ? "" : parent, "name", name);
    }

    @DeleteMapping("/folders/{id}")
    public Map<String, Object> delete(@PathVariable String id) {
        Integer children = jdbc.queryForObject("SELECT count(*) FROM jinban.qe_folder WHERE parent_id=?", Integer.class, id);
        Integer tasks = jdbc.queryForObject("SELECT count(*) FROM jinban.qe_task WHERE folder_id=?", Integer.class, id);
        if ((children != null && children > 0) || (tasks != null && tasks > 0)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "目录非空，请先移走子目录或任务");
        }
        jdbc.update("DELETE FROM jinban.qe_folder WHERE id=?", id);
        return Map.of("deleted", id);
    }

    @PutMapping("/quick-entry/tasks/{id}/folder")
    public Map<String, Object> moveTask(@PathVariable String id, @RequestBody Map<String, Object> body) {
        String folder = body.get("folder_id") == null ? null : String.valueOf(body.get("folder_id"));
        if (folder != null && folder.isEmpty()) folder = null;
        jdbc.update("UPDATE jinban.qe_task SET folder_id=? WHERE id=?", folder, id);
        return Map.of("id", id, "folder_id", folder == null ? "" : folder);
    }
}
