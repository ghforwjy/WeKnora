# Docker 运行和代码挂载指南

## 1. 从 GitHub 下载原始代码

### 1.1 克隆代码仓库

```powershell
# 克隆 WeKnora 仓库
git clone https://github.com/WechatOpenAI/WeKnora.git

# 进入项目目录
cd WeKnora
```

### 1.2 初始状态

克隆下来的原始状态：

- `docker-compose.yml` 没有代码挂载配置
- `Dockerfile.app` 的 final stage 没有 Go 编译器
- 无法直接在容器内编译代码

## 2. 配置代码挂载

### 2.1 修改 docker-compose.yml

原始配置（第40-45行）：

```yaml
    volumes:
      - data-files:/data/files
      - docreader-tmp:/tmp/docreader:ro
      - ./config/config.yaml:/app/config/config.yaml
      # Optional: mount custom skills directory (allows adding skills without rebuilding image)
      - ./skills/preloaded:/app/skills/preloaded
```

**修改后**：

```yaml
    volumes:
      - data-files:/data/files
      - docreader-tmp:/tmp/docreader:ro
      - ./config/config.yaml:/app/config/config.yaml
      # Optional: mount custom skills directory (allows adding skills without rebuilding image)
      - ./skills/preloaded:/app/skills/preloaded
      # 代码挂载：将本地整个项目目录挂载到容器内，修改代码后容器内立即可见
      - .:/go/src/github.com/Tencent/WeKnora
```

**说明**：

- `.` 表示当前项目目录（克隆下来就有的，包含 internal/, cmd/ 等）
- 挂载后容器内 `/go/src/github.com/Tencent/WeKnora` 直接指向本地代码
- 不需要创建任何新的目录

## 3. 安装 Go 编译器到容器

### 3.1 修改 Dockerfile.app

原始的 `docker/Dockerfile.app` 的 final stage（第88-111行）只有系统工具，没有 Go 编译器。

**在 final stage 中添加 Go 编译器安装**（在 `apt-get clean` 之前添加）：

```dockerfile
# 安装 Go 编译器（用于本地编译代码）
ENV GOLANG_VERSION=1.24.0
ENV GOPATH=/go
ENV PATH=$PATH:/usr/local/go/bin:$GOPATH/bin
RUN curl -fsSL https://go.dev/dl/go${GOLANG_VERSION}.linux-amd64.tar.gz -o /tmp/go.tar.gz && \
    tar -C /usr/local -xzf /tmp/go.tar.gz && \
    rm /tmp/go.tar.gz && \
    mkdir -p $GOPATH/src/github.com/Tencent && \
    ln -s /app $GOPATH/src/github.com/Tencent/WeKnora && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
```

**修改后的完整安装顺序**：

```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential postgresql-client default-mysql-client ca-certificates tzdata sed curl bash vim wget \
        libsqlite3-0 \
        python3 python3-pip python3-dev libffi-dev libssl-dev \
        nodejs npm \
        gosu && \
    python3 -m pip install --break-system-packages --upgrade pip setuptools wheel && \
    mkdir -p /home/appuser/.local/bin && \
    curl -LsSf https://astral.sh/uv/install.sh | CARGO_HOME=/home/appuser/.cargo UV_INSTALL_DIR=/home/appuser/.local/bin sh && \
    chown -R appuser:appuser /home/appuser && \
    ln -sf /home/appuser/.local/bin/uvx /usr/local/bin/uvx && \
    chmod +x /usr/local/bin/uvx && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 安装 Go 编译器
ENV GOLANG_VERSION=1.24.0
ENV GOPATH=/go
ENV PATH=$PATH:/usr/local/go/bin:$GOPATH/bin
RUN curl -fsSL https://go.dev/dl/go${GOLANG_VERSION}.linux-amd64.tar.gz -o /tmp/go.tar.gz && \
    tar -C /usr/local -xzf /tmp/go.tar.gz && \
    rm /tmp/go.tar.gz && \
    mkdir -p $GOPATH/src/github.com/Tencent && \
    ln -s /app $GOPATH/src/github.com/Tencent/WeKnora && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
```

### 3.2 添加国内镜像源（可选）

如果在国内构建，Debian 仓库访问困难，可以在 apt-get 之前添加阿里云镜像源：

