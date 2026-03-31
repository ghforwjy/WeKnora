# 容器内 Go 编译踩坑记录

## 背景
在 Windows 环境下开发 WeKnora 项目时，需要在容器内编译 Go 代码，但过程中遇到了多个坑。本文记录这些失败的做法，避免后续重复踩坑。

## 失败做法一：Windows 本地直接编译 Go 代码

### 做法
尝试在 Windows 宿主机上直接执行 `go build ./...`

### 失败原因
Windows 环境不支持直接编译 Go 代码。WeKnora 项目的 Go 代码依赖于 Linux 特定的系统调用和库，在 Windows 上无法直接编译通过。

### 结论
**此路不通**，必须在 Linux 容器内进行编译。

---

## 失败做法二：使用 Docker Compose 重新构建后端容器

### 做法
尝试使用 `docker-compose up --build app` 或 `docker-compose build app` 重新构建后端容器，希望新构建的容器能使用代理配置。

### 失败原因
1. **依赖服务也会被重建**：后端服务（app）在 docker-compose.yml 中配置了 `depends_on: docreader`，导致重建 app 时也会触发 docreader 的重建
2. **docreader 构建耗时极长**：docreader 是 Python 文档解析服务，需要下载和安装大量 Python 依赖包（pandas、onnxruntime、scikit-image、magika、rapidocr 等），整个过程可能需要几十分钟甚至更久
3. **无意义重复构建**：如果只是想测试后端 Go 代码的编译，完全不需要重建 docreader 服务

### 实际现象
```
=> [docreader builder  8/10] RUN pip install uv --break-system-packages && python -m uv sync --no-dev
=> => # Downloaded pandas
=> => # Downloaded onnxruntime
=> => # Downloaded scikit-image
=> => # Downloaded magika
=> => # Downloaded rapidocr
=> => # Downloaded numpy
# ... 耗时 300+ 秒
```

### 结论
**不要这样做**，除非确实需要更新 docreader 服务。

---

## 失败做法三：容器内使用 127.0.0.1 访问宿主机代理

### 做法
在容器内设置代理环境变量时，使用 `127.0.0.1:7897` 指向宿主机代理

```bash
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
```

### 失败原因
容器内的 `127.0.0.1` 指向的是容器本身，而不是宿主机。因此容器无法通过 `127.0.0.1` 访问宿主机的代理服务。

### 正确做法
使用 Docker 提供的特殊 DNS 名称 `host.docker.internal` 来访问宿主机：

```bash
export HTTP_PROXY=http://host.docker.internal:7897
export HTTPS_PROXY=http://host.docker.internal:7897
```

### 配置更新
需要在 `.env` 文件中将代理地址从 `127.0.0.1` 改为 `host.docker.internal`：

```env
# 错误配置
HTTP_PROXY=http://127.0.0.1:7897
HTTPS_PROXY=http://127.0.0.1:7897

# 正确配置
HTTP_PROXY=http://host.docker.internal:7897
HTTPS_PROXY=http://host.docker.internal:7897
```

---

## 失败做法四：修改 docker-compose.yml 后期望已运行容器自动生效

### 做法
修改了 docker-compose.yml 中的代理环境变量配置，期望已运行的容器自动使用新配置。

### 失败原因
已运行的容器不会自动感知 docker-compose.yml 的变更。必须重启容器才能应用新的环境变量配置。

### 正确做法
```bash
# 停止并删除旧容器
docker-compose stop app
docker-compose rm -f app

# 重新启动容器（使用新配置）
docker-compose up -d app
```

---

## 成功做法：进入现有容器手动设置代理并编译

### 步骤

1. **确保容器使用正确的代理配置启动**
   - 修改 `.env` 文件，使用 `host.docker.internal:7897`
   - 重启容器以应用新配置

2. **进入容器并执行编译（推荐方式）**

   **方式一：交互式进入容器（推荐，可以看到实时输出）**
   ```bash
   docker exec -it <容器名> bash
   ```
   然后在容器内执行：
   ```bash
   cd /app_src
   export HTTP_PROXY=http://host.docker.internal:7897
   export HTTPS_PROXY=http://host.docker.internal:7897
   go build -v ./...
   ```

   **方式二：直接执行命令（注意使用单引号）**
   ```bash
   docker exec -it <容器名> bash -c 'cd /app_src && export HTTP_PROXY=http://host.docker.internal:7897 && export HTTPS_PROXY=http://host.docker.internal:7897 && go build -v ./...'
   ```
   > ⚠️ **注意**：必须使用单引号 `'...'` 包裹命令，避免变量在宿主机 shell 中被提前解析。

3. **注意目录位置**
   - 源代码挂载在 `/app_src` 目录（不是 `/app`）
   - 必须先 `cd /app_src` 再执行编译

### 验证代理生效
如果看到类似以下的输出，说明代理配置生效，Go 正在通过代理下载依赖：
```
go: downloading github.com/duckdb/duckdb-go-bindings/linux-amd64 v0.1.24
go: downloading github.com/pierrec/lz4/v4 v4.1.22
```

### 常见问题

**问题：使用双引号的命令没有生效**
```bash
# 错误做法（双引号会导致变量在宿主机解析）
docker exec -it <容器名> bash -c "cd /app_src && export HTTP_PROXY=http://host.docker.internal:7897 && go build ./..."

# 正确做法（使用单引号）
docker exec -it <容器名> bash -c 'cd /app_src && export HTTP_PROXY=http://host.docker.internal:7897 && go build ./...'
```

---

## 总结

| 做法 | 是否可行 | 说明 |
|------|----------|------|
| Windows 本地编译 Go | ❌ 不可行 | Windows 不支持 |
| Docker Compose 重建后端 | ❌ 不推荐 | 会触发 docreader 重建，耗时极长 |
| 容器内使用 127.0.0.1 | ❌ 不可行 | 容器内 127.0.0.1 指向容器自身 |
| 修改配置后期望自动生效 | ❌ 不可行 | 必须重启容器 |
| 进入现有容器手动编译 | ✅ 推荐 | 快速、可控、不影响其他服务 |

---

## 附录：关键配置修改记录

### 修改 1：.env 文件
```env
# 代理配置（容器内使用 host.docker.internal 访问宿主机代理）
HTTP_PROXY=http://host.docker.internal:7897
HTTPS_PROXY=http://host.docker.internal:7897
NO_PROXY=localhost,127.0.0.1,0.0.0.0,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,.local,host.docker.internal
```

### 修改 2：docker-compose.yml（后端服务）
已在 app 服务中添加了代理环境变量：
```yaml
environment:
  - HTTP_PROXY=${HTTP_PROXY:-}
  - HTTPS_PROXY=${HTTPS_PROXY:-}
  - NO_PROXY=${NO_PROXY:-}
```

### 修改 3：docker/Dockerfile.docreader
移除了 `--locked` 标志以避免依赖锁文件问题：
```dockerfile
# 原配置（会失败）
RUN python -m uv sync --locked --no-dev

# 修改后（正常）
RUN python -m uv sync --no-dev
```

---

*文档创建时间：2026-03-31*
