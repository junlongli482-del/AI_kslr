-- 教辅分组：不限层级，任务归入文件夹；仅空目录可删除（接口层校验）
CREATE TABLE IF NOT EXISTS jinban.qe_folder (
    id          varchar(64) PRIMARY KEY,
    parent_id   varchar(64) REFERENCES jinban.qe_folder(id),
    name        varchar(200) NOT NULL,
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE jinban.qe_task ADD COLUMN IF NOT EXISTS folder_id varchar(64) REFERENCES jinban.qe_folder(id);

CREATE INDEX IF NOT EXISTS idx_qe_folder_parent ON jinban.qe_folder(parent_id);
CREATE INDEX IF NOT EXISTS idx_qe_task_folder ON jinban.qe_task(folder_id);