```dockerfile
# 默认使用阿里云镜像源
RUN if [ -n "$APK_MIRROR_ARG" ]; then \
        sed -i "s@deb.debian.org@${APK_MIRROR_ARG}@g" /etc/apt/sources.list.d/debian.sources; \
    else \
        sed -i "s@deb.debian.org@mirrors.aliyun.com@g" /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && ...
```

## 4. 创建编译脚本（可选）

这一步**完全可选**，只是为了方便日常开发。

### 4.1 为什么需要编译脚本

正常编译需要输入一长串命令：

```powershell
docker exec WeKnora-app sh -c "cd /go/src/github.com/Tencent/WeKnora && go build -o /app/WeKnora ./cmd/server"
```

有了编译脚本，只需要：

```powershell
docker exec WeKnora-app sh -c "/go/src/github.com/Tencent/WeKnora/.dev/compile.sh"
```

### 4.2 脚本位置

脚本放在本地项目目录的 `.dev/compile.sh`，通过挂载让容器内也能访问：

```
本地: WeKnora/.dev/compile.sh
        ↓ 挂载 (.:/go/src/...)
容器内: /go/src/github.com/Tencent/WeKnora/.dev/compile.sh
```

### 4.3 脚本内容

`.dev/compile.sh`:

```bash
#!/bin/bash
set -e

echo "开始编译 WeKnora..."

cd /go/src/github.com/Tencent/WeKnora

# 下载依赖（首次编译需要，之后会缓存）
echo "下载 Go 依赖..."
go mod download

# 编译
echo "编译中..."
export CGO_ENABLED=1
export LDFLAGS="-X 'github.com/Tencent/WeKnora/internal/handler.Version=dev'"
go build -ldflags="-w -s $LDFLAGS" -o /app/WeKnora ./cmd/server

echo "编译完成!"
ls -lh /app/WeKnora
```

### 4.4 使用方法

```powershell
# 方式1：直接编译（不需要脚本）
docker exec WeKnora-app sh -c "cd /go/src/github.com/Tencent/WeKnora && go build -o /app/WeKnora ./cmd/server"

# 方式2：使用脚本（更简洁）
docker exec WeKnora-app sh -c "chmod +x /go/src/github.com/Tencent/WeKnora/.dev/compile.sh && /go/src/github.com/Tencent/WeKnora/.dev/compile.sh"
```

### 4.5 总结

| 问题       | 答案                      |
| -------- | ----------------------- |
| 脚本在哪创建？  | 本地宿主机 `.dev/compile.sh` |
| 脚本在哪执行？  | 容器内部                    |
| 脚本什么时候用？ | 可选，平时开发用直接编译命令就行        |
| 必须创建吗？   | 不必须，只是为了方便              |

## 5. 构建并运行

### 5.1 构建镜像

**前提**：代码已经从 GitHub 克隆到本地，不需要额外创建目录

```powershell
# 确保 Docker Desktop 已启动
docker info

# 构建 app 镜像（如果需要代理）
docker-compose build --build-arg HTTP_PROXY=http://host.docker.internal:7897 app

# 或者不需要代理
docker-compose build app
```

### 5.2 启动服务

```powershell
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker ps | findstr WeKnora
```

### 5.3 构建流程说明

```
GitHub 克隆代码（本地已有 internal/, cmd/, ...）
        ↓
docker-compose build（构建镜像时，COPY 指令把代码复制到镜像内）
        ↓
docker-compose up -d（启动容器时，volumes 挂载让容器直接访问本地代码）
```

**注意**：

- **构建时**：代码通过 Dockerfile 中的 `COPY` 指令复制到镜像
- **运行时**：volumes 挂载让容器直接读取本地代码（开发时修改代码无需重新构建）

## 6. 开发流程：修改代码并重新部署

### 6.1 前端代码修改

前端是**解释型语言**（Vue/TypeScript），不需要在容器内编译，只需要在本地构建。

**修改流程**：

```
本地修改代码 (src/views/...)
        ↓
本地构建 (npm run build)
        ↓
dist/ 目录更新
        ↓
重启前端容器（挂载的 dist 目录自动生效）
```

**命令**：

```powershell
# 1. 进入前端目录
cd frontend

# 2. 安装依赖（首次需要）
npm install

# 3. 构建前端
npm run build

# 4. 返回项目目录
cd ..

# 5. 重启前端容器
docker-compose restart frontend
```

