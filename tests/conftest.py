from __future__ import annotations

import importlib.util
import asyncio
import os
import sys

# Tests pin the deterministic embedding stack for reproducibility: with
# semantic-by-default (2026-08-01), an installed fastembed would otherwise
# make similarity rankings — and thus consolidation/supersede choices —
# model-dependent. Embedding-behavior tests override this explicitly.
os.environ.setdefault("MEM1_EMBEDDING_PROVIDER", "local")
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if SERVER_DIR.exists() and str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


OPTIONAL_TEST_MODULES = {
    "tests/embeddings/test_azure_openai_embeddings.py": ("azure.identity",),
    "tests/embeddings/test_gemini_emeddings.py": ("google.genai",),
    "tests/embeddings/test_huggingface_embeddings.py": ("openai", "sentence_transformers"),
    "tests/embeddings/test_lm_studio_embeddings.py": ("openai",),
    "tests/embeddings/test_ollama_embeddings.py": ("ollama",),
    "tests/embeddings/test_openai_embeddings.py": ("openai",),
    "tests/embeddings/test_vertexai_embeddings.py": ("vertexai",),
    "tests/llms/test_anthropic.py": ("anthropic",),
    "tests/llms/test_aws_bedrock.py": ("boto3",),
    "tests/llms/test_azure_openai.py": ("azure.identity",),
    "tests/llms/test_azure_openai_structured.py": ("azure.identity",),
    "tests/llms/test_deepseek.py": ("openai",),
    "tests/llms/test_gemini.py": ("google.genai",),
    "tests/llms/test_groq.py": ("groq",),
    "tests/llms/test_litellm.py": ("litellm",),
    "tests/llms/test_lm_studio.py": ("openai",),
    "tests/llms/test_minimax.py": ("openai",),
    "tests/llms/test_ollama.py": ("ollama",),
    "tests/llms/test_openai.py": ("openai",),
    "tests/llms/test_openai_structured.py": ("openai",),
    "tests/llms/test_sarvam.py": ("openai",),
    "tests/llms/test_together.py": ("together",),
    "tests/llms/test_vllm.py": ("openai",),
    "tests/llms/test_xai.py": ("openai",),
    "tests/test_main.py": ("openai",),
    "tests/test_proxy.py": ("litellm", "openai"),
    "tests/test_server_auth.py": ("sqlalchemy", "slowapi"),
    "tests/test_server_default_config.py": ("sqlalchemy", "slowapi"),
    "tests/test_server_params.py": ("sqlalchemy", "slowapi"),
    "tests/vector_stores/test_azure_ai_search.py": ("azure.search.documents",),
    "tests/vector_stores/test_azure_mysql.py": ("pymysql", "dbutils"),
    "tests/vector_stores/test_baidu.py": ("pymochow",),
    "tests/vector_stores/test_cassandra.py": ("cassandra",),
    "tests/vector_stores/test_chroma.py": ("chromadb",),
    "tests/vector_stores/test_e2e_threshold.py": ("chromadb", "faiss"),
    "tests/vector_stores/test_databricks.py": ("databricks",),
    "tests/vector_stores/test_elasticsearch.py": ("elasticsearch",),
    "tests/vector_stores/test_faiss.py": ("faiss",),
    "tests/vector_stores/test_langchain_vector_store.py": ("langchain_community",),
    "tests/vector_stores/test_milvus.py": ("pymilvus",),
    "tests/vector_stores/test_mongodb.py": ("pymongo",),
    "tests/vector_stores/test_neptune_analytics.py": ("langchain_aws",),
    "tests/vector_stores/test_opensearch.py": ("opensearchpy",),
    "tests/vector_stores/test_pgvector.py": ("psycopg",),
    "tests/vector_stores/test_pinecone.py": ("pinecone", "pinecone_text"),
    "tests/vector_stores/test_qdrant.py": ("qdrant_client",),
    "tests/vector_stores/test_qdrant_config.py": ("qdrant_client",),
    "tests/vector_stores/test_redis.py": ("redis", "pytz"),
    "tests/vector_stores/test_s3_vectors.py": ("boto3", "botocore"),
    "tests/vector_stores/test_score_normalization.py": ("qdrant_client",),
    "tests/vector_stores/test_supabase.py": ("vecs",),
    "tests/vector_stores/test_turbopuffer.py": ("turbopuffer",),
    "tests/vector_stores/test_upstash_vector.py": ("upstash_vector",),
    "tests/vector_stores/test_valkey.py": ("valkey", "pytz"),
    "tests/vector_stores/test_vertex_ai_vector_search.py": ("google.api_core", "google.cloud.aiplatform"),
    "tests/vector_stores/test_weaviate.py": ("weaviate",),
}


def pytest_ignore_collect(collection_path, config):
    root = Path(str(config.rootpath))
    try:
        relative = Path(str(collection_path)).resolve().relative_to(root).as_posix()
    except ValueError:
        return False
    required = OPTIONAL_TEST_MODULES.get(relative)
    return bool(required and any(not _has_module(module) for module in required))


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: run coroutine tests with the local asyncio shim")


@pytest.fixture
def mocker():
    patches = []

    def _patch(*args, **kwargs):
        patcher = mock.patch(*args, **kwargs)
        patches.append(patcher)
        return patcher.start()

    def _patch_object(*args, **kwargs):
        patcher = mock.patch.object(*args, **kwargs)
        patches.append(patcher)
        return patcher.start()

    _patch.object = _patch_object
    api = SimpleNamespace(
        patch=_patch,
        MagicMock=mock.MagicMock,
        Mock=mock.Mock,
        AsyncMock=mock.AsyncMock,
        call=mock.call,
        ANY=mock.ANY,
    )
    try:
        yield api
    finally:
        for patcher in reversed(patches):
            patcher.stop()


def pytest_pyfunc_call(pyfuncitem):
    if "asyncio" not in pyfuncitem.keywords:
        return None
    testfunction = pyfuncitem.obj
    if not asyncio.iscoroutinefunction(testfunction):
        return None
    kwargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
    asyncio.run(testfunction(**kwargs))
    return True
