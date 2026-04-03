# 后台 Go 文件编译方法

## 1. 背景说明

WeKnora 项目使用 Go 语言开发，后端服务运行在 Docker 容器中。由于容器内源码目录是只读挂载，无法在容器内直接编译代码。本文档介绍如何在宿主机上编译后台 Go 文件并使容器使用新编译的二进制文件。

## 2. 容器目录结构

**app服务（WeKnora-app）挂载情况：**

| 本地路径 | 容器路径 | 权限 | 用途 |
|----------|----------|------|------|
| `./` | `/app_src` | 只读`:ro` | 后端源码挂载 |
| `./scripts` | `/app/scripts` | 只读`:ro` | 脚本目录 |
| `./volumes/data_files` | `/data/files` | 可写 | 数据文件存储 |
| `./volumes/docreader-tmp` | `/tmp/docreader` | 只读`:ro` | docreader临时文件 |
| `./config/config.yaml` | `/app/config/config.yaml` | 可写 | 配置文件 |
| `./config/prompt_templates` | `/app/config/prompt_templates` | 只读`:ro` | 提示模板 |
| `./config/builtin_agents.yaml` | `/app/config/builtin_agents.yaml` | 只读`:ro` | 内置代理配置 |
| `./volumes/go-build-cache` | `/root/.cache/go-build` | 可写 | Go编译缓存 |
| `./volumes/pip-cache` | `/root/.cache/pip` | 可写 | pip缓存 |
| `./volumes/uv-cache` | `/root/.cache/uv` | 可写 | uv缓存 |
| `./volumes/duckdb` | `/home/appuser/.duckdb` | 可写 | DuckDB数据 |
| 无映射 | `/app` | 无 | 运行时目录（来自镜像，包含二进制文件WeKnora） |

**关键点：**
- **/app_src**：源码挂载，**只读**，修改后重启恢复原状
- **/app**：二进制文件所在目录，**无本地映射**，无法持久化修改
- 其他缓存和数据目录有本地映射，可持久化

## 3. 问题分析

在容器内编译后端代码需要解决三个问题：

| 序号 | 问题 | 当前状态 | 需要改为 |
|------|------|----------|----------|
| 1 | 代码可编辑 | `/app_src` 只读挂载 (`:ro`) | 改为可写挂载 |
| 2 | 二进制持久化 | `/app` 无本地映射 | 映射到宿主机目录 |
| 3 | 编译依赖 | 容器缺少 sqlite3 开发库 | 在容器内安装依赖 |

## 4. 解决方案：临时容器编译跳板法

### 4.1 核心思想

在独立于主容器的临时环境中编译代码，编译成功后二进制文件直接写入主容器挂载的本地目录。

**关键价值**：当编译出错导致二进制文件不可用时，主容器仍然正常运行，可以继续修复代码、重新编译、反复尝试，而不会陷入"编译失败→容器起不来→无法修复代码"的死循环。

### 4.2 步骤1：修改 docker-compose.yml

```yaml
# app 服务添加两个挂载
volumes:
  # 1. 源码改为可写
  - ./:/app_src:rw
  # 2. 二进制目录映射到本地（持久化编译结果）
  - ./volumes/app:/app
```

**注意**：
- `./volumes/app` 目录需要提前创建
- 修改 docker-compose.yml 后需要重启容器使配置生效

### 4.3 步骤2：创建编译跳板容器

```bash
# 创建临时容器（保留，作为编译跳板）
docker run -d --name WeKnora-app-temp \
  --network weknora_WeKnora-network \
  -v E:/mycode/weknora:/app_src:rw \
  -v E:/mycode/weknora/volumes/app:/app \
  golang:1.24-bookworm sleep 3600
```

**说明**：
- `--network weknora_WeKnora-network`：与主容器在同一网络，确保编译结果能直接写入 `/app` 目录
- `golang:1.24-bookworm`：使用 Go 1.24 镜像，与项目要求的版本一致
- `sleep 3600`：让容器持续运行3600秒（1小时），避免容器退出

### 4.4 步骤3：安装编译依赖

```bash
# 首次使用需要安装编译依赖（只需执行一次）
docker exec WeKnora-app-temp bash -c 'apt-get update && apt-get install -y libsqlite3-dev'
```

**说明**：
- 项目依赖 `go-sqlite3`（SQLite数据库的Go语言绑定），使用cgo调用C库
- 需要安装 SQLite 开发库才能编译成功

