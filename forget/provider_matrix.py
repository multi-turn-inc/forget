from __future__ import annotations

from typing import Any


BASELINE_REF = "d772f9a961a8de5ff10383c938c4f34ae592e48a"

MEM0_PROVIDER_BASELINE: dict[str, list[str]] = {
    "llms": [
        "anthropic",
        "aws_bedrock",
        "azure_openai",
        "azure_openai_structured",
        "deepseek",
        "gemini",
        "groq",
        "langchain",
        "litellm",
        "lmstudio",
        "minimax",
        "ollama",
        "openai",
        "openai_structured",
        "sarvam",
        "together",
        "vllm",
        "xai",
    ],
    "embeddings": [
        "aws_bedrock",
        "azure_openai",
        "fastembed",
        "gemini",
        "huggingface",
        "langchain",
        "lmstudio",
        "mock",
        "ollama",
        "openai",
        "together",
        "vertexai",
    ],
    "vector_stores": [
        "azure_ai_search",
        "azure_mysql",
        "baidu",
        "cassandra",
        "chroma",
        "databricks",
        "elasticsearch",
        "faiss",
        "langchain",
        "milvus",
        "mongodb",
        "neptune_analytics",
        "opensearch",
        "pgvector",
        "pinecone",
        "qdrant",
        "redis",
        "s3_vectors",
        "supabase",
        "turbopuffer",
        "upstash_vector",
        "valkey",
        "vertex_ai_vector_search",
        "weaviate",
    ],
    "graphs": [],
    "rerankers": [
        "cohere_reranker",
        "huggingface_reranker",
        "llm_reranker",
        "sentence_transformer_reranker",
        "zero_entropy_reranker",
    ],
}

