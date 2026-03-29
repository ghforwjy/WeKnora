import gc
import os
import torch
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from transformers import AutoModelForSequenceClassification, AutoTokenizer

security = HTTPBearer(auto_error=False)

class RerankRequest(BaseModel):
    model: str
    query: str
    documents: List[str]
    truncate_prompt_tokens: Optional[int] = 511

class DocumentInfo(BaseModel):
    text: str

class RankResult(BaseModel):
    index: int
    document: DocumentInfo
    relevance_score: float

class RerankResponse(BaseModel):
    results: List[RankResult]

model_path = os.environ.get("RERANK_MODEL_PATH", "/app/model")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
api_key = os.environ.get("RERANK_API_KEY", "")

print(f"正在加载模型: {model_path}")
print(f"使用的设备: {device}")
print(f"API Key 验证: {'开启' if api_key else '关闭'}")

tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path)
model.to(device)
model.eval()
print("模型加载成功!")

app = FastAPI(
    title="BGE Reranker API",
    description="BGE-Reranker-v2-m3 重排序服务 (OpenAI Compatible)",
    version="1.0.0"
)

async def verify_api_key(credentials: Optional[HTTPAuthorizationCredentials] = Header(None)):
    if not api_key:
        return
    if credentials is None or credentials.credentials != api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.post("/rerank", response_model=RerankResponse)
async def rerank_endpoint(request: RerankRequest, credentials: Optional[HTTPAuthorizationCredentials] = Header(None)):
    await verify_api_key(credentials)

    pairs = [[request.query, doc] for doc in request.documents]

    with torch.no_grad():
        inputs = outputs = logits = None
        try:
            max_length = min(request.truncate_prompt_tokens * 2, 1024) if request.truncate_prompt_tokens else 1024
            inputs = tokenizer(pairs, padding=True, truncation=True, return_tensors="pt", max_length=max_length).to(device)
            outputs = model(**inputs, return_dict=True)
            logits = outputs.logits.view(-1,).float()
            scores = torch.sigmoid(logits)
        finally:
            del inputs, outputs, logits
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch, "mps") and torch.mps.is_available():
                torch.mps.empty_cache()

    results = []
    for i, (text, score_val) in enumerate(zip(request.documents, scores)):
        doc_info = DocumentInfo(text=text)
        result = RankResult(
            index=i,
            document=doc_info,
            relevance_score=round(score_val.item(), 6)
        )
        results.append(result)

    sorted_results = sorted(results, key=lambda x: x.relevance_score, reverse=True)
    return {"results": sorted_results}

@app.get("/")
async def read_root(credentials: Optional[HTTPAuthorizationCredentials] = Header(None)):
    await verify_api_key(credentials)
    return {"status": "BGE Reranker API is running", "model": model_path}

if __name__ == "__main__":
    port = int(os.environ.get("RERANK_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)