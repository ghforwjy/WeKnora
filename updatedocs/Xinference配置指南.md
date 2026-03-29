# Xinference 配置指南

## 1. 简介

Xinference 是一个强大的模型服务框架，支持部署和服务各种大语言模型、嵌入模型和重排序模型。本文档将详细说明如何启用 Xinference 的 OpenAI 兼容接口，以及如何正确加载模型。

## 2. 启用 OpenAI 兼容接口

Xinference 默认启用 OpenAI 兼容接口，无需额外配置。当 Xinference 服务启动后，您可以通过以下 URL 访问 OpenAI 兼容的 API：

```
http://localhost:9997/v1
```

### 2.1 验证接口可用性

您可以通过发送 HTTP 请求来验证接口是否正常工作：

```bash
# 检查模型列表
curl http://localhost:9997/v1/models

# 测试聊天接口
curl -X POST http://localhost:9997/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "chatglm3", "messages": [{"role": "user", "content": "你好"}]}'
```

## 3. 正确加载模型

### 3.1 通过 API 加载模型

您可以使用 HTTP POST 请求来加载模型：

```bash
# 加载重排序模型
curl -X POST http://localhost:9997/v1/models \
  -H "Content-Type: application/json" \
  -d '{"model_name": "bge-reranker-v2-m3", "model_type": "rerank"}'

# 加载嵌入模型
curl -X POST http://localhost:9997/v1/models \
  -H "Content-Type: application/json" \
  -d '{"model_name": "bge-m3:latest", "model_type": "embedding"}'

# 加载聊天模型
curl -X POST http://localhost:9997/v1/models \
  -H "Content-Type: application/json" \
  -d '{"model_name": "chatglm3", "model_type": "llm"}'
```

### 3.2 在 Docker Compose 中自动加载模型

为了确保模型在容器重启后自动加载，您可以修改 `docker-compose.yml` 文件，为 Xinference 服务添加启动脚本：

```yaml
xinference:
  image: xprobe/xinference:latest
  container_name: WeKnora-xinference
  ports:
    - "${XINFERENCE_PORT:-9997}:9997"
  volumes:
    - ./volumes/xinference:/root/.xinference
    - ./volumes/xinference/model_cache:/root/.cache
  networks:
    - WeKnora-network
  restart: unless-stopped
  profiles:
    - xinference
    - full
  command: >
    bash -c "xinference-local -H 0.0.0.0 & until curl -s http://localhost:9997/v1/models; do sleep 1; done && curl -X POST http://localhost:9997/v1/models -H 'Content-Type: application/json' -d '{\"model_name\": \"bge-reranker-v2-m3\", \"model_type\": \"rerank\"}' && wait"
  environment:
    - XINFERENCE_MODEL_SRC=huggingface
  extra_hosts:
    - "host.docker.internal:host-gateway"
  runtime: nvidia
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9997/v1/models"]
    interval: 1s
    timeout: 5s
    retries: 30
```

这个配置会：
1. 启动 Xinference 服务
2. 轮询检查服务是否可用
3. 服务可用后自动加载 bge-reranker-v2-m3 模型
4. 等待服务继续运行

### 3.3 模型加载状态检查

您可以通过以下命令检查模型是否成功加载：

```bash
curl http://localhost:9997/v1/models
```

如果模型成功加载，您会在响应中看到模型信息。

## 4. 故障排除

### 4.1 模型加载失败

如果模型加载失败，可能的原因包括：

1. **模型文件不存在**：确保模型文件已经下载到挂载目录
2. **网络问题**：检查网络连接，确保能够访问 Hugging Face
3. **资源不足**：检查 GPU 内存是否足够加载模型
4. **权限问题**：确保容器有足够的权限访问模型文件

### 4.2 服务启动失败

如果 Xinference 服务启动失败，您可以查看容器日志来了解具体原因：

```bash
docker logs WeKnora-xinference
```

## 5. 最佳实践

1. **使用持久化挂载**：将模型目录挂载到本地，避免每次容器重启都重新下载模型
2. **合理配置资源**：根据模型大小分配足够的 GPU 内存
3. **定期更新模型**：定期检查并更新模型版本
4. **监控服务状态**：使用健康检查监控服务状态
5. **设置合理的超时**：在启动脚本中设置合理的超时时间，避免服务启动失败

## 6. 示例：使用 OpenAI 客户端访问 Xinference

您可以使用 OpenAI 客户端库来访问 Xinference 的 OpenAI 兼容接口：

```python
from openai import OpenAI

client = OpenAI(
    api_key="not_empty",  # 任意非空字符串即可
    base_url="http://localhost:9997/v1"
)

# 聊天完成
response = client.chat.completions.create(
    model="chatglm3",
    messages=[
        {"role": "user", "content": "你好"}
    ]
)
print(response.choices[0].message.content)

# 嵌入生成
response = client.embeddings.create(
    model="bge-m3:latest",
    input="这是一个测试句子"
)
print(response.data[0].embedding)

# 重排序
response = client.rerank.create(
    model="bge-reranker-v2-m3",
    query="软件",
    documents=[
        "软件是计算机系统中的程序和数据",
        "硬件是计算机的物理组件",
        "网络是连接计算机的系统"
    ]
)
print(response.results)
```

## 7. 总结

通过本文档，您应该已经了解了如何：

1. 启用和验证 Xinference 的 OpenAI 兼容接口
2. 通过 API 手动加载模型
3. 在 Docker Compose 中配置自动加载模型
4. 排查模型加载和服务启动问题
5. 使用 OpenAI 客户端访问 Xinference

遵循这些指南，您可以确保 Xinference 服务正常运行，并在容器重启后自动加载所需的模型。