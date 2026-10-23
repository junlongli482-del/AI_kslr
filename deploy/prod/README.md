# 生产试用地（Docker + Nginx + cpolar）

开发环境保持 `scripts\dev.cmd`，本目录是独立生产栈，数据与开发完全隔离。

## 组成

| 服务 | 说明 | 端口 |
|---|---|---|
| nginx | 前端静态文件 + `/api` 反代 + Basic Auth | 宿主机 **2001** |
| api | Java jar（profile=prod，库 quickentry_prod） | 内网 2002 |
| ai | Python 识别服务，数据在卷 proddata | 内网 2003 |
| db | 独立 postgres:16，卷 pgdata | 内网 5432 |

本地 MinerU 不放进容器：AI 通过 `host.docker.internal:8020` 使用宿主机常驻服务。

## 首次启动

```bat
cd /d "C:\Workspace\projects\deepseekharness\快速录入和智能批阅工作区\P1-v1-交接-03343c3\AI_kslr-v1"
docker compose --env-file deploy\prod\.env.prod -f deploy\prod\docker-compose.yml up -d --build
```

访问 `http://127.0.0.1:2001`，浏览器会弹登录框（账号见 `.env.prod`）。

## cpolar

隧道类型 HTTP，本地地址填 `2001`，使用你的固定二级域名即可。不要额外映射 2002/2003/5432。

## 更新

```bat
git pull
docker compose --env-file deploy\prod\.env.prod -f deploy\prod\docker-compose.yml up -d --build
```

Flyway 会在 api 启动时自动迁移生产库。

## 备份

```bat
docker exec quick-entry-prod-db-1 pg_dump -U quickentry quickentry_prod > backup.sql
docker run --rm -v quick-entry-prod_proddata:/data -v %cd%:/out alpine tar czf /out/proddata.tgz -C /data .
```

## 停止 / 清理

```bat
docker compose --env-file deploy\prod\.env.prod -f deploy\prod\docker-compose.yml down
docker compose --env-file deploy\prod\.env.prod -f deploy\prod\docker-compose.yml down -v   # 连数据卷一起删
```

## 注意

- 只保留一个本地 MinerU 实例（并发 2），不要再为生产另起一个；
- 生产 AI 并发建议 2，避免和开发抢 GPU；
- `.env.prod` 含密码，已在 `.gitignore` 中排除，不要提交；
- 首次构建会拉取 Maven/Node/Python 依赖，耗时较长。