### 6.2 后端代码修改

后端是 **Go 编译型语言**，需要在容器内编译。

**修改流程**：

```
本地修改代码 (internal/...)
        ↓
挂载让容器能看到（docker-compose.yml 中已配置）
        ↓
容器内编译 (go build)
        ↓
重启后端容器
```

**方式1：直接编译命令**

```powershell
# 1. 修改本地代码（如 internal/infrastructure/chunker/splitter.go）

# 2. 在容器内编译
docker exec WeKnora-app sh -c "cd /go/src/github.com/Tencent/WeKnora && go build -o /app/WeKnora ./cmd/server"

# 3. 重启后端容器
docker restart WeKnora-app

# 4. 验证
docker logs WeKnora-app
```

**方式2：使用编译脚本（更简洁）**

```powershell
# 1. 修改本地代码（如 internal/infrastructure/chunker/splitter.go）

# 2. 使用脚本编译
docker exec WeKnora-app sh -c "chmod +x /go/src/github.com/Tencent/WeKnora/.dev/compile.sh && /go/src/github.com/Tencent/WeKnora/.dev/compile.sh"

# 3. 重启后端容器
docker restart WeKnora-app

# 4. 验证
docker logs WeKnora-app
```

### 6.3 前端 vs 后端对比

| 对比项    | 前端                   | 后端              |
| ------ | -------------------- | --------------- |
| 语言     | Vue/TypeScript       | Go              |
| 类型     | 解释型                  | 编译型             |
| 需要编译？  | ❌ 不需要                | ✅ 需要            |
| 修改后怎么做 | `npm run build` + 重启 | `go build` + 重启 |
| 编译在哪执行 | 本地宿主机                | 容器内             |

### 6.4 一行总结

- **前端**：本地改 → 本地构建 → 重启容器
- **后端**：本地改 → 挂载到容器 → 容器内编译 → 重启容器

## 7. Docker 基本操作

### 7.1 启动 Docker Desktop

```powershell
# 方式1：使用 PowerShell 命令启动
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# 方式2：手动启动
# 点击开始菜单，搜索并打开 "Docker Desktop"
```

### 7.2 检查 Docker 状态

```powershell
# 检查 Docker 是否运行
docker info

# 如果显示 "Server" 信息，说明 Docker 已成功启动
# 如果显示 "error during connect"，说明 Docker 引擎未运行
```

### 7.3 启动 WeKnora 服务

```powershell
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker ps | findstr WeKnora

# 停止所有服务
docker-compose down

# 重启特定服务
docker-compose restart app
docker-compose restart frontend
```

### 7.4 查看容器日志

```powershell
# 查看 app 容器日志
docker logs WeKnora-app

# 实时查看日志
docker logs -f WeKnora-app

# 查看最近 100 行日志
docker logs --tail 100 WeKnora-app
```

## 8. 代理配置

### 8.1 为什么需要代理

在国内构建 Docker 镜像时，需要访问国外资源（Docker Hub、Debian 仓库等），代理可以加速访问。

### 8.2 WSL2 环境下的代理地址

| 场景            | 代理地址                            |
| ------------- | ------------------------------- |
| 宿主机 (Windows) | `127.0.0.1:端口` 或 `localhost:端口` |
| Docker 容器内    | `host.docker.internal:端口`       |

### 8.3 为 Docker 构建配置代理

```powershell
docker-compose build `
  --build-arg HTTP_PROXY=http://host.docker.internal:7897 `
  --build-arg HTTPS_PROXY=http://host.docker.internal:7897 `
  --build-arg http_proxy=http://host.docker.internal:7897 `
  --build-arg https_proxy=http://host.docker.internal:7897 `
  app
```

## 9. 遇到的问题及解决方案

### 问题1：Docker Desktop 未启动

**错误信息**：

```
error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/..."
```

**解决方案**：

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
# 等待 Docker 图标变为绿色
docker info
```

### 问题2：代理连接失败

**错误信息**：

```
Could not connect to 127.0.0.1:7897 (127.0.0.1). - Connection refused
```

**原因**：WSL2 环境中，容器内不能使用 `127.0.0.1` 访问宿主机代理

**解决方案**：使用 `host.docker.internal` 地址

### 问题3：apt-get 无法连接 Debian 仓库

