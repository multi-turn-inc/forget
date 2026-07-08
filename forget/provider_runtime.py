from __future__ import annotations

import importlib.util
import os
from typing import Any

from .db import current_db_path
from .provider_matrix import MEM0_PROVIDER_BASELINE, MEM1_PROVIDER_STATUS
from .providers import get_project_settings, update_project_settings


SUPPORTED_STATUSES = {"native", "native_alias", "compatible_endpoint"}
SECRET_KEYS = {"api_key", "token", "secret", "password"}

PROVIDER_SETTINGS: dict[str, dict[str, dict[str, Any]]] = {
    "llms": {
        "local": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "rule-extractor",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "local",
        },
        "anthropic": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "claude-haiku-4-5",
            "credential_env": "ANTHROPIC_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.anthropic.com/v1",
            "stored_provider": "anthropic",
        },
        "aws_bedrock": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "anthropic.claude-3-5-sonnet-20240620-v1:0",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "aws_bedrock",
            "optional_dependency": "boto3",
        },
        "azure_openai": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "gpt-5-mini",
            "credential_env": "LLM_AZURE_OPENAI_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "",
            "stored_provider": "azure_openai",
            "url_required": True,
        },
        "azure_openai_structured": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "gpt-5-mini",
            "credential_env": "LLM_AZURE_OPENAI_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "",
            "stored_provider": "azure_openai_structured",
            "url_required": True,
        },
        "openai": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "gpt-5.5",
            "credential_env": "MEM1_LLM_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.openai.com/v1",
            "stored_provider": "openai",
        },
        "openai_compatible": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "gpt-5.5",
            "credential_env": "MEM1_LLM_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.openai.com/v1",
            "stored_provider": "openai_compatible",
        },
        "openai_structured": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "gpt-5.5",
            "credential_env": "MEM1_LLM_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.openai.com/v1",
            "stored_provider": "openai",
        },
        "deepseek": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "deepseek-chat",
            "credential_env": "DEEPSEEK_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.deepseek.com/v1",
            "stored_provider": "deepseek",
        },
        "gemini": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "gemini-2.0-flash",
            "credential_env": "GEMINI_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
            "stored_provider": "gemini",
        },
        "groq": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "llama-3.3-70b-versatile",
            "credential_env": "GROQ_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.groq.com/openai/v1",
            "stored_provider": "groq",
        },
        "lmstudio": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "local-model",
            "credential_env": "LMSTUDIO_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "credential_optional": True,
            "base_url_setting": "llm_base_url",
            "default_base_url": "http://127.0.0.1:1234/v1",
            "stored_provider": "lmstudio",
        },
        "litellm": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "gpt-4o-mini",
            "credential_env": "LITELLM_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "credential_optional": True,
            "base_url_setting": "llm_base_url",
            "default_base_url": "http://127.0.0.1:4000/v1",
            "stored_provider": "litellm",
        },
        "minimax": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "MiniMax-M2.7",
            "credential_env": "MINIMAX_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.minimax.io/v1",
            "stored_provider": "minimax",
        },
        "ollama": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "llama3.1",
            "credential_env": "OLLAMA_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "credential_optional": True,
            "default_api_key": "ollama",
            "base_url_setting": "llm_base_url",
            "default_base_url": "http://127.0.0.1:11434/v1",
            "stored_provider": "ollama",
        },
        "sarvam": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "sarvam-m",
            "credential_env": "SARVAM_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.sarvam.ai/v1",
            "stored_provider": "sarvam",
        },
        "together": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "credential_env": "TOGETHER_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.together.xyz/v1",
            "stored_provider": "together",
        },
        "vllm": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "local-model",
            "credential_env": "VLLM_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "credential_optional": True,
            "base_url_setting": "llm_base_url",
            "default_base_url": "http://127.0.0.1:8001/v1",
            "stored_provider": "vllm",
        },
        "xai": {
            "provider_setting": "llm_provider",
            "model_setting": "llm_model",
            "default_model": "grok-3-mini",
            "credential_env": "XAI_API_KEY",
            "credential_env_setting": "llm_api_key_env",
            "base_url_setting": "llm_base_url",
            "default_base_url": "https://api.x.ai/v1",
            "stored_provider": "xai",
        },
    },
    "embeddings": {
        "local": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "deterministic-128",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "local",
        },
        "mock": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "deterministic-128",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "local",
        },
        "openai": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "text-embedding-3-small",
            "credential_env": "MEM1_EMBEDDING_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "base_url_setting": "embedding_base_url",
            "default_base_url": "https://api.openai.com/v1",
            "stored_provider": "openai",
        },
        "openai_compatible": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "text-embedding-3-small",
            "credential_env": "MEM1_EMBEDDING_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "base_url_setting": "embedding_base_url",
            "default_base_url": "https://api.openai.com/v1",
            "stored_provider": "openai_compatible",
        },
        "aws_bedrock": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "amazon.titan-embed-text-v1",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "aws_bedrock",
            "optional_dependency": "boto3",
        },
        "azure_openai": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "text-embedding-3-small",
            "credential_env": "EMBEDDING_AZURE_OPENAI_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "base_url_setting": "embedding_base_url",
            "default_base_url": "",
            "stored_provider": "azure_openai",
            "url_required": True,
        },
        "fastembed": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "thenlper/gte-large",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "fastembed",
            "optional_dependency": "fastembed",
        },
        "gemini": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "gemini-embedding-001",
            "credential_env": "GEMINI_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "base_url_setting": "embedding_base_url",
            "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
            "stored_provider": "gemini",
        },
        "huggingface": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "multi-qa-MiniLM-L6-cos-v1",
            "credential_env": "HUGGINGFACE_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "credential_optional": True,
            "base_url_setting": "embedding_base_url",
            "default_base_url": "",
            "stored_provider": "huggingface",
        },
        "lmstudio": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "local-embedding-model",
            "credential_env": "LMSTUDIO_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "credential_optional": True,
            "base_url_setting": "embedding_base_url",
            "default_base_url": "http://127.0.0.1:1234/v1",
            "stored_provider": "lmstudio",
        },
        "ollama": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "nomic-embed-text",
            "credential_env": "OLLAMA_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "credential_optional": True,
            "default_api_key": "ollama",
            "base_url_setting": "embedding_base_url",
            "default_base_url": "http://127.0.0.1:11434/v1",
            "stored_provider": "ollama",
        },
        "together": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "togethercomputer/m2-bert-80M-8k-retrieval",
            "credential_env": "TOGETHER_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "base_url_setting": "embedding_base_url",
            "default_base_url": "https://api.together.xyz/v1",
            "stored_provider": "together",
        },
        "vllm": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "local-embedding-model",
            "credential_env": "VLLM_API_KEY",
            "credential_env_setting": "embedding_api_key_env",
            "credential_optional": True,
            "base_url_setting": "embedding_base_url",
            "default_base_url": "http://127.0.0.1:8001/v1",
            "stored_provider": "vllm",
        },
        "vertexai": {
            "provider_setting": "embedding_provider",
            "model_setting": "embedding_model",
            "default_model": "gemini-embedding-001",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "vertexai",
            "optional_dependency": "vertexai",
        },
    },
    "vector_stores": {
        "sqlite": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "sqlite",
        },
        "qdrant": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "MEM1_QDRANT_API_KEY",
            "credential_env_setting": "vector_store_api_key_env",
            "credential_optional": True,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "qdrant",
            "url_required": True,
        },
        "s3_vectors": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "s3_vectors",
            "url_required": True,
            "optional_dependency": "boto3",
        },
        "redis": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "redis",
            "url_required": True,
            "optional_dependency": "redis",
        },
        "valkey": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "valkey",
            "url_required": True,
            "optional_dependency": "valkey",
        },
        "faiss": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "/tmp/mem1-faiss",
            "stored_provider": "faiss",
            "optional_dependency": "faiss",
        },
        "cassandra": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "MEM1_CASSANDRA_PASSWORD",
            "credential_env_setting": "vector_store_api_key_env",
            "credential_optional": True,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "cassandra",
            "url_required": True,
            "optional_dependency": "cassandra",
        },
        "azure_mysql": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "MEM1_AZURE_MYSQL_PASSWORD",
            "credential_env_setting": "vector_store_api_key_env",
            "credential_optional": True,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "azure_mysql",
            "url_required": True,
            "optional_dependency": "pymysql",
        },
        "baidu": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "MEM1_BAIDU_API_KEY",
            "credential_env_setting": "vector_store_api_key_env",
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "baidu",
            "url_required": True,
            "optional_dependency": "pymochow",
        },
        "neptune_analytics": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "neptune_analytics",
            "url_required": True,
            "optional_dependency": "langchain_aws",
        },
        "vertex_ai_vector_search": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "vertex_ai_vector_search",
            "url_required": True,
            "optional_dependency": "google.cloud.aiplatform",
        },
        "pgvector": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "pgvector",
            "url_required": True,
            "optional_dependency": "psycopg",
        },
        "supabase": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "supabase",
            "url_required": True,
            "optional_dependency": "psycopg",
        },
        "pinecone": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "PINECONE_API_KEY",
            "credential_env_setting": "vector_store_api_key_env",
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "pinecone",
            "url_required": True,
        },
        "upstash_vector": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "UPSTASH_VECTOR_REST_TOKEN",
            "credential_env_setting": "vector_store_api_key_env",
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "upstash_vector",
            "url_required": True,
        },
        "elasticsearch": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "ELASTICSEARCH_API_KEY",
            "credential_env_setting": "vector_store_api_key_env",
            "credential_optional": True,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "elasticsearch",
            "url_required": True,
        },
        "turbopuffer": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "TURBOPUFFER_API_KEY",
            "credential_env_setting": "vector_store_api_key_env",
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "turbopuffer",
            "url_required": True,
        },
        "opensearch": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "OPENSEARCH_AUTHORIZATION",
            "credential_env_setting": "vector_store_api_key_env",
            "credential_optional": True,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "opensearch",
            "url_required": True,
        },
        "weaviate": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "WEAVIATE_API_KEY",
            "credential_env_setting": "vector_store_api_key_env",
            "credential_optional": True,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "weaviate",
            "url_required": True,
        },
        "chroma": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "CHROMA_API_KEY",
            "credential_env_setting": "vector_store_api_key_env",
            "credential_optional": True,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "chroma",
            "url_required": True,
        },
        "milvus": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "MILVUS_TOKEN",
            "credential_env_setting": "vector_store_api_key_env",
            "credential_optional": True,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "milvus",
            "url_required": True,
        },
        "mongodb": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": None,
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "mongodb",
            "url_required": True,
            "optional_dependency": "pymongo",
        },
        "azure_ai_search": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "AZURE_SEARCH_API_KEY",
            "credential_env_setting": "vector_store_api_key_env",
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "azure_ai_search",
            "url_required": True,
        },
        "databricks": {
            "provider_setting": "vector_store",
            "model_setting": None,
            "credential_env": "DATABRICKS_TOKEN",
            "credential_env_setting": "vector_store_api_key_env",
            "base_url_setting": "vector_store_url",
            "default_base_url": "",
            "stored_provider": "databricks",
            "url_required": True,
        },
    },
    "graphs": {
        "disabled": {
            "provider_setting": "graph_enabled",
            "stored_provider": False,
            "credential_env": None,
            "base_url_setting": None,
        },
        "entity_links": {
            "provider_setting": "graph_enabled",
            "stored_provider": True,
            "credential_env": None,
            "base_url_setting": None,
        },
    },
    "rerankers": {
        "cohere_reranker": {
            "provider_setting": "reranker_provider",
            "model_setting": "reranker_model",
            "default_model": "rerank-v4.0-pro",
            "credential_env": "COHERE_API_KEY",
            "credential_env_setting": "reranker_api_key_env",
            "base_url_setting": "reranker_base_url",
            "default_base_url": "https://api.cohere.com/v2",
            "stored_provider": "cohere_reranker",
        },
        "huggingface_reranker": {
            "provider_setting": "reranker_provider",
            "model_setting": "reranker_model",
            "default_model": "BAAI/bge-reranker-base",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "huggingface_reranker",
            "optional_dependency": "transformers",
        },
        "llm_reranker": {
            "provider_setting": "reranker_provider",
            "model_setting": "reranker_model",
            "default_model": "gpt-4o-mini",
            "credential_env": "MEM1_RERANKER_API_KEY",
            "credential_env_setting": "reranker_api_key_env",
            "base_url_setting": "reranker_base_url",
            "default_base_url": "https://api.openai.com/v1",
            "stored_provider": "llm_reranker",
        },
        "local": {
            "provider_setting": "reranker_provider",
            "model_setting": "reranker_model",
            "default_model": "lexical-v1",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "local",
        },
        "sentence_transformer_reranker": {
            "provider_setting": "reranker_provider",
            "model_setting": "reranker_model",
            "default_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "credential_env": None,
            "base_url_setting": None,
            "stored_provider": "sentence_transformer_reranker",
            "optional_dependency": "sentence_transformers",
        },
        "zero_entropy_reranker": {
            "provider_setting": "reranker_provider",
            "model_setting": "reranker_model",
            "default_model": "zerank-1",
            "credential_env": "ZERO_ENTROPY_API_KEY",
            "credential_env_setting": "reranker_api_key_env",
            "base_url_setting": None,
            "stored_provider": "zero_entropy_reranker",
            "optional_dependency": "zeroentropy",
        },
    },
}


