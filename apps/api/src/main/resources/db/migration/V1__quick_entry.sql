CREATE TABLE jinban.qe_task (
 id varchar(64) PRIMARY KEY,
 title text NOT NULL,
 mode varchar(24) NOT NULL CHECK (mode IN ('textbook','questions','paper')),
 generate_answers boolean NOT NULL DEFAULT false,
 channel_policy varchar(24) NOT NULL DEFAULT 'low_first',
 status varchar(24) NOT NULL DEFAULT 'uploaded',
 stage text NOT NULL DEFAULT '待上传',
 message text NOT NULL DEFAULT '',
 review jsonb,
 revision integer NOT NULL DEFAULT 0,
 committed_revision integer,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE jinban.qe_file (
 id varchar(64) PRIMARY KEY,
 task_id varchar(64) NOT NULL REFERENCES jinban.qe_task(id),
 name text NOT NULL,
 role varchar(16) NOT NULL CHECK (role IN ('question','answer','mixed')),
 storage_key text NOT NULL,
 sha256 varchar(64) NOT NULL,
 size bigint NOT NULL,
 sort_order integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE jinban.question_revision (
 id varchar(128) PRIMARY KEY,
 logical_id varchar(128) NOT NULL,
 task_id varchar(64) NOT NULL REFERENCES jinban.qe_task(id),
 review_revision integer NOT NULL,
 source_question_id varchar(128) NOT NULL,
 number text NOT NULL,
 stem text NOT NULL,
 content jsonb NOT NULL,
 content_hash varchar(64) NOT NULL,
 status varchar(24) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (task_id, review_revision, source_question_id)
);
CREATE INDEX question_content_hash ON jinban.question_revision(content_hash);
CREATE INDEX question_content_search ON jinban.question_revision USING gin(content);
CREATE TABLE jinban.paper_revision (
 id varchar(128) PRIMARY KEY,
 task_id varchar(64) NOT NULL REFERENCES jinban.qe_task(id),
 review_revision integer NOT NULL,
 title text NOT NULL,
 mode varchar(24) NOT NULL,
 content jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE jinban.paper_question (
 paper_id varchar(128) NOT NULL REFERENCES jinban.paper_revision(id),
 question_id varchar(128) NOT NULL REFERENCES jinban.question_revision(id),
 sort_order integer NOT NULL,
 score numeric,
 PRIMARY KEY(paper_id, question_id)
);
CREATE TABLE jinban.source_template (
 id varchar(128) PRIMARY KEY,
 paper_id varchar(128) NOT NULL REFERENCES jinban.paper_revision(id),
 content jsonb NOT NULL,
 review_status varchar(24) NOT NULL DEFAULT 'pending',
 scan_capability varchar(24) NOT NULL DEFAULT 'not_integrated'
);
CREATE TABLE jinban.qe_stage_event (
 id bigserial PRIMARY KEY,
 task_id varchar(64) NOT NULL REFERENCES jinban.qe_task(id),
 stage text NOT NULL,
 status text NOT NULL,
 message text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