**错误信息**：

```
E: Failed to fetch http://deb.debian.org/debian/...  Unable to connect
```

**解决方案**：在 Dockerfile 中使用国内镜像源：

```dockerfile
sed -i "s@deb.debian.org@mirrors.aliyun.com@g" /etc/apt/sources.list.d/debian.sources
```

### 问题4：前端修改后不生效

**原因**：挂载了 `src` 目录，但容器实际使用的是 `dist` 目录

**解决方案**：

```yaml
# 错误配置
volumes:
  - ./frontend/src:/usr/share/nginx/html/src

# 正确配置
volumes:
  - ./frontend/dist:/usr/share/nginx/html
```

### 问题5：正则表达式分隔符不生效

**现象**：设置了 `第.*章` 作为分隔符，但分块结果不符合预期

**原因**：`splitBySeparators` 函数使用 `regexp.QuoteMeta()` 转义了所有分隔符

**解决方案**：

```go
func isRegexPattern(s string) bool {
    regexMetaChars := []byte("*+?()[]{}|\\^$.#")
    for _, c := range []byte(s) {
        for _, m := range regexMetaChars {
            if c == m {
                return true
            }
        }
    }
    return false
}

for _, sep := range separators {
    if isRegexPattern(sep) {
        parts = append(parts, sep)  // 正则表达式直接使用
    } else {
        parts = append(parts, regexp.QuoteMeta(sep))
    }
}
```

## 10. 代码挂载概念

### 10.1 什么是代码挂载

代码挂载（Volume Mount）是指将本地文件系统目录映射到容器内部，使容器可以直接读取本地修改的代码文件。

### 10.2 挂载类型

| 类型           | 说明            | 适用场景        |
| ------------ | ------------- | ----------- |
| `bind mount` | 直接映射本地目录到容器   | 开发环境，代码频繁修改 |
| `volume`     | Docker 内部管理的卷 | 生产环境，数据持久化  |

### 10.3 WeKnora 项目代码挂载配置

#### 前端挂载

```yaml
frontend:
  volumes:
    - ./frontend/dist:/usr/share/nginx/html
```

**说明**：

- `./frontend/dist` 是本地构建后的前端文件目录
- `/usr/share/nginx/html` 是容器内 Nginx 读取静态文件的位置
- **重要**：容器内使用的是构建后的 `dist` 目录，而不是源码 `src` 目录

#### 后端挂载

```yaml
app:
  volumes:
    - .:/go/src/github.com/Tencent/WeKnora
```

**说明**：

- `.` 表示本地项目根目录（克隆下来就有的）
- 挂载后容器内 `/go/src/github.com/Tencent/WeKnora` 直接指向本地代码
- Go 编译器需要代码在 GOPATH 路径下才能正确编译

## 11. 数据挂载和数据迁移

### 11.1 为什么需要数据挂载

Docker 默认使用 **named volumes** 存储数据，数据存在 Docker 内部：

- ❌ 换电脑数据无法迁移
- ❌ 无法直接查看和备份数据

使用 **bind mounts** 将数据存储到本地目录：

- ✅ 换电脑直接迁移整个项目目录
- ✅ 可以直接查看和备份数据

### 11.2 WeKnora 数据挂载配置

以下是所有数据服务的挂载配置（已修改为 bind mounts）：

```yaml
# PostgreSQL 数据库 - 使用本地目录便于数据迁移
postgres:
  volumes:
    - ./volumes/postgres:/var/lib/postgresql/data

# 上传的文件和知识库文档
app:
  volumes:
    - ./volumes/data_files:/data/files

# Ollama 大语言模型
ollama:
  volumes:
    - ./volumes/ollama:/root/.ollama

# Rerank 模型
rerank:
  volumes:
    - ./volumes/rerank:/app/model

# MinIO 对象存储
minio:
  volumes:
    - ./volumes/minio:/data

# Neo4j 图数据库
neo4j:
  volumes:
    - ./volumes/neo4j:/data

# Qdrant 向量数据库
qdrant:
  volumes:
    - ./volumes/qdrant:/qdrant/storage

# Milvus 向量数据库
milvus:
  volumes:
    - ./volumes/milvus:/var/lib/milvus

# Weaviate 向量数据库
weaviate:
  volumes:
    - ./volumes/weaviate:/var/lib/weaviate
```