MEM1_PROVIDER_STATUS: dict[str, dict[str, dict[str, str]]] = {
    "llms": {
        "local": {
            "status": "native",
            "notes": "Deterministic rule extractor used when external provider credentials are absent.",
        },
        "anthropic": {
            "status": "compatible_endpoint",
            "notes": "Uses Anthropic Messages API with ANTHROPIC_API_KEY-compatible configuration.",
        },
        "aws_bedrock": {
            "status": "compatible_endpoint",
            "notes": "Optional AWS Bedrock runtime adapter using boto3 bedrock-runtime when installed.",
        },
        "azure_openai": {
            "status": "compatible_endpoint",
            "notes": "Uses Azure OpenAI chat completions through Azure resource or /openai/v1 endpoints.",
        },
        "azure_openai_structured": {
            "status": "compatible_endpoint",
            "notes": "Structured-output alias for the Azure OpenAI chat-completions runtime path.",
        },
        "openai": {
            "status": "compatible_endpoint",
            "notes": "Uses MEM1_LLM_API_KEY and OpenAI-compatible /chat/completions.",
        },
        "openai_compatible": {
            "status": "native_alias",
            "notes": "Provider alias for OpenAI-compatible chat endpoints.",
        },
        "deepseek": {
            "status": "compatible_endpoint",
            "notes": "Uses the OpenAI-compatible chat-completions path with a DeepSeek base URL and API key env.",
        },
        "gemini": {
            "status": "compatible_endpoint",
            "notes": "Uses the Gemini REST generateContent endpoint with GEMINI_API_KEY-compatible configuration.",
        },
        "groq": {
            "status": "compatible_endpoint",
            "notes": "Uses the OpenAI-compatible chat-completions path with a Groq base URL and API key env.",
        },
        "lmstudio": {
            "status": "compatible_endpoint",
            "notes": "Uses LM Studio's local OpenAI-compatible chat-completions endpoint.",
        },
        "litellm": {
            "status": "compatible_endpoint",
            "notes": "Uses a LiteLLM proxy OpenAI-compatible chat-completions endpoint.",
        },
        "langchain": {
            "status": "sdk_wrapper",
            "notes": "In-process wrapper around an existing LangChain BaseChatModel; not a hosted runtime endpoint.",
        },
        "minimax": {
            "status": "compatible_endpoint",
            "notes": "Uses the OpenAI-compatible chat-completions path with a MiniMax base URL and API key env.",
        },
        "ollama": {
            "status": "compatible_endpoint",
            "notes": "Uses Ollama's local OpenAI-compatible chat-completions endpoint.",
        },
        "sarvam": {
            "status": "compatible_endpoint",
            "notes": "Uses Sarvam's chat-completions endpoint with SARVAM_API_KEY-compatible configuration.",
        },
        "together": {
            "status": "compatible_endpoint",
            "notes": "Uses the OpenAI-compatible chat-completions path with a Together base URL and API key env.",
        },
        "vllm": {
            "status": "compatible_endpoint",
            "notes": "Uses a self-hosted vLLM OpenAI-compatible chat-completions endpoint.",
        },
        "xai": {
            "status": "compatible_endpoint",
            "notes": "Uses the OpenAI-compatible chat-completions path with an xAI base URL and API key env.",
        },
    },
    "embeddings": {
        "local": {
            "status": "native",
            "notes": "Deterministic 128-dimensional embedding fallback.",
        },
        "mock": {
            "status": "native_alias",
            "notes": "Maps to the deterministic local embedding path for Mem0 SDK test compatibility.",
        },
        "openai": {
            "status": "compatible_endpoint",
            "notes": "Uses MEM1_EMBEDDING_API_KEY and OpenAI-compatible /embeddings.",
        },
        "openai_compatible": {
            "status": "native_alias",
            "notes": "Provider alias for OpenAI-compatible embedding endpoints.",
        },
        "aws_bedrock": {
            "status": "compatible_endpoint",
            "notes": "Optional AWS Bedrock embedding adapter using boto3 bedrock-runtime when installed.",
        },
        "azure_openai": {
            "status": "compatible_endpoint",
            "notes": "Uses Azure OpenAI embeddings through Azure resource or /openai/v1 endpoints.",
        },
        "fastembed": {
            "status": "compatible_endpoint",
            "notes": "Optional local FastEmbed ONNX embedding adapter when fastembed is installed.",
        },
        "gemini": {
            "status": "compatible_endpoint",
            "notes": "Uses the Gemini REST embedContent endpoint with GEMINI_API_KEY-compatible configuration.",
        },
        "huggingface": {
            "status": "compatible_endpoint",
            "notes": "Uses local SentenceTransformers or a Hugging Face TEI/OpenAI-compatible embeddings endpoint.",
        },
        "langchain": {
            "status": "sdk_wrapper",
            "notes": "In-process wrapper around an existing LangChain Embeddings client; not a hosted runtime endpoint.",
        },
        "lmstudio": {
            "status": "compatible_endpoint",
            "notes": "Uses LM Studio's local OpenAI-compatible embeddings endpoint.",
        },
        "ollama": {
            "status": "compatible_endpoint",
            "notes": "Uses Ollama's local OpenAI-compatible embeddings endpoint.",
        },
        "together": {
            "status": "compatible_endpoint",
            "notes": "Uses the OpenAI-compatible embeddings path with a Together base URL and API key env.",
        },
        "vllm": {
            "status": "compatible_endpoint",
            "notes": "Uses a self-hosted vLLM OpenAI-compatible embeddings endpoint.",
        },
        "vertexai": {
            "status": "compatible_endpoint",
            "notes": "Optional Vertex AI text embedding adapter using the vertexai SDK when installed.",
        },
    },
    "vector_stores": {
        "sqlite": {
            "status": "native",
            "notes": "Single-file persistent store with JSON embeddings and cosine scoring.",
        },
        "qdrant": {
            "status": "compatible_endpoint",
            "notes": "Optional Qdrant REST mirror/query adapter while SQLite remains the authoritative memory store.",
        },
        "s3_vectors": {
            "status": "compatible_endpoint",
            "notes": "Optional Amazon S3 Vectors mirror/query adapter using boto3 when installed.",
        },
        "redis": {
            "status": "compatible_endpoint",
            "notes": "Optional Redis Search mirror/query adapter using redis-py when installed.",
        },
        "valkey": {
            "status": "compatible_endpoint",
            "notes": "Optional Valkey Search mirror/query adapter using valkey-py when installed.",
        },
        "faiss": {
            "status": "compatible_endpoint",
            "notes": "Optional local FAISS mirror/query adapter using faiss-cpu or faiss-gpu when installed.",
        },
        "cassandra": {
            "status": "compatible_endpoint",
            "notes": "Optional Cassandra/Astra DB mirror/query adapter using cassandra-driver when installed.",
        },
        "azure_mysql": {
            "status": "compatible_endpoint",
            "notes": "Optional Azure Database for MySQL mirror/query adapter using PyMySQL when installed.",
        },
        "baidu": {
            "status": "compatible_endpoint",
            "notes": "Optional Baidu Mochow vector database mirror/query adapter using pymochow when installed.",
        },
        "neptune_analytics": {
            "status": "compatible_endpoint",
            "notes": "Optional Amazon Neptune Analytics vector mirror/query adapter using langchain-aws when installed.",
        },
        "vertex_ai_vector_search": {
            "status": "compatible_endpoint",
            "notes": "Optional Vertex AI Vector Search adapter using google-cloud-aiplatform when installed.",
        },
        "langchain": {
            "status": "sdk_wrapper",
            "notes": "In-process wrapper around an existing LangChain VectorStore client; not a hosted runtime endpoint.",
        },
        "pgvector": {
            "status": "compatible_endpoint",
            "notes": "Optional PostgreSQL pgvector mirror/query adapter using psycopg when installed.",
        },
        "supabase": {
            "status": "compatible_endpoint",
            "notes": "Optional Supabase Postgres pgvector-compatible mirror/query adapter using psycopg.",
        },
        "pinecone": {
            "status": "compatible_endpoint",
            "notes": "Optional Pinecone data-plane REST mirror/query adapter using Api-Key and index host configuration.",
        },
        "upstash_vector": {
            "status": "compatible_endpoint",
            "notes": "Optional Upstash Vector REST mirror/query adapter using REST URL and Bearer token configuration.",
        },
        "elasticsearch": {
            "status": "compatible_endpoint",
            "notes": "Optional Elasticsearch REST mirror/query adapter using dense_vector and script_score cosine similarity.",
        },
        "turbopuffer": {
            "status": "compatible_endpoint",
            "notes": "Optional turbopuffer REST mirror/query adapter using namespace write/query endpoints.",
        },
        "opensearch": {
            "status": "compatible_endpoint",
            "notes": "Optional OpenSearch REST mirror/query adapter using knn_vector and knn_score script queries.",
        },
        "weaviate": {
            "status": "compatible_endpoint",
            "notes": "Optional Weaviate REST object mirror plus GraphQL nearVector query adapter.",
        },
        "chroma": {
            "status": "compatible_endpoint",
            "notes": "Optional Chroma self-hosted REST collection mirror/query adapter.",
        },
        "milvus": {
            "status": "compatible_endpoint",
            "notes": "Optional Milvus/Zilliz REST v2 mirror/query adapter using vectordb entity endpoints.",
        },
        "mongodb": {
            "status": "compatible_endpoint",
            "notes": "Optional MongoDB Atlas Vector Search mirror/query adapter using pymongo when installed.",
        },
        "azure_ai_search": {
            "status": "compatible_endpoint",
            "notes": "Optional Azure AI Search REST mirror/query adapter using search.index and vectorQueries.",
        },
        "databricks": {
            "status": "compatible_endpoint",
            "notes": "Optional Databricks AI Search REST direct-access mirror/query adapter.",
        },
    },
    "graphs": {
        "entity_links": {
            "status": "native",
            "notes": "Lightweight entity extraction, aliases, and relationship links; not a full Mem0 graph provider.",
        },
    },
    "rerankers": {
        "cohere_reranker": {
            "status": "compatible_endpoint",
            "notes": "Uses Cohere v2 /rerank with COHERE_API_KEY-compatible configuration.",
        },
        "huggingface_reranker": {
            "status": "compatible_endpoint",
            "notes": "Optional Hugging Face cross-encoder reranker using transformers and torch when installed.",
        },
        "llm_reranker": {
            "status": "compatible_endpoint",
            "notes": "Uses an OpenAI-compatible chat-completions endpoint to score memory relevance.",
        },
        "local": {
            "status": "native",
            "notes": "Deterministic lexical/entity overlap scoring inside search and context assembly.",
        },
        "sentence_transformer_reranker": {
            "status": "compatible_endpoint",
            "notes": "Optional SentenceTransformers cross-encoder reranker when sentence-transformers is installed.",
        },
        "zero_entropy_reranker": {
            "status": "compatible_endpoint",
            "notes": "Optional ZeroEntropy rerank adapter using ZERO_ENTROPY_API_KEY-compatible configuration.",
        },
    },
}