def _matrix_entry(category: str, provider: str) -> dict[str, str]:
    if category == "graphs" and provider == "disabled":
        return {"provider": provider, "status": "native_alias", "notes": "Graph memory is disabled for this project."}
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
        "notes": "Public Mem0 provider module exists; Mem1 currently needs a provider adapter before claiming parity.",
    }


def _safe_settings(settings: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in settings.items():
        lowered = str(key).lower()
        if (
            any(secret in lowered for secret in SECRET_KEYS)
            and not lowered.endswith("_api_key_env")
            and not lowered.endswith("_api_key_required")
        ):
            safe[key] = "***redacted***"
        else:
            safe[key] = value
    return safe


def _active_provider(category: str, settings: dict[str, Any]) -> str:
    if category == "llms":
        return str(settings.get("llm_provider") or "local")
    if category == "embeddings":
        return str(settings.get("embedding_provider") or "local")
    if category == "vector_stores":
        return str(settings.get("vector_store") or "sqlite")
    if category == "graphs":
        return "entity_links" if settings.get("graph_enabled") else "disabled"
    if category == "rerankers":
        return str(settings.get("reranker_provider") or "local")
    return "unknown"


def _option_payload(category: str, provider: str, settings: dict[str, Any]) -> dict[str, Any]:
    entry = _matrix_entry(category, provider)
    runtime = PROVIDER_SETTINGS.get(category, {}).get(provider)
    active = _active_provider(category, settings) == provider
    payload: dict[str, Any] = {
        **entry,
        "active": active,
        "configurable": bool(runtime and entry["status"] in SUPPORTED_STATUSES),
    }
    if runtime:
        option_settings = {
            key: value
            for key, value in {
                "provider_setting": runtime.get("provider_setting"),
                "model_setting": runtime.get("model_setting"),
                "base_url_setting": runtime.get("base_url_setting"),
                "credential_env_setting": runtime.get("credential_env_setting"),
                "credential_env": runtime.get("credential_env"),
                "default_model": runtime.get("default_model"),
                "default_base_url": runtime.get("default_base_url"),
                "optional_dependency": runtime.get("optional_dependency"),
            }.items()
            if value is not None
        }
        fallback_env = _runtime_credential_fallback_envs(runtime)
        if fallback_env:
            option_settings["fallback_credential_env"] = fallback_env
        payload["settings"] = option_settings
    return payload


def provider_catalog_payload(project_id: str = "proj_local") -> dict[str, Any]:
    settings = get_project_settings(project_id)
    categories: dict[str, Any] = {}
    category_names = sorted(set(MEM0_PROVIDER_BASELINE) | set(PROVIDER_SETTINGS) | set(MEM1_PROVIDER_STATUS))
    for category in category_names:
        baseline = list(MEM0_PROVIDER_BASELINE.get(category, []))
        known = sorted(set(baseline) | set(PROVIDER_SETTINGS.get(category, {})) | set(MEM1_PROVIDER_STATUS.get(category, {})))
        options = [_option_payload(category, provider, settings) for provider in known]
        categories[category] = {
            "active_provider": _active_provider(category, settings),
            "baseline_count": len(baseline),
            "option_count": len(options),
            "configurable_count": len([option for option in options if option["configurable"]]),
            "adapter_needed_count": len([option for option in options if option["status"] == "adapter_needed"]),
            "options": options,
        }
    return {
        "schema_version": "mem1-provider-catalog-v1",
        "project_id": project_id,
        "settings": _safe_settings(settings),
        "categories": categories,
    }


def _runtime_credential_fallback_envs(runtime: dict[str, Any]) -> list[str]:
    env_setting = runtime.get("credential_env_setting")
    stored_provider = str(runtime.get("stored_provider") or "").lower()
    if env_setting in {"llm_api_key_env", "embedding_api_key_env"} and stored_provider == "openai":
        return ["OPENAI_API_KEY"]
    return []


def _credential_env_candidates(runtime: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    default_env = runtime.get("credential_env")
    env_setting = runtime.get("credential_env_setting")
    env_name = str(settings.get(env_setting) or default_env or "") if (default_env or env_setting) else ""
    candidates = [env_name] if env_name else []
    provider_setting = runtime.get("provider_setting")
    active_provider = (
        str(settings.get(provider_setting) or runtime.get("stored_provider") or "").lower() if provider_setting else ""
    )
    if active_provider == "openai":
        for fallback_env in _runtime_credential_fallback_envs(runtime):
            if fallback_env not in candidates:
                candidates.append(fallback_env)
    return candidates


def _credential_state(runtime: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    candidates = _credential_env_candidates(runtime, settings)
    env_name = candidates[0] if candidates else ""
    if not env_name:
        return {"required": False, "ok": True}
    present_env = next((candidate for candidate in candidates if os.getenv(candidate)), "")
    if runtime.get("credential_optional"):
        return {
            "required": False,
            "env": env_name,
            "fallback_env": [candidate for candidate in candidates[1:]],
            "present_env": present_env,
            "present": bool(present_env),
            "ok": True,
        }
    return {
        "required": True,
        "env": env_name,
        "fallback_env": [candidate for candidate in candidates[1:]],
        "present_env": present_env,
        "present": bool(present_env),
        "ok": bool(present_env),
    }


def _health_check(category: str, settings: dict[str, Any]) -> dict[str, Any]:
    provider = _active_provider(category, settings)
    entry = _matrix_entry(category, provider)
    runtime = PROVIDER_SETTINGS.get(category, {}).get(provider)
    if provider == "disabled":
        return {
            "category": category,
            "provider": provider,
            "provider_status": "disabled",
            "status": "disabled",
            "ready": True,
            "issues": [],
        }
    if not runtime:
        return {
            "category": category,
            "provider": provider,
            "provider_status": entry["status"],
            "status": "adapter_needed",
            "ready": False,
            "issues": [f"{category}.{provider} is not implemented as a Mem1 runtime adapter"],
        }
    credential = _credential_state(runtime, settings)
    issues: list[str] = []
    if entry["status"] not in SUPPORTED_STATUSES:
        issues.append(f"{category}.{provider} is tracked as {entry['status']}")
    if not credential["ok"]:
        issues.append(f"missing credential env {credential['env']}")
    dependency = runtime.get("optional_dependency")
    if dependency and importlib.util.find_spec(str(dependency)) is None:
        issues.append(f"missing optional dependency {dependency}")
    details: dict[str, Any] = {
        "category": category,
        "provider": provider,
        "provider_status": entry["status"],
        "credential": credential,
        "ready": not issues,
        "issues": issues,
    }
    model_setting = runtime.get("model_setting")
    if model_setting:
        details["model"] = settings.get(model_setting) or runtime.get("default_model")
    base_url_setting = runtime.get("base_url_setting")
    if base_url_setting:
        details["base_url"] = settings.get(base_url_setting) or runtime.get("default_base_url")
        if runtime.get("url_required") and not details["base_url"]:
            issues.append(f"missing {base_url_setting}")
    if category == "vector_stores" and provider == "sqlite":
        db_path = current_db_path()
        details["db_path"] = str(db_path)
        details["db_parent_exists"] = db_path.parent.exists()
    details["ready"] = not issues
    details["issues"] = issues
    details["status"] = "ok" if not issues else "blocked"
    return details


def provider_health_payload(project_id: str = "proj_local") -> dict[str, Any]:
    settings = get_project_settings(project_id)
    checks = {category: _health_check(category, settings) for category in ("llms", "embeddings", "vector_stores", "graphs", "rerankers")}
    ready = all(check["ready"] for check in checks.values())
    return {
        "schema_version": "mem1-provider-health-v1",
        "project_id": project_id,
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "checks": checks,
    }


def _provider_updates(category: str, provider: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime = PROVIDER_SETTINGS.get(category, {}).get(provider)
    entry = _matrix_entry(category, provider)
    if not runtime or entry["status"] not in SUPPORTED_STATUSES:
        return {}, {
            "configurable": False,
            "provider_status": entry["status"],
            "reason": f"{category}.{provider} is not configurable until an adapter is implemented",
        }

    updates: dict[str, Any] = {str(runtime["provider_setting"]): runtime["stored_provider"]}
    model_setting = runtime.get("model_setting")
    model = payload.get("model") or payload.get("model_id")
    if model_setting:
        updates[str(model_setting)] = model or runtime.get("default_model")
    base_url_setting = runtime.get("base_url_setting")
    if base_url_setting and payload.get("base_url"):
        updates[str(base_url_setting)] = str(payload["base_url"]).rstrip("/")
    credential_env_setting = runtime.get("credential_env_setting")
    if credential_env_setting:
        updates[str(credential_env_setting)] = payload.get("api_key_env") or runtime.get("credential_env")
    if category == "llms":
        updates["llm_api_key_required"] = not bool(runtime.get("credential_optional"))
        updates["llm_default_api_key"] = runtime.get("default_api_key") or ""
        if runtime.get("default_base_url") and not payload.get("base_url"):
            updates["llm_base_url"] = runtime["default_base_url"]
    if category == "embeddings":
        updates["embedding_api_key_required"] = not bool(runtime.get("credential_optional"))
        updates["embedding_default_api_key"] = runtime.get("default_api_key") or ""
        if runtime.get("default_base_url") and not payload.get("base_url"):
            updates["embedding_base_url"] = runtime["default_base_url"]
    if category == "rerankers":
        updates["reranker_api_key_required"] = not bool(runtime.get("credential_optional"))
        if runtime.get("default_base_url") and not payload.get("base_url"):
            updates["reranker_base_url"] = runtime["default_base_url"]
    if category == "vector_stores" and provider in {
        "qdrant",
        "s3_vectors",
        "redis",
        "valkey",
        "faiss",
        "cassandra",
        "azure_mysql",
        "baidu",
        "neptune_analytics",
        "vertex_ai_vector_search",
        "pgvector",
        "supabase",
        "pinecone",
        "upstash_vector",
        "elasticsearch",
        "turbopuffer",
        "opensearch",
        "weaviate",
        "chroma",
        "milvus",
        "mongodb",
        "azure_ai_search",
        "databricks",
    }:
        if payload.get("collection"):
            updates["vector_store_collection"] = str(payload["collection"])
        if payload.get("timeout") is not None:
            updates["vector_store_timeout"] = payload["timeout"]
        if payload.get("strict") is not None:
            updates["vector_store_strict"] = bool(payload["strict"])
        if payload.get("auto_create") is not None:
            updates["vector_store_auto_create"] = bool(payload["auto_create"])
        if payload.get("dimensions") is not None:
            updates["vector_store_dimensions"] = payload["dimensions"]
    return updates, {"configurable": True, "provider_status": entry["status"]}


def configure_provider_payload(payload: dict[str, Any], project_id: str = "proj_local") -> dict[str, Any]:
    category = str(payload.get("category") or "").strip().lower()
    provider = str(payload.get("provider") or "").strip().lower()
    if not category or not provider:
        return {
            "schema_version": "mem1-provider-configure-v1",
            "project_id": project_id,
            "applied": False,
            "configurable": False,
            "reason": "category and provider are required",
        }

    current = get_project_settings(project_id)
    updates, status = _provider_updates(category, provider, payload)
    apply = bool(payload.get("apply", False))
    if apply and not status["configurable"]:
        return {
            "schema_version": "mem1-provider-configure-v1",
            "project_id": project_id,
            "category": category,
            "provider": provider,
            "applied": False,
            **status,
        }
    preview = {**current, **updates}
    result: dict[str, Any] = {
        "schema_version": "mem1-provider-configure-v1",
        "project_id": project_id,
        "category": category,
        "provider": provider,
        "applied": False,
        "updates": _safe_settings(updates),
        "settings_preview": _safe_settings(preview),
        **status,
    }
    if apply and status["configurable"]:
        result["applied"] = True
        result["settings"] = _safe_settings(update_project_settings(project_id, updates))
    return result