### 11.3 路径命名规则

**容器内路径是镜像设计者决定的，不能修改**
**本地路径是我们自己决定的，应该便于理解和迁移**

命名规则：

| 服务       | 本地路径                   | 规则        |
| -------- | ---------------------- | --------- |
| postgres | `./volumes/postgres`   | 服务名       |
| minio    | `./volumes/minio`      | 服务名       |
| neo4j    | `./volumes/neo4j`      | 服务名       |
| qdrant   | `./volumes/qdrant`     | 服务名       |
| milvus   | `./volumes/milvus`     | 服务名       |
| weaviate | `./volumes/weaviate`   | 服务名       |
| app data | `./volumes/data_files` | 用途 + 文件类型 |

所有数据统一放在 `volumes/` 目录下，便于集中管理和迁移。

### 11.4 数据目录说明

| 目录                     | 容器内路径                      | 数据类型             | 重要性    | 迁移必要性 |
| ---------------------- | -------------------------- | ---------------- | ------ | ----- |
| `./volumes/postgres`   | `/var/lib/postgresql/data` | 用户账户、知识库配置、文档元数据 | ⭐⭐⭐ 极高 | 必须迁移  |
| `./volumes/data_files` | `/data/files`              | 上传的文档、文件         | ⭐⭐⭐ 极高 | 必须迁移  |
| `./volumes/ollama`     | `/root/.ollama`            | LLM 模型权重（非常大）    | ⭐⭐ 可选  | 建议迁移  |
| `./volumes/rerank`     | `/app/model`               | Rerank 模型        | ⭐⭐ 可选  | 建议迁移  |
| `./volumes/minio`      | `/data`                    | 对象存储数据           | ⭐⭐ 中等  | 建议迁移  |
| `./volumes/neo4j`      | `/data`                    | 知识图谱数据           | ⭐⭐ 中等  | 建议迁移  |
| `./volumes/qdrant`     | `/qdrant/storage`          | 向量索引数据           | ⭐⭐ 中等  | 建议迁移  |
| `./volumes/milvus`     | `/var/lib/milvus`          | 向量索引数据           | ⭐⭐ 中等  | 建议迁移  |
| `./volumes/weaviate`   | `/var/lib/weaviate`        | 向量索引数据           | ⭐⭐ 中等  | 建议迁移  |
| `./frontend/dist`      | `/usr/share/nginx/html`    | 前端构建文件           | ⭐ 可忽略  | 无需迁移  |

### 11.5 迁移到新电脑

1. **复制整个项目目录**
   ```powershell
   # 把 WeKnora 整个目录复制到新电脑
   robocopy /E "F:\WeKnora" "\\新电脑\C$\WeKnora"
   ```
2. **确保 Docker Desktop 运行**
3. **启动服务**
   ```powershell
   cd WeKnora
   docker-compose up -d
   ```
4. **验证数据**
   ```powershell
   # 检查数据库是否正常
   docker exec WeKnora-postgres psql -U postgres -c "\l"

   # 检查文件是否存在
   ls ./volumes/data_files
   ```

### 11.6 备份数据

```powershell
# 备份整个 volumes 目录
tar -czvf weknora_backup.tar.gz ./volumes

# 或单独备份数据库
docker exec WeKnora-postgres pg_dump -U postgres weknora > backup.sql
```

## 12. 最佳实践

1. **开发环境**
   - 前端代码修改后重新构建并重启前端容器
   - 后端代码修改后在容器内编译并重启后端容器
   - 使用 `docker-compose logs -f app` 实时查看日志
2. **代理配置**
   - 始终使用 `host.docker.internal` 而不是 `127.0.0.1`
   - 国内镜像源配置避免代理影响 apt-get
3. **挂载配置**
   - 确保挂载正确的目录（dist 而不是 src）
   - Go 代码需要 Go 编译器才能在容器内编译
   - 生产环境不要使用代码挂载，使用镜像构建
4. **数据迁移**
   - 使用 bind mounts 存储数据，便于迁移
   - 定期备份重要数据（postgres\_data, data\_files）
   - 模型数据（ollama\_data, rerank\_data）根据需要迁移
5. **调试技巧**
   - `docker exec -it container_name sh` 进入容器调试
   - `docker diff container_name` 查看容器内文件变化
   - `docker inspect container_name` 查看容器详细信息