def _provider_entry(category: str, provider: str) -> dict[str, str]:
    status = MEM1_PROVIDER_STATUS.get(category, {}).get(provider)
    if status:
        return {"provider": provider, **status}
    if category in {"llms", "embeddings"} and provider in {"openai", "openai_structured"}:
        return {
            "provider": provider,
            "status": "compatible_endpoint",
            "notes": "Covered through the OpenAI-compatible API path, not through an upstream provider class.",
        }
    return {
        "provider": provider,
        "status": "adapter_needed",
        "notes": "Public Mem0 provider module exists; Forget currently needs a provider adapter before claiming parity.",
    }


def provider_parity_payload(
    baseline: dict[str, list[str]] | None = None,
    *,
    source: str = "github.com/mem0ai/mem0",
    ref: str | None = None,
) -> dict[str, Any]:
    resolved_baseline = baseline or MEM0_PROVIDER_BASELINE
    categories: dict[str, Any] = {}
    for category, baseline_providers in resolved_baseline.items():
        mem1_only = sorted(set(MEM1_PROVIDER_STATUS.get(category, {})) - set(baseline_providers))
        entries = [_provider_entry(category, provider) for provider in baseline_providers]
        entries.extend({"provider": provider, **MEM1_PROVIDER_STATUS[category][provider]} for provider in mem1_only)
        supported = [entry for entry in entries if entry["status"] in {"native", "native_alias", "compatible_endpoint"}]
        categories[category] = {
            "baseline_count": len(baseline_providers),
            "tracked_count": len(entries),
            "supported_count": len(supported),
            "adapter_needed_count": len([entry for entry in entries if entry["status"] == "adapter_needed"]),
            "providers": entries,
        }
    baseline_provider_count = sum(len(providers) for providers in resolved_baseline.values())
    supported_provider_count = sum(category["supported_count"] for category in categories.values())
    adapter_needed_count = sum(category["adapter_needed_count"] for category in categories.values())
    return {
        "schema_version": "mem1-provider-parity-v1",
        "source": source,
        "ref": ref or BASELINE_REF,
        "expected_count": baseline_provider_count,
        "supported_count": supported_provider_count,
        "adapter_needed_count": adapter_needed_count,
        "missing_count": adapter_needed_count,
        "ok": adapter_needed_count == 0,
        "baseline": {
            "source": source,
            "ref": ref or BASELINE_REF,
            "method": "provider module files under mem0/llms, embeddings, vector_stores, graphs, reranker",
        },
        "categories": categories,
        "summary": {
            "baseline_provider_count": baseline_provider_count,
            "supported_provider_count": supported_provider_count,
            "adapter_needed_count": adapter_needed_count,
        },
    }