### 4.5 步骤4：编译 Go 代码

```bash
# 编译 Go 代码
docker exec WeKnora-app-temp bash -c 'cd /app_src/cmd/server && go build -o /app/WeKnora .'
```

**说明**：
- 编译结果直接写入 `/app/WeKnora`（映射到宿主机 `volumes/app`）
- 无需单独拷贝步骤

### 4.6 步骤5：重启主容器生效

```bash
# 编译完成后重启主容器
docker restart WeKnora-app
```

## 5. Protobuf 冲突解决

### 5.1 问题现象

编译成功后启动容器时出现以下错误：

```
proto: file "common.proto" is already registered
```

### 5.2 原因分析

项目使用 gRPC 和 Protocol Buffers，在重复导入或编译时可能发生 proto 文件注册冲突。

### 5.3 解决方案

在 docker-compose.yml 的 app 服务中添加环境变量：

```yaml
environment:
  - GOLANG_PROTOBUF_REGISTRATION_CONFLICT=warn
```

**说明**：
- `GOLANG_PROTOBUF_REGISTRATION_CONFLICT=warn`：将冲突错误降级为警告，允许程序继续运行
- 此环境变量应添加到 app 服务的 environment 配置中

## 6. 跳板容器维护

| 操作 | 命令 |
|------|------|
| **保留跳板容器** | 跳板容器稳定运行时应保留，避免每次重新下载依赖 |
| **删除并重建** | 仅在容器异常或需要重置时执行：`docker rm -f WeKnora-app-temp` 后重新创建 |
| **验证源码** | `docker exec WeKnora-app-temp sed -n '310,320p' /app_src/internal/handler/initialization.go` |
| **验证编译结果** | `grep -c "Before saving to database" /app/WeKnora` |
| **清理缓存** | `docker exec WeKnora-app-temp bash -c 'cd /app_src && go clean -cache'` |

## 7. 完整操作流程

### 首次设置（一次性操作）

```bash
# 1. 创建 volumes/app 目录
mkdir -p volumes/app

# 2. 修改 docker-compose.yml（添加挂载）

# 3. 重启主容器
docker-compose down && docker-compose up -d

# 4. 创建编译跳板容器
docker run -d --name WeKnora-app-temp \
  --network weknora_WeKnora-network \
  -v E:/mycode/weknora:/app_src:rw \
  -v E:/mycode/weknora/volumes/app:/app \
  golang:1.24-bookworm sleep 3600

# 5. 安装编译依赖
docker exec WeKnora-app-temp bash -c 'apt-get update && apt-get install -y libsqlite3-dev'
```

### 日常编译流程

```bash
# 1. 修改源码（编辑器中修改代码）

# 2. 编译 Go 代码
docker exec WeKnora-app-temp bash -c 'cd /app_src/cmd/server && go build -o /app/WeKnora .'

# 3. 重启主容器
docker restart WeKnora-app

# 4. 验证修改是否生效
```

## 8. 关键经验总结

| 经验 | 说明 |
|------|------|
| **临时容器做跳板** | 编译失败不影响主容器，可以反复重试 |
| **编译结果持久化** | 二进制文件写入 `/app`（映射到宿主机 `volumes/app`），重启后不丢失 |
| **先验证源码** | 用 `sed -n '310,320p' /app_src/internal/handler/initialization.go` 确认代码存在 |
| **清理缓存** | `go clean -cache` 避免缓存导致编译问题 |
| **LDFLAGS 必须设置** | protobuf 冲突需要添加 `protoregistry.conflictPolicy=warn` |

## 9. 常见问题

### Q1: 编译时报错 "sqlite3.h: No such file or directory"

**原因**：未安装 SQLite 开发库

**解决**：
```bash
docker exec WeKnora-app-temp bash -c 'apt-get update && apt-get install -y libsqlite3-dev'
```

### Q2: 编译成功但运行时没有效果

**原因**：可能是编译缓存问题，或者容器未正确重启

**解决**：
```bash
# 清理缓存
docker exec WeKnora-app-temp bash -c 'cd /app_src && go clean -cache'

# 重新编译
docker exec WeKnora-app-temp bash -c 'cd /app_src/cmd/server && go build -o /app/WeKnora .'

# 重启容器
docker restart WeKnora-app
```

### Q3: 容器启动失败

**原因**：可能是新的二进制文件有问题

**解决**：重新编译或从备份恢复二进制文件
