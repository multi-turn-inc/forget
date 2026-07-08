from __future__ import annotations

import importlib
import json
import os
import re
import struct
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from fastapi import HTTPException

from .db import json_dumps
from .providers import get_project_settings


def _bool_setting(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _float_setting(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_setting(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _qdrant_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    api_key_env = str(settings.get("vector_store_api_key_env") or "MEM1_QDRANT_API_KEY")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("MEM1_QDRANT_URL") or "").rstrip("/"),
        "collection": str(settings.get("vector_store_collection") or os.getenv("MEM1_QDRANT_COLLECTION") or "mem1_memories"),
        "api_key": os.getenv(api_key_env),
        "api_key_env": api_key_env,
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "distance": str(settings.get("vector_store_distance") or "Cosine"),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
    }


def _s3_vectors_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "bucket": str(settings.get("vector_store_url") or os.getenv("MEM1_S3_VECTORS_BUCKET") or ""),
        "index": str(settings.get("vector_store_collection") or os.getenv("MEM1_S3_VECTORS_INDEX") or "mem1_memories"),
        "region": os.getenv("MEM1_S3_VECTORS_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
        "distance": str(settings.get("vector_store_distance") or "cosine").lower(),
    }


def _redis_like_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    provider = str(settings.get("vector_store") or "sqlite").lower()
    if provider == "valkey":
        url = settings.get("vector_store_url") or os.getenv("MEM1_VALKEY_URL") or os.getenv("VALKEY_URL") or ""
        index_env = os.getenv("MEM1_VALKEY_INDEX")
    else:
        url = settings.get("vector_store_url") or os.getenv("MEM1_REDIS_URL") or os.getenv("REDIS_URL") or ""
        index_env = os.getenv("MEM1_REDIS_INDEX")
    index = str(settings.get("vector_store_collection") or index_env or "mem1_memories")
    return {
        "provider": provider,
        "url": str(url).rstrip("/"),
        "index": index,
        "prefix": f"mem0:{index}",
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
        "distance": str(settings.get("vector_store_distance") or "COSINE").upper(),
    }


def _faiss_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "path": str(settings.get("vector_store_url") or os.getenv("MEM1_FAISS_PATH") or "/tmp/mem1-faiss"),
        "collection": str(settings.get("vector_store_collection") or os.getenv("MEM1_FAISS_COLLECTION") or "mem1_memories"),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
        "distance": str(settings.get("vector_store_distance") or "cosine").lower(),
    }


def _cassandra_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    raw_url = str(settings.get("vector_store_url") or os.getenv("MEM1_CASSANDRA_CONTACT_POINTS") or "")
    parsed = urlparse(raw_url if "://" in raw_url else "")
    contact_points = [item.strip() for item in raw_url.split(",") if item.strip()] if not parsed.scheme else []
    if parsed.hostname:
        contact_points = [parsed.hostname]
    keyspace = (parsed.path or "").strip("/") if parsed.scheme else ""
    password_env = str(settings.get("vector_store_api_key_env") or "MEM1_CASSANDRA_PASSWORD")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "contact_points": contact_points,
        "port": parsed.port or _int_setting(os.getenv("MEM1_CASSANDRA_PORT"), 9042),
        "username": os.getenv("MEM1_CASSANDRA_USERNAME") or parsed.username,
        "password": os.getenv(password_env) or parsed.password,
        "password_env": password_env,
        "keyspace": os.getenv("MEM1_CASSANDRA_KEYSPACE") or keyspace or "mem1",
        "table": str(settings.get("vector_store_collection") or os.getenv("MEM1_CASSANDRA_TABLE") or "mem1_memories"),
        "secure_connect_bundle": os.getenv("MEM1_CASSANDRA_SECURE_CONNECT_BUNDLE") or "",
        "protocol_version": _int_setting(os.getenv("MEM1_CASSANDRA_PROTOCOL_VERSION"), 4),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
    }


def _azure_mysql_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    raw_url = str(settings.get("vector_store_url") or os.getenv("MEM1_AZURE_MYSQL_URL") or "")
    parsed = urlparse(raw_url if "://" in raw_url else "")
    password_env = str(settings.get("vector_store_api_key_env") or "MEM1_AZURE_MYSQL_PASSWORD")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "host": parsed.hostname or raw_url,
        "port": parsed.port or _int_setting(os.getenv("MEM1_AZURE_MYSQL_PORT"), 3306),
        "user": os.getenv("MEM1_AZURE_MYSQL_USER") or parsed.username or "",
        "password": os.getenv(password_env) or parsed.password,
        "password_env": password_env,
        "database": os.getenv("MEM1_AZURE_MYSQL_DATABASE") or (parsed.path or "").strip("/") or "mem1",
        "table": str(settings.get("vector_store_collection") or os.getenv("MEM1_AZURE_MYSQL_TABLE") or "mem1_memories"),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
    }


def _baidu_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    api_key_env = str(settings.get("vector_store_api_key_env") or "MEM1_BAIDU_API_KEY")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("MEM1_BAIDU_ENDPOINT") or "").rstrip("/"),
        "account": os.getenv("MEM1_BAIDU_ACCOUNT") or "",
        "api_key": os.getenv(api_key_env),
        "api_key_env": api_key_env,
        "database": os.getenv("MEM1_BAIDU_DATABASE") or "mem1",
        "table": str(settings.get("vector_store_collection") or os.getenv("MEM1_BAIDU_TABLE") or "mem1_memories"),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
    }


def _neptune_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "endpoint": str(
            settings.get("vector_store_url") or os.getenv("MEM1_NEPTUNE_ANALYTICS_ENDPOINT") or ""
        ),
        "collection": str(
            settings.get("vector_store_collection")
            or os.getenv("MEM1_NEPTUNE_ANALYTICS_COLLECTION")
            or "mem1_memories"
        ),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
    }


def _vertex_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "api_endpoint": str(settings.get("vector_store_url") or os.getenv("MEM1_VERTEX_VECTOR_SEARCH_API_ENDPOINT") or ""),
        "project_id": os.getenv("MEM1_VERTEX_PROJECT_ID") or "",
        "project_number": os.getenv("MEM1_VERTEX_PROJECT_NUMBER") or "",
        "region": os.getenv("MEM1_VERTEX_REGION") or "us-central1",
        "endpoint_id": os.getenv("MEM1_VERTEX_ENDPOINT_ID") or "",
        "index_id": os.getenv("MEM1_VERTEX_INDEX_ID") or "",
        "deployment_index_id": (
            os.getenv("MEM1_VERTEX_DEPLOYMENT_INDEX_ID")
            or str(settings.get("vector_store_collection") or "mem1_memories")
        ),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
    }


def _pgvector_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    provider = str(settings.get("vector_store") or "sqlite").lower()
    default_url = os.getenv("MEM1_PGVECTOR_URL") or ""
    default_table = os.getenv("MEM1_PGVECTOR_TABLE") or "mem1_memories"
    if provider == "supabase":
        default_url = (
            os.getenv("SUPABASE_DB_URL")
            or os.getenv("SUPABASE_POSTGRES_URL")
            or os.getenv("MEM1_SUPABASE_URL")
            or ""
        )
        default_table = os.getenv("MEM1_SUPABASE_TABLE") or "mem1_memories"
    return {
        "provider": provider,
        "url": str(settings.get("vector_store_url") or default_url).strip(),
        "table": _pg_identifier(str(settings.get("vector_store_collection") or default_table)),
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
    }


def _pinecone_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    api_key_env = str(settings.get("vector_store_api_key_env") or "PINECONE_API_KEY")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("MEM1_PINECONE_HOST") or "").rstrip("/"),
        "namespace": str(settings.get("vector_store_collection") or os.getenv("MEM1_PINECONE_NAMESPACE") or "mem1_memories"),
        "api_key": os.getenv(api_key_env),
        "api_key_env": api_key_env,
        "api_version": str(settings.get("vector_store_api_version") or os.getenv("MEM1_PINECONE_API_VERSION") or "2025-10"),
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
    }


def _upstash_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    token_env = str(settings.get("vector_store_api_key_env") or "UPSTASH_VECTOR_REST_TOKEN")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("UPSTASH_VECTOR_REST_URL") or "").rstrip("/"),
        "namespace": str(
            settings.get("vector_store_collection") or os.getenv("MEM1_UPSTASH_VECTOR_NAMESPACE") or "mem1_memories"
        ),
        "token": os.getenv(token_env),
        "token_env": token_env,
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
    }


def _elastic_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    api_key_env = str(settings.get("vector_store_api_key_env") or "ELASTICSEARCH_API_KEY")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("ELASTICSEARCH_URL") or "").rstrip("/"),
        "index": str(settings.get("vector_store_collection") or os.getenv("MEM1_ELASTICSEARCH_INDEX") or "mem1_memories"),
        "api_key": os.getenv(api_key_env),
        "api_key_env": api_key_env,
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
    }


def _turbopuffer_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    api_key_env = str(settings.get("vector_store_api_key_env") or "TURBOPUFFER_API_KEY")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("TURBOPUFFER_URL") or "").rstrip("/"),
        "namespace": str(
            settings.get("vector_store_collection") or os.getenv("MEM1_TURBOPUFFER_NAMESPACE") or "mem1_memories"
        ),
        "api_key": os.getenv(api_key_env),
        "api_key_env": api_key_env,
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
    }


def _opensearch_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    auth_env = str(settings.get("vector_store_api_key_env") or "OPENSEARCH_AUTHORIZATION")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("OPENSEARCH_URL") or "").rstrip("/"),
        "index": str(settings.get("vector_store_collection") or os.getenv("MEM1_OPENSEARCH_INDEX") or "mem1_memories"),
        "authorization": os.getenv(auth_env),
        "auth_env": auth_env,
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
    }


def _weaviate_class_name(value: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value or "") if part]
    class_name = "".join(part[:1].upper() + part[1:] for part in parts) or "Mem1Memories"
    if not class_name[0].isalpha():
        class_name = f"Mem1{class_name}"
    return class_name


def _weaviate_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    api_key_env = str(settings.get("vector_store_api_key_env") or "WEAVIATE_API_KEY")
    class_name = _weaviate_class_name(
        str(settings.get("vector_store_collection") or os.getenv("MEM1_WEAVIATE_CLASS") or "mem1_memories")
    )
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("WEAVIATE_URL") or "").rstrip("/"),
        "class_name": class_name,
        "api_key": os.getenv(api_key_env),
        "api_key_env": api_key_env,
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
    }


def _chroma_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    api_key_env = str(settings.get("vector_store_api_key_env") or "CHROMA_API_KEY")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("CHROMA_URL") or "").rstrip("/"),
        "collection": str(settings.get("vector_store_collection") or os.getenv("MEM1_CHROMA_COLLECTION") or "mem1_memories"),
        "api_key": os.getenv(api_key_env),
        "api_key_env": api_key_env,
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
    }


def _milvus_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    token_env = str(settings.get("vector_store_api_key_env") or "MILVUS_TOKEN")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("MILVUS_URL") or "").rstrip("/"),
        "collection": str(settings.get("vector_store_collection") or os.getenv("MEM1_MILVUS_COLLECTION") or "mem1_memories"),
        "token": os.getenv(token_env),
        "token_env": token_env,
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
    }


def _mongodb_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    collection = str(
        settings.get("vector_store_collection") or os.getenv("MEM1_MONGODB_COLLECTION") or "mem1_memories"
    )
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("MONGODB_URI") or os.getenv("MEM1_MONGODB_URI") or ""),
        "db": str(os.getenv("MEM1_MONGODB_DB") or "mem0_db"),
        "collection": collection,
        "index": str(os.getenv("MEM1_MONGODB_INDEX") or f"{collection}_vector_index"),
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
    }


def _azure_search_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    api_key_env = str(settings.get("vector_store_api_key_env") or "AZURE_SEARCH_API_KEY")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(settings.get("vector_store_url") or os.getenv("AZURE_SEARCH_ENDPOINT") or "").rstrip("/"),
        "index": str(settings.get("vector_store_collection") or os.getenv("MEM1_AZURE_SEARCH_INDEX") or "mem1_memories"),
        "api_key": os.getenv(api_key_env),
        "api_key_env": api_key_env,
        "api_version": str(
            settings.get("vector_store_api_version") or os.getenv("MEM1_AZURE_SEARCH_API_VERSION") or "2026-04-01"
        ),
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
    }


def _databricks_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    token_env = str(settings.get("vector_store_api_key_env") or "DATABRICKS_TOKEN")
    return {
        "provider": str(settings.get("vector_store") or "sqlite").lower(),
        "url": str(
            settings.get("vector_store_url")
            or os.getenv("DATABRICKS_HOST")
            or os.getenv("DATABRICKS_WORKSPACE_URL")
            or ""
        ).rstrip("/"),
        "index": str(
            settings.get("vector_store_collection")
            or os.getenv("MEM1_DATABRICKS_INDEX")
            or "main.default.mem1_memories"
        ),
        "token": os.getenv(token_env),
        "token_env": token_env,
        "endpoint_name": str(os.getenv("MEM1_DATABRICKS_ENDPOINT_NAME") or ""),
        "query_type": str(settings.get("vector_store_query_type") or os.getenv("MEM1_DATABRICKS_QUERY_TYPE") or "ANN"),
        "timeout": _float_setting(settings.get("vector_store_timeout"), 5.0),
        "strict": _bool_setting(settings.get("vector_store_strict"), False),
        "auto_create": _bool_setting(settings.get("vector_store_auto_create"), False),
        "dimensions": _int_setting(settings.get("vector_store_dimensions"), 128),
    }


def _enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "qdrant" and bool(settings["url"])


def _pgvector_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] in {"pgvector", "supabase"} and bool(settings["url"])


def _s3_vectors_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "s3_vectors" and bool(settings["bucket"])


def _redis_like_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] in {"redis", "valkey"} and bool(settings["url"])


def _faiss_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "faiss" and bool(settings["path"])


def _cassandra_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "cassandra" and (
        bool(settings["contact_points"]) or bool(settings["secure_connect_bundle"])
    )


def _azure_mysql_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "azure_mysql" and bool(settings["host"]) and bool(settings["database"])


def _baidu_enabled(settings: dict[str, Any]) -> bool:
    return (
        settings["provider"] == "baidu"
        and bool(settings["url"])
        and bool(settings["account"])
        and bool(settings["api_key"])
    )


def _neptune_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "neptune_analytics" and str(settings["endpoint"]).startswith("neptune-graph://")


def _vertex_enabled(settings: dict[str, Any]) -> bool:
    return (
        settings["provider"] == "vertex_ai_vector_search"
        and bool(settings["project_id"])
        and bool(settings["project_number"])
        and bool(settings["endpoint_id"])
        and bool(settings["index_id"])
    )


def _pinecone_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "pinecone" and bool(settings["url"]) and bool(settings["api_key"])


def _upstash_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "upstash_vector" and bool(settings["url"]) and bool(settings["token"])


def _elastic_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "elasticsearch" and bool(settings["url"])


def _turbopuffer_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "turbopuffer" and bool(settings["url"]) and bool(settings["api_key"])


def _opensearch_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "opensearch" and bool(settings["url"])


def _weaviate_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "weaviate" and bool(settings["url"])


def _chroma_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "chroma" and bool(settings["url"])


def _milvus_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "milvus" and bool(settings["url"])


def _mongodb_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "mongodb" and bool(settings["url"])


def _azure_search_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "azure_ai_search" and bool(settings["url"]) and bool(settings["api_key"])


def _databricks_enabled(settings: dict[str, Any]) -> bool:
    return settings["provider"] == "databricks" and bool(settings["url"]) and bool(settings["token"])


def _pg_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise HTTPException(status_code=400, detail=f"invalid pgvector table name: {value}")
    return f'"{value}"'


def _pg_vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _psycopg_module() -> Any:
    return importlib.import_module("psycopg")


def _boto3_module() -> Any:
    return importlib.import_module("boto3")


def _pymongo_module() -> Any:
    return importlib.import_module("pymongo")


def _pymongo_operations_module() -> Any:
    return importlib.import_module("pymongo.operations")


def _headers(settings: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.get("api_key"):
        headers["api-key"] = str(settings["api_key"])
    return headers


def _pinecone_headers(settings: dict[str, Any]) -> dict[str, str]:
    return {
        "Api-Key": str(settings["api_key"]),
        "Content-Type": "application/json",
        "X-Pinecone-Api-Version": str(settings["api_version"]),
    }


def _upstash_headers(settings: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings['token']}",
        "Content-Type": "application/json",
    }


def _elastic_headers(settings: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.get("api_key"):
        headers["Authorization"] = f"ApiKey {settings['api_key']}"
    return headers


def _turbopuffer_headers(settings: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }


def _opensearch_headers(settings: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    authorization = settings.get("authorization")
    if authorization:
        value = str(authorization)
        if not value.lower().startswith(("basic ", "bearer ", "apikey ")):
            value = f"Basic {value}"
        headers["Authorization"] = value
    return headers


def _weaviate_headers(settings: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.get("api_key"):
        headers["Authorization"] = f"Bearer {settings['api_key']}"
    return headers


def _chroma_headers(settings: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.get("api_key"):
        headers["Authorization"] = f"Bearer {settings['api_key']}"
    return headers


def _milvus_headers(settings: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.get("token"):
        headers["Authorization"] = f"Bearer {settings['token']}"
    return headers


def _azure_search_headers(settings: dict[str, Any]) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "api-key": str(settings["api_key"]),
    }


def _databricks_headers(settings: dict[str, Any]) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {settings['token']}",
        "Content-Type": "application/json",
    }


def _handle_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"qdrant {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "qdrant", "operation": operation, "error": str(exc)}


def _handle_pgvector_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    provider = str(settings.get("provider") or "pgvector")
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"{provider} {operation} failed: {exc}") from exc
    return {"ok": False, "provider": provider, "operation": operation, "error": str(exc)}


def _handle_s3_vectors_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"s3_vectors {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "s3_vectors", "operation": operation, "error": str(exc)}


def _handle_redis_like_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    provider = str(settings.get("provider") or "redis")
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"{provider} {operation} failed: {exc}") from exc
    return {"ok": False, "provider": provider, "operation": operation, "error": str(exc)}


def _handle_faiss_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"faiss {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "faiss", "operation": operation, "error": str(exc)}


def _handle_cassandra_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"cassandra {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "cassandra", "operation": operation, "error": str(exc)}


def _handle_azure_mysql_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"azure_mysql {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "azure_mysql", "operation": operation, "error": str(exc)}


def _handle_baidu_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"baidu {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "baidu", "operation": operation, "error": str(exc)}


def _handle_neptune_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"neptune_analytics {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "neptune_analytics", "operation": operation, "error": str(exc)}


def _handle_vertex_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"vertex_ai_vector_search {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "vertex_ai_vector_search", "operation": operation, "error": str(exc)}


def _handle_pinecone_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"pinecone {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "pinecone", "operation": operation, "error": str(exc)}


def _handle_upstash_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"upstash_vector {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "upstash_vector", "operation": operation, "error": str(exc)}


def _handle_elastic_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"elasticsearch {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "elasticsearch", "operation": operation, "error": str(exc)}


def _handle_turbopuffer_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"turbopuffer {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "turbopuffer", "operation": operation, "error": str(exc)}


def _handle_opensearch_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"opensearch {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "opensearch", "operation": operation, "error": str(exc)}


def _handle_weaviate_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"weaviate {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "weaviate", "operation": operation, "error": str(exc)}


def _handle_chroma_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"chroma {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "chroma", "operation": operation, "error": str(exc)}


def _handle_milvus_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"milvus {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "milvus", "operation": operation, "error": str(exc)}


def _handle_mongodb_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"mongodb {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "mongodb", "operation": operation, "error": str(exc)}


def _handle_azure_search_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"azure_ai_search {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "azure_ai_search", "operation": operation, "error": str(exc)}


def _handle_databricks_error(exc: Exception, settings: dict[str, Any], operation: str) -> dict[str, Any]:
    if settings.get("strict"):
        raise HTTPException(status_code=502, detail=f"databricks {operation} failed: {exc}") from exc
    return {"ok": False, "provider": "databricks", "operation": operation, "error": str(exc)}


def _ensure_collection(settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    size = dimensions or int(settings["dimensions"])
    with httpx.Client(timeout=float(settings["timeout"])) as client:
        response = client.put(
            f"{settings['url']}/collections/{settings['collection']}",
            headers=_headers(settings),
            json={"vectors": {"size": size, "distance": settings["distance"]}},
        )
    response.raise_for_status()


def _payload_filter(filters: dict[str, Any], project_id: str) -> dict[str, Any]:
    must: list[dict[str, Any]] = [{"key": "project_id", "match": {"value": project_id}}]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            must.append({"key": field, "match": {"value": value}})
    return {"must": must}


def _s3_vectors_client(settings: dict[str, Any]) -> Any:
    boto3 = _boto3_module()
    kwargs = {"region_name": settings["region"]} if settings.get("region") else {}
    return boto3.client("s3vectors", **kwargs)


def _s3_vectors_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", {})
    if isinstance(response, dict):
        error = response.get("Error", {})
        if isinstance(error, dict):
            return str(error.get("Code") or "")
    return ""


def _s3_vectors_ensure_index(client: Any, settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    try:
        client.get_vector_bucket(vectorBucketName=settings["bucket"])
    except Exception as exc:
        if _s3_vectors_error_code(exc) != "NotFoundException":
            raise
        client.create_vector_bucket(vectorBucketName=settings["bucket"])
    try:
        client.get_index(vectorBucketName=settings["bucket"], indexName=settings["index"])
    except Exception as exc:
        if _s3_vectors_error_code(exc) != "NotFoundException":
            raise
        client.create_index(
            vectorBucketName=settings["bucket"],
            indexName=settings["index"],
            dataType="float32",
            dimension=dimensions or int(settings["dimensions"]),
            distanceMetric=settings["distance"],
        )


def _s3_vectors_metadata(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    return _pinecone_metadata(memory, project_id)


def _s3_vectors_filter(filters: dict[str, Any], project_id: str) -> dict[str, Any]:
    s3_filter: dict[str, Any] = {"project_id": project_id}
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            s3_filter[field] = value
    return s3_filter


def _redis_like_module(settings: dict[str, Any]) -> Any:
    return importlib.import_module("valkey" if settings["provider"] == "valkey" else "redis")


def _redis_like_client(settings: dict[str, Any]) -> Any:
    module = _redis_like_module(settings)
    if settings["provider"] == "redis":
        return module.Redis.from_url(settings["url"], socket_timeout=settings["timeout"])
    return module.from_url(settings["url"], socket_timeout=settings["timeout"])


def _redis_like_vector_bytes(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *[float(value) for value in values])


def _redis_like_escape_tag(value: str) -> str:
    text = str(value)
    for char in ("\\", " ", ",", ".", "<", ">", "{", "}", "[", "]", '"', "'", ":", ";", "!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "-", "+", "=", "~", "|"):
        text = text.replace(char, f"\\{char}")
    return text


def _redis_like_filter(filters: dict[str, Any], project_id: str) -> str:
    clauses = [f"@project_id:{{{_redis_like_escape_tag(project_id)}}}"]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            clauses.append(f"@{field}:{{{_redis_like_escape_tag(value)}}}")
    return " ".join(clauses)


def _redis_like_create_index_args(settings: dict[str, Any], dimensions: int) -> list[Any]:
    return [
        "FT.CREATE",
        settings["index"],
        "ON",
        "HASH",
        "PREFIX",
        "1",
        f"{settings['prefix']}:",
        "SCHEMA",
        "memory_id",
        "TAG",
        "project_id",
        "TAG",
        "user_id",
        "TAG",
        "agent_id",
        "TAG",
        "app_id",
        "TAG",
        "run_id",
        "TAG",
        "memory",
        "TEXT",
        "metadata",
        "TEXT",
        "created_at",
        "TAG",
        "updated_at",
        "TAG",
        "embedding",
        "VECTOR",
        "FLAT",
        "6",
        "TYPE",
        "FLOAT32",
        "DIM",
        str(dimensions or int(settings["dimensions"])),
        "DISTANCE_METRIC",
        settings["distance"],
    ]


def _redis_like_ensure_index(client: Any, settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    try:
        client.execute_command(*_redis_like_create_index_args(settings, dimensions))
    except Exception as exc:
        if "exist" not in str(exc).lower():
            raise


def _redis_like_metadata(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    metadata = _pinecone_metadata(memory, project_id)
    return {key: value for key, value in metadata.items() if key not in {"memory", "metadata_json"}}


def _redis_like_hash(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "memory_id": str(memory["id"]),
        "project_id": project_id,
        "memory": str(memory.get("memory") or ""),
        "metadata": json_dumps(_redis_like_metadata(memory, project_id)),
        "embedding": _redis_like_vector_bytes(embedding),
    }
    for field in ("user_id", "agent_id", "app_id", "run_id", "created_at", "updated_at"):
        value = memory.get(field)
        if value is not None:
            row[field] = str(value)
    return row


def _redis_like_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _redis_like_field_map(fields: Any) -> dict[str, Any]:
    if isinstance(fields, dict):
        return {_redis_like_text(key): value for key, value in fields.items()}
    if not isinstance(fields, (list, tuple)):
        return {}
    mapped: dict[str, Any] = {}
    for index in range(0, len(fields) - 1, 2):
        mapped[_redis_like_text(fields[index])] = fields[index + 1]
    return mapped


def _redis_like_parse_search_response(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, (list, tuple)) or len(response) < 2:
        return []
    hits: list[dict[str, Any]] = []
    for rank, index in enumerate(range(1, len(response), 2)):
        key = response[index]
        fields = response[index + 1] if index + 1 < len(response) else {}
        mapped = _redis_like_field_map(fields)
        memory_id = mapped.get("memory_id") or _redis_like_text(key).rsplit(":", 1)[-1]
        distance = mapped.get("vector_distance") or mapped.get("__embedding_score")
        try:
            score = max(0.0, 1.0 - float(_redis_like_text(distance))) if distance is not None else 0.0
        except ValueError:
            score = 0.0
        hits.append({"id": _redis_like_text(memory_id), "score": score, "rank": rank})
    return hits


def _faiss_module() -> Any:
    return importlib.import_module("faiss")


def _numpy_module() -> Any:
    return importlib.import_module("numpy")


def _faiss_paths(settings: dict[str, Any]) -> tuple[Path, Path]:
    root = Path(settings["path"])
    root.mkdir(parents=True, exist_ok=True)
    collection = settings["collection"]
    return root / f"{collection}.faiss", root / f"{collection}.json"


def _faiss_empty_state() -> dict[str, Any]:
    return {"ids": [], "vectors": {}, "payloads": {}}


def _faiss_load_state(settings: dict[str, Any]) -> dict[str, Any]:
    _index_path, state_path = _faiss_paths(settings)
    if not state_path.exists():
        return _faiss_empty_state()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _faiss_empty_state()
    if not isinstance(data, dict):
        return _faiss_empty_state()
    ids = data.get("ids") if isinstance(data.get("ids"), list) else []
    vectors = data.get("vectors") if isinstance(data.get("vectors"), dict) else {}
    payloads = data.get("payloads") if isinstance(data.get("payloads"), dict) else {}
    valid_ids = [str(memory_id) for memory_id in ids if str(memory_id) in vectors]
    return {"ids": valid_ids, "vectors": vectors, "payloads": payloads}


def _faiss_vector_matrix(vectors: list[list[float]]) -> Any:
    numpy = _numpy_module()
    return numpy.array(vectors, dtype=numpy.float32)


def _faiss_prepare_vectors(vectors: list[list[float]], settings: dict[str, Any]) -> Any:
    matrix = _faiss_vector_matrix(vectors)
    if settings["distance"] == "cosine" and len(vectors) > 0:
        _faiss_module().normalize_L2(matrix)
    return matrix


def _faiss_new_index(settings: dict[str, Any], dimensions: int) -> Any:
    faiss = _faiss_module()
    if settings["distance"] in {"cosine", "inner_product", "ip"}:
        return faiss.IndexFlatIP(dimensions)
    return faiss.IndexFlatL2(dimensions)


def _faiss_rebuild_index(settings: dict[str, Any], state: dict[str, Any], dimensions: int) -> Any:
    index = _faiss_new_index(settings, dimensions)
    ids = [memory_id for memory_id in state["ids"] if memory_id in state["vectors"]]
    if ids:
        index.add(_faiss_prepare_vectors([state["vectors"][memory_id] for memory_id in ids], settings))
    _index_path, state_path = _faiss_paths(settings)
    _faiss_module().write_index(index, str(_index_path))
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def _faiss_payload(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    payload = _pinecone_metadata(memory, project_id)
    payload["metadata"] = memory.get("metadata", {})
    return payload


def _faiss_payload_matches(payload: dict[str, Any], filters: dict[str, Any], project_id: str) -> bool:
    if payload.get("project_id") != project_id:
        return False
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value and payload.get(field) != value:
            return False
    return True


def _faiss_load_index(settings: dict[str, Any], state: dict[str, Any], dimensions: int) -> Any:
    index_path, _state_path = _faiss_paths(settings)
    if index_path.exists():
        return _faiss_module().read_index(str(index_path))
    if settings.get("auto_create"):
        return _faiss_rebuild_index(settings, state, dimensions)
    return None


def _safe_cql_identifier(name: str, label: str) -> str:
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]{0,127}$", name):
        raise ValueError(f"invalid Cassandra {label}: {name}")
    return name


def _cassandra_modules() -> tuple[Any, Any]:
    cluster_module = importlib.import_module("cassandra.cluster")
    auth_module = importlib.import_module("cassandra.auth")
    return cluster_module, auth_module


def _cassandra_connect(settings: dict[str, Any]) -> tuple[Any, Any]:
    cluster_module, auth_module = _cassandra_modules()
    auth_provider = None
    if settings.get("username") and settings.get("password"):
        auth_provider = auth_module.PlainTextAuthProvider(
            username=settings["username"],
            password=settings["password"],
        )
    if settings.get("secure_connect_bundle"):
        cluster = cluster_module.Cluster(
            cloud={"secure_connect_bundle": settings["secure_connect_bundle"]},
            auth_provider=auth_provider,
            protocol_version=settings["protocol_version"],
        )
    else:
        kwargs: dict[str, Any] = {
            "contact_points": settings["contact_points"],
            "port": settings["port"],
            "protocol_version": settings["protocol_version"],
        }
        if auth_provider:
            kwargs["auth_provider"] = auth_provider
        cluster = cluster_module.Cluster(**kwargs)
    return cluster, cluster.connect()


def _cassandra_close(cluster: Any) -> None:
    shutdown = getattr(cluster, "shutdown", None)
    if callable(shutdown):
        shutdown()


def _cassandra_ensure_schema(session: Any, settings: dict[str, Any]) -> None:
    keyspace = _safe_cql_identifier(settings["keyspace"], "keyspace")
    table = _safe_cql_identifier(settings["table"], "table")
    session.execute(
        f"CREATE KEYSPACE IF NOT EXISTS {keyspace} "
        "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"
    )
    set_keyspace = getattr(session, "set_keyspace", None)
    if callable(set_keyspace):
        set_keyspace(keyspace)
    session.execute(
        f"CREATE TABLE IF NOT EXISTS {keyspace}.{table} ("
        "id text PRIMARY KEY, vector list<float>, payload text)"
    )


def _cassandra_payload(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    payload = _pinecone_metadata(memory, project_id)
    payload["metadata"] = memory.get("metadata", {})
    return payload


def _cassandra_row_value(row: Any, field: str, index: int) -> Any:
    if hasattr(row, field):
        return getattr(row, field)
    if isinstance(row, dict):
        return row.get(field)
    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]
    return None


def _cassandra_payload_matches(payload: dict[str, Any], filters: dict[str, Any], project_id: str) -> bool:
    if payload.get("project_id") != project_id:
        return False
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value and payload.get(field) != value:
            return False
    return True


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = sum(float(value) * float(value) for value in left) ** 0.5
    right_norm = sum(float(value) * float(value) for value in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _azure_mysql_module() -> Any:
    return importlib.import_module("pymysql")


def _azure_mysql_connect(settings: dict[str, Any]) -> Any:
    pymysql = _azure_mysql_module()
    cursor_class = getattr(getattr(pymysql, "cursors", None), "DictCursor", None)
    kwargs: dict[str, Any] = {
        "host": settings["host"],
        "port": int(settings["port"]),
        "user": settings["user"],
        "password": settings["password"],
        "database": settings["database"],
        "charset": "utf8mb4",
        "autocommit": False,
    }
    if cursor_class is not None:
        kwargs["cursorclass"] = cursor_class
    return pymysql.connect(**kwargs)


def _azure_mysql_close(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def _azure_mysql_ensure_schema(connection: Any, settings: dict[str, Any]) -> None:
    table = _safe_cql_identifier(settings["table"], "table")
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS `{table}` ("
            "id VARCHAR(255) PRIMARY KEY, vector JSON, payload JSON)"
        )
        connection.commit()
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def _azure_mysql_payload(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    payload = _pinecone_metadata(memory, project_id)
    payload["metadata"] = memory.get("metadata", {})
    return payload


def _azure_mysql_row_value(row: Any, field: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    if hasattr(row, field):
        return getattr(row, field)
    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]
    return None


def _baidu_modules() -> tuple[Any, Any, Any, Any]:
    pymochow = importlib.import_module("pymochow")
    credentials_module = importlib.import_module("pymochow.auth.bce_credentials")
    configuration_module = importlib.import_module("pymochow.configuration")
    table_module = importlib.import_module("pymochow.model.table")
    return pymochow, credentials_module, configuration_module, table_module


def _baidu_table(settings: dict[str, Any]) -> tuple[Any, Any]:
    pymochow, credentials_module, configuration_module, _table_module = _baidu_modules()
    credentials = credentials_module.BceCredentials(settings["account"], settings["api_key"])
    config = configuration_module.Configuration(credentials=credentials, endpoint=settings["url"])
    client = pymochow.MochowClient(config)
    database = client.database(settings["database"])
    return client, database.describe_table(settings["table"])


def _baidu_filter(filters: dict[str, Any], project_id: str) -> str:
    clauses = [f'metadata["project_id"] = "{project_id}"']
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            clauses.append(f'metadata["{field}"] = "{value}"')
    return " AND ".join(clauses)


def _baidu_payload(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    payload = _pinecone_metadata(memory, project_id)
    payload["metadata"] = memory.get("metadata", {})
    return payload


def _neptune_graph(settings: dict[str, Any]) -> Any:
    module = importlib.import_module("langchain_aws")
    graph_id = str(settings["endpoint"]).replace("neptune-graph://", "", 1)
    return module.NeptuneAnalyticsGraph(graph_id)


def _neptune_label(settings: dict[str, Any]) -> str:
    return "MEM0_VECTOR_" + _safe_cql_identifier(settings["collection"], "collection")


def _neptune_payload(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    payload = _pinecone_metadata(memory, project_id)
    payload["label"] = _neptune_label(_neptune_settings(project_id))
    payload["metadata"] = memory.get("metadata", {})
    return payload


def _neptune_filter_clause(filters: dict[str, Any], project_id: str, label: str) -> str:
    conditions = [
        f"{{equals:{{property: 'label', value: '{label}'}}}}",
        f"{{equals:{{property: 'project_id', value: '{project_id}'}}}}",
    ]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            conditions.append(f"{{equals:{{property: '{field}', value: '{value}'}}}}")
    if len(conditions) == 1:
        return f", nodeFilter: {conditions[0]}"
    return f", nodeFilter: {{andAll: [ {', '.join(conditions)} ]}}"


def _neptune_parse_search(response: Any) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for index, item in enumerate(response or []):
        node = item.get("n", {}) if isinstance(item, dict) else {}
        memory_id = node.get("~id")
        if memory_id is None:
            continue
        hits.append({"id": str(memory_id), "score": float(item.get("score", 0.0)), "rank": index})
    return hits


def _vertex_modules() -> tuple[Any, Any, Any]:
    aiplatform = importlib.import_module("google.cloud.aiplatform")
    aiplatform_v1 = importlib.import_module("google.cloud.aiplatform_v1")
    endpoint_module = importlib.import_module(
        "google.cloud.aiplatform.matching_engine.matching_engine_index_endpoint"
    )
    return aiplatform, aiplatform_v1, endpoint_module


def _vertex_clients(settings: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    aiplatform, aiplatform_v1, endpoint_module = _vertex_modules()
    aiplatform.init(project=settings["project_id"], location=settings["region"])
    index_name = f"projects/{settings['project_number']}/locations/{settings['region']}/indexes/{settings['index_id']}"
    index = aiplatform.MatchingEngineIndex(index_name=index_name)
    endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=settings["endpoint_id"])
    return index, endpoint, aiplatform_v1, endpoint_module


def _vertex_payload(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    payload = _pinecone_metadata(memory, project_id)
    return {key: value for key, value in payload.items() if key not in {"metadata_json", "categories"}}


def _vertex_datapoint(aiplatform_v1: Any, memory_id: str, vector: list[float], payload: dict[str, Any]) -> Any:
    datapoint_type = aiplatform_v1.types.index.IndexDatapoint
    restrictions = [
        datapoint_type.Restriction(namespace=key, allow_list=[str(value)])
        for key, value in payload.items()
        if value is not None
    ]
    return datapoint_type(datapoint_id=memory_id, feature_vector=vector, restricts=restrictions)


def _vertex_namespaces(endpoint_module: Any, filters: dict[str, Any], project_id: str) -> list[Any]:
    namespace = endpoint_module.Namespace
    namespaces = [namespace("project_id", [project_id], [])]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            namespaces.append(namespace(field, [value], []))
    return namespaces


def _vertex_parse_neighbors(response: Any) -> list[dict[str, Any]]:
    if not response:
        return []
    neighbors = response[0] if isinstance(response, (list, tuple)) else []
    hits: list[dict[str, Any]] = []
    for index, neighbor in enumerate(neighbors):
        memory_id = getattr(neighbor, "id", None)
        if memory_id is None:
            continue
        distance = getattr(neighbor, "distance", None)
        score = max(0.0, 1.0 - float(distance)) if distance is not None else 0.0
        hits.append({"id": str(memory_id), "score": score, "rank": index})
    return hits


def _pinecone_filter(filters: dict[str, Any], project_id: str) -> dict[str, Any]:
    pinecone_filter: dict[str, Any] = {"project_id": {"$eq": project_id}}
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            pinecone_filter[field] = {"$eq": value}
    return pinecone_filter


def _pinecone_metadata(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    metadata = {
        "project_id": project_id,
        "memory": memory.get("memory") or "",
        "categories": memory.get("categories") or [],
        "metadata_json": json_dumps(memory.get("metadata", {})),
    }
    for field in ("user_id", "agent_id", "app_id", "run_id", "created_at", "updated_at"):
        value = memory.get(field)
        if value is not None:
            metadata[field] = str(value)
    return metadata


def _upstash_endpoint(settings: dict[str, Any], operation: str) -> str:
    namespace = str(settings.get("namespace") or "")
    if namespace:
        return f"{settings['url']}/{operation}/{quote(namespace, safe='')}"
    return f"{settings['url']}/{operation}"


def _upstash_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _upstash_filter(filters: dict[str, Any], project_id: str) -> str:
    clauses = [f"project_id = {_upstash_quote(project_id)}"]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            clauses.append(f"{field} = {_upstash_quote(value)}")
    return " AND ".join(clauses)


def _elastic_endpoint(settings: dict[str, Any], suffix: str) -> str:
    return f"{settings['url']}/{quote(str(settings['index']), safe='')}{suffix}"


def _elastic_filter(filters: dict[str, Any], project_id: str) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = [{"term": {"project_id": project_id}}]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            clauses.append({"term": {field: value}})
    return clauses


def _elastic_document(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    document = {
        "id": str(memory["id"]),
        "project_id": project_id,
        "memory": memory.get("memory") or "",
        "categories": memory.get("categories") or [],
        "metadata_json": json_dumps(memory.get("metadata", {})),
        "embedding": embedding,
    }
    for field in ("user_id", "agent_id", "app_id", "run_id", "created_at", "updated_at"):
        value = memory.get(field)
        if value is not None:
            document[field] = str(value)
    return document


def _turbopuffer_endpoint(settings: dict[str, Any], suffix: str = "") -> str:
    namespace = quote(str(settings["namespace"]), safe="")
    return f"{settings['url']}/v2/namespaces/{namespace}{suffix}"


def _turbopuffer_filter(filters: dict[str, Any], project_id: str) -> list[Any]:
    clauses: list[Any] = [["project_id", "Eq", project_id]]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            clauses.append([field, "Eq", value])
    if len(clauses) == 1:
        return clauses[0]
    return ["And", clauses]


def _turbopuffer_row(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    row = _elastic_document(memory, embedding, project_id)
    row["vector"] = row.pop("embedding")
    return row


def _elastic_ensure_index(settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    size = dimensions or int(settings["dimensions"])
    mapping = {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "agent_id": {"type": "keyword"},
                "app_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "categories": {"type": "keyword"},
                "memory": {"type": "text"},
                "metadata_json": {"type": "keyword", "index": False},
                "embedding": {"type": "dense_vector", "dims": size, "index": False},
                "created_at": {"type": "keyword", "index": False},
                "updated_at": {"type": "keyword", "index": False},
            }
        }
    }
    with httpx.Client(timeout=float(settings["timeout"])) as client:
        response = client.put(_elastic_endpoint(settings, ""), headers=_elastic_headers(settings), json=mapping)
    if getattr(response, "status_code", 200) not in {200, 201, 400}:
        response.raise_for_status()


def _opensearch_ensure_index(settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    size = dimensions or int(settings["dimensions"])
    mapping = {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "agent_id": {"type": "keyword"},
                "app_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "categories": {"type": "keyword"},
                "memory": {"type": "text"},
                "metadata_json": {"type": "keyword", "index": False},
                "vector": {"type": "knn_vector", "dimension": size},
                "created_at": {"type": "keyword", "index": False},
                "updated_at": {"type": "keyword", "index": False},
            }
        },
    }
    with httpx.Client(timeout=float(settings["timeout"])) as client:
        response = client.put(_elastic_endpoint(settings, ""), headers=_opensearch_headers(settings), json=mapping)
    if getattr(response, "status_code", 200) not in {200, 201, 400}:
        response.raise_for_status()


def _weaviate_properties(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    properties = {
        "project_id": project_id,
        "memory_id": str(memory["id"]),
        "memory": memory.get("memory") or "",
        "categories": memory.get("categories") or [],
        "metadata_json": json_dumps(memory.get("metadata", {})),
    }
    for field in ("user_id", "agent_id", "app_id", "run_id", "created_at", "updated_at"):
        value = memory.get(field)
        if value is not None:
            properties[field] = str(value)
    return properties


def _weaviate_ensure_schema(settings: dict[str, Any]) -> None:
    if not settings.get("auto_create"):
        return
    class_name = settings["class_name"]
    schema = {
        "class": class_name,
        "vectorizer": "none",
        "properties": [
            {"name": "project_id", "dataType": ["text"]},
            {"name": "memory_id", "dataType": ["text"]},
            {"name": "memory", "dataType": ["text"]},
            {"name": "user_id", "dataType": ["text"]},
            {"name": "agent_id", "dataType": ["text"]},
            {"name": "app_id", "dataType": ["text"]},
            {"name": "run_id", "dataType": ["text"]},
            {"name": "categories", "dataType": ["text[]"]},
            {"name": "metadata_json", "dataType": ["text"]},
            {"name": "created_at", "dataType": ["text"]},
            {"name": "updated_at", "dataType": ["text"]},
        ],
    }
    with httpx.Client(timeout=float(settings["timeout"])) as client:
        response = client.post(f"{settings['url']}/v1/schema", headers=_weaviate_headers(settings), json=schema)
    if getattr(response, "status_code", 200) not in {200, 201, 422}:
        response.raise_for_status()


def _weaviate_where(filters: dict[str, Any], project_id: str) -> str:
    operands = [f'{{path: ["project_id"], operator: Equal, valueText: {json_dumps(project_id)}}}']
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            operands.append(f'{{path: ["{field}"], operator: Equal, valueText: {json_dumps(value)}}}')
    if len(operands) == 1:
        return operands[0]
    return "{operator: And, operands: [" + ", ".join(operands) + "]}"


def _weaviate_query(settings: dict[str, Any], query_embedding: list[float], filters: dict[str, Any], top_k: int, project_id: str) -> str:
    vector = json_dumps([float(value) for value in query_embedding])
    where = _weaviate_where(filters, project_id)
    class_name = settings["class_name"]
    return (
        "{ Get { "
        f"{class_name}(nearVector: {{vector: {vector}}}, where: {where}, limit: {int(top_k)}) "
        "{ memory_id _additional { id certainty distance } } "
        "} }"
    )


def _chroma_where(filters: dict[str, Any], project_id: str) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = [{"project_id": {"$eq": project_id}}]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            clauses.append({field: {"$eq": value}})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _chroma_metadata(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    metadata = {
        "project_id": project_id,
        "memory": memory.get("memory") or "",
        "categories_json": json_dumps(memory.get("categories", [])),
        "metadata_json": json_dumps(memory.get("metadata", {})),
    }
    for field in ("user_id", "agent_id", "app_id", "run_id", "created_at", "updated_at"):
        value = memory.get(field)
        if value is not None:
            metadata[field] = str(value)
    return metadata


def _chroma_collection_id(settings: dict[str, Any]) -> str:
    headers = _chroma_headers(settings)
    collection = str(settings["collection"])
    encoded = quote(collection, safe="")
    with httpx.Client(timeout=float(settings["timeout"])) as client:
        response = client.get(f"{settings['url']}/api/v1/collections/{encoded}", headers=headers)
        if getattr(response, "status_code", 200) == 404 and settings.get("auto_create"):
            response = client.post(
                f"{settings['url']}/api/v1/collections",
                headers=headers,
                json={"name": collection, "metadata": {"hnsw:space": "cosine"}},
            )
        if getattr(response, "status_code", 200) == 404:
            return collection
        response.raise_for_status()
        payload = response.json()
    if isinstance(payload, dict):
        return str(payload.get("id") or payload.get("name") or collection)
    return collection


def _milvus_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _milvus_filter(filters: dict[str, Any], project_id: str) -> str:
    clauses = [f"project_id == {_milvus_quote(project_id)}"]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            clauses.append(f"{field} == {_milvus_quote(value)}")
    return " and ".join(clauses)


def _milvus_row(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    row = _turbopuffer_row(memory, embedding, project_id)
    row["metadata_json"] = json_dumps(memory.get("metadata", {}))
    row["categories_json"] = json_dumps(memory.get("categories", []))
    row.pop("categories", None)
    return row


def _milvus_ensure_collection(settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    with httpx.Client(timeout=float(settings["timeout"])) as client:
        response = client.post(
            f"{settings['url']}/v2/vectordb/collections/create",
            headers=_milvus_headers(settings),
            json={
                "collectionName": settings["collection"],
                "dimension": dimensions or int(settings["dimensions"]),
                "primaryField": "id",
                "vectorField": "vector",
                "metricType": "COSINE",
            },
        )
    if getattr(response, "status_code", 200) not in {200, 201, 409}:
        response.raise_for_status()


def _mongodb_payload(memory: dict[str, Any], project_id: str) -> dict[str, Any]:
    payload = {
        "project_id": project_id,
        "data": memory.get("memory") or "",
        "memory": memory.get("memory") or "",
        "categories": memory.get("categories") or [],
        "metadata_json": json_dumps(memory.get("metadata", {})),
    }
    for field in ("user_id", "agent_id", "app_id", "run_id", "created_at", "updated_at"):
        value = memory.get(field)
        if value is not None:
            payload[field] = str(value)
    return payload


def _mongodb_document(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    return {
        "_id": str(memory["id"]),
        "embedding": [float(value) for value in embedding],
        "payload": _mongodb_payload(memory, project_id),
    }


def _mongodb_filter(filters: dict[str, Any], project_id: str) -> dict[str, Any]:
    mongo_filter: dict[str, Any] = {"payload.project_id": project_id}
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            mongo_filter[f"payload.{field}"] = value
    return mongo_filter


def _mongodb_collection(settings: dict[str, Any]) -> tuple[Any, Any]:
    pymongo = _pymongo_module()
    client = pymongo.MongoClient(
        settings["url"],
        serverSelectionTimeoutMS=max(int(float(settings["timeout"]) * 1000), 1000),
    )
    return client, client[settings["db"]][settings["collection"]]


def _mongodb_ensure_index(collection: Any, settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    operations = _pymongo_operations_module()
    model = operations.SearchIndexModel(
        name=settings["index"],
        type="vectorSearch",
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": dimensions or int(settings["dimensions"]),
                    "similarity": "cosine",
                }
            ]
        },
    )
    collection.create_search_index(model)


def _mongodb_pipeline(
    settings: dict[str, Any],
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    return [
        {
            "$vectorSearch": {
                "index": settings["index"],
                "limit": int(top_k),
                "numCandidates": min(max(int(top_k) * 20, int(top_k)), 10000),
                "queryVector": [float(value) for value in query_embedding],
                "path": "embedding",
            }
        },
        {"$match": _mongodb_filter(filters, project_id)},
        {"$set": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},
    ]


def _azure_search_index_url(settings: dict[str, Any]) -> str:
    index = quote(str(settings["index"]), safe="")
    return f"{settings['url']}/indexes/{index}?api-version={settings['api_version']}"


def _azure_search_index_documents_url(settings: dict[str, Any]) -> str:
    index = quote(str(settings["index"]), safe="")
    return f"{settings['url']}/indexes('{index}')/docs/search.index?api-version={settings['api_version']}"


def _azure_search_query_url(settings: dict[str, Any]) -> str:
    index = quote(str(settings["index"]), safe="")
    return f"{settings['url']}/indexes/{index}/docs/search?api-version={settings['api_version']}"


def _azure_search_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _azure_search_filter(filters: dict[str, Any], project_id: str) -> str:
    clauses = [f"project_id eq {_azure_search_quote(project_id)}"]
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            clauses.append(f"{field} eq {_azure_search_quote(value)}")
    return " and ".join(clauses)


def _azure_search_document(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    document = {
        "id": str(memory["id"]),
        "project_id": project_id,
        "memory": memory.get("memory") or "",
        "vector": [float(value) for value in embedding],
        "categories_json": json_dumps(memory.get("categories", [])),
        "metadata_json": json_dumps(memory.get("metadata", {})),
    }
    for field in ("user_id", "agent_id", "app_id", "run_id", "created_at", "updated_at"):
        value = memory.get(field)
        if value is not None:
            document[field] = str(value)
    return document


def _azure_search_ensure_index(settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    size = dimensions or int(settings["dimensions"])
    index = {
        "name": settings["index"],
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "project_id", "type": "Edm.String", "filterable": True},
            {"name": "user_id", "type": "Edm.String", "filterable": True},
            {"name": "agent_id", "type": "Edm.String", "filterable": True},
            {"name": "app_id", "type": "Edm.String", "filterable": True},
            {"name": "run_id", "type": "Edm.String", "filterable": True},
            {"name": "memory", "type": "Edm.String", "searchable": True},
            {"name": "categories_json", "type": "Edm.String"},
            {"name": "metadata_json", "type": "Edm.String"},
            {"name": "created_at", "type": "Edm.String"},
            {"name": "updated_at", "type": "Edm.String"},
            {
                "name": "vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "dimensions": size,
                "vectorSearchProfile": "mem1-vector-profile",
            },
        ],
        "vectorSearch": {
            "algorithms": [{"name": "mem1-hnsw", "kind": "hnsw"}],
            "profiles": [{"name": "mem1-vector-profile", "algorithm": "mem1-hnsw"}],
        },
    }
    with httpx.Client(timeout=float(settings["timeout"])) as client:
        response = client.put(_azure_search_index_url(settings), headers=_azure_search_headers(settings), json=index)
    if getattr(response, "status_code", 200) not in {200, 201, 204, 409}:
        response.raise_for_status()


def _databricks_index_path(settings: dict[str, Any]) -> str:
    index = quote(str(settings["index"]), safe=".")
    return f"{settings['url']}/api/2.0/vector-search/indexes/{index}"


def _databricks_columns() -> list[str]:
    return [
        "memory_id",
        "project_id",
        "user_id",
        "agent_id",
        "app_id",
        "run_id",
        "memory",
        "categories_json",
        "metadata_json",
        "created_at",
        "updated_at",
    ]


def _databricks_filters_json(filters: dict[str, Any], project_id: str) -> str:
    databricks_filter: dict[str, str] = {"project_id": project_id}
    for field in ("user_id", "agent_id", "app_id", "run_id"):
        value = filters.get(field)
        if isinstance(value, str) and value:
            databricks_filter[field] = value
    return json_dumps(databricks_filter)


def _databricks_row(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    row = {
        "memory_id": str(memory["id"]),
        "project_id": project_id,
        "memory": memory.get("memory") or "",
        "embedding": [float(value) for value in embedding],
        "categories_json": json_dumps(memory.get("categories", [])),
        "metadata_json": json_dumps(memory.get("metadata", {})),
    }
    for field in ("user_id", "agent_id", "app_id", "run_id", "created_at", "updated_at"):
        value = memory.get(field)
        if value is not None:
            row[field] = str(value)
    return row


def _databricks_ensure_index(settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create") or not settings.get("endpoint_name"):
        return
    schema = {
        "memory_id": "string",
        "project_id": "string",
        "user_id": "string",
        "agent_id": "string",
        "app_id": "string",
        "run_id": "string",
        "memory": "string",
        "categories_json": "string",
        "metadata_json": "string",
        "created_at": "string",
        "updated_at": "string",
        "embedding": "array<float>",
    }
    body = {
        "name": settings["index"],
        "endpoint_name": settings["endpoint_name"],
        "primary_key": "memory_id",
        "index_type": "DIRECT_ACCESS",
        "direct_access_index_spec": {
            "embedding_vector_columns": [
                {"name": "embedding", "embedding_dimension": dimensions or int(settings["dimensions"])}
            ],
            "schema_json": json_dumps(schema),
        },
    }
    with httpx.Client(timeout=float(settings["timeout"])) as client:
        response = client.post(
            f"{settings['url']}/api/2.0/vector-search/indexes",
            headers=_databricks_headers(settings),
            json=body,
        )
    if getattr(response, "status_code", 200) not in {200, 201, 409}:
        response.raise_for_status()


def _databricks_hit_from_row(row: Any, columns: list[str], rank: int) -> dict[str, Any] | None:
    if isinstance(row, dict):
        memory_id = row.get("memory_id") or row.get("id")
        score = row.get("score")
    elif isinstance(row, (list, tuple)):
        row_dict = dict(zip(columns, row))
        memory_id = row_dict.get("memory_id") or row_dict.get("id")
        score = row_dict.get("score")
        if score is None and len(row) > len(columns):
            score = row[-1]
    else:
        return None
    if memory_id is None:
        return None
    return {"id": str(memory_id), "score": float(score or 0.0), "rank": rank}


def _databricks_hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
    manifest_columns = payload.get("manifest", {}).get("columns", []) if isinstance(payload, dict) else []
    columns = [str(item.get("name")) for item in manifest_columns if isinstance(item, dict) and item.get("name")]
    if not columns:
        columns = [*_databricks_columns(), "score"]
    result = payload.get("result", payload) if isinstance(payload, dict) else {}
    rows = result.get("data_array") if isinstance(result, dict) else []
    hits: list[dict[str, Any]] = []
    for index, row in enumerate(rows or []):
        hit = _databricks_hit_from_row(row, columns, index)
        if hit:
            hits.append(hit)
    return hits


def _pinecone_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _pinecone_settings(project_id)
    if not _pinecone_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/vectors/upsert",
                headers=_pinecone_headers(settings),
                json={
                    "namespace": settings["namespace"],
                    "vectors": [
                        {
                            "id": point_id,
                            "values": embedding,
                            "metadata": _pinecone_metadata(memory, project_id),
                        }
                    ],
                },
            )
        response.raise_for_status()
        return {"ok": True, "provider": "pinecone", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_pinecone_error(exc, settings, "upsert")


def _s3_vectors_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _s3_vectors_settings(project_id)
    if not _s3_vectors_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        client = _s3_vectors_client(settings)
        _s3_vectors_ensure_index(client, settings, len(embedding))
        client.put_vectors(
            vectorBucketName=settings["bucket"],
            indexName=settings["index"],
            vectors=[
                {
                    "key": point_id,
                    "data": {"float32": [float(value) for value in embedding]},
                    "metadata": _s3_vectors_metadata(memory, project_id),
                }
            ],
        )
        return {"ok": True, "provider": "s3_vectors", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_s3_vectors_error(exc, settings, "upsert")


def _s3_vectors_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _s3_vectors_settings(project_id)
    if not _s3_vectors_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        client = _s3_vectors_client(settings)
        client.delete_vectors(
            vectorBucketName=settings["bucket"],
            indexName=settings["index"],
            keys=[str(memory_id)],
        )
        return {"ok": True, "provider": "s3_vectors", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_s3_vectors_error(exc, settings, "delete")


def _s3_vectors_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _s3_vectors_settings(project_id)
    if not _s3_vectors_enabled(settings):
        return []
    try:
        client = _s3_vectors_client(settings)
        response = client.query_vectors(
            vectorBucketName=settings["bucket"],
            indexName=settings["index"],
            queryVector={"float32": [float(value) for value in query_embedding]},
            topK=int(top_k),
            returnMetadata=True,
            returnDistance=True,
            filter=_s3_vectors_filter(filters, project_id),
        )
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(response.get("vectors", []) if isinstance(response, dict) else []):
            if not isinstance(item, dict) or item.get("key") is None:
                continue
            distance = item.get("distance")
            score = max(0.0, 1.0 - float(distance)) if distance is not None else 0.0
            hits.append({"id": str(item["key"]), "score": score, "rank": index})
        return hits
    except Exception as exc:
        _handle_s3_vectors_error(exc, settings, "search")
        return []


def _redis_like_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _redis_like_settings(project_id)
    if not _redis_like_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        client = _redis_like_client(settings)
        _redis_like_ensure_index(client, settings, len(embedding))
        client.hset(f"{settings['prefix']}:{point_id}", mapping=_redis_like_hash(memory, embedding, project_id))
        return {"ok": True, "provider": settings["provider"], "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_redis_like_error(exc, settings, "upsert")


def _redis_like_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _redis_like_settings(project_id)
    if not _redis_like_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        client = _redis_like_client(settings)
        client.delete(f"{settings['prefix']}:{memory_id}")
        return {"ok": True, "provider": settings["provider"], "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_redis_like_error(exc, settings, "delete")


def _redis_like_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _redis_like_settings(project_id)
    if not _redis_like_enabled(settings):
        return []
    try:
        client = _redis_like_client(settings)
        query = f"{_redis_like_filter(filters, project_id)}=>[KNN {int(top_k)} @embedding $vec_param AS vector_distance]"
        response = client.execute_command(
            "FT.SEARCH",
            settings["index"],
            query,
            "PARAMS",
            2,
            "vec_param",
            _redis_like_vector_bytes(query_embedding),
            "RETURN",
            2,
            "memory_id",
            "vector_distance",
            "SORTBY",
            "vector_distance",
            "ASC",
            "DIALECT",
            2,
        )
        return _redis_like_parse_search_response(response)
    except Exception as exc:
        _handle_redis_like_error(exc, settings, "search")
        return []


def _faiss_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _faiss_settings(project_id)
    if not _faiss_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        state = _faiss_load_state(settings)
        if point_id not in state["ids"]:
            state["ids"].append(point_id)
        state["vectors"][point_id] = [float(value) for value in embedding]
        state["payloads"][point_id] = _faiss_payload(memory, project_id)
        _faiss_rebuild_index(settings, state, len(embedding))
        return {"ok": True, "provider": "faiss", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_faiss_error(exc, settings, "upsert")


def _faiss_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _faiss_settings(project_id)
    if not _faiss_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        state = _faiss_load_state(settings)
        memory_id = str(memory_id)
        state["ids"] = [item for item in state["ids"] if item != memory_id]
        state["vectors"].pop(memory_id, None)
        state["payloads"].pop(memory_id, None)
        dimensions = int(settings["dimensions"])
        if state["ids"]:
            first_vector = state["vectors"][state["ids"][0]]
            dimensions = len(first_vector)
        _faiss_rebuild_index(settings, state, dimensions)
        return {"ok": True, "provider": "faiss", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_faiss_error(exc, settings, "delete")


def _faiss_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _faiss_settings(project_id)
    if not _faiss_enabled(settings):
        return []
    try:
        state = _faiss_load_state(settings)
        if not state["ids"]:
            return []
        index = _faiss_load_index(settings, state, len(query_embedding))
        if index is None:
            return []
        fetch_k = min(len(state["ids"]), int(top_k) * 2 if filters else int(top_k))
        query = _faiss_prepare_vectors([[float(value) for value in query_embedding]], settings)
        scores, indices = index.search(query, fetch_k)
        hits: list[dict[str, Any]] = []
        raw_scores = scores[0] if scores is not None else []
        raw_indices = indices[0] if indices is not None else []
        for raw_score, raw_index in zip(raw_scores, raw_indices):
            index_id = int(raw_index)
            if index_id < 0 or index_id >= len(state["ids"]):
                continue
            memory_id = str(state["ids"][index_id])
            payload = state["payloads"].get(memory_id, {})
            if not isinstance(payload, dict) or not _faiss_payload_matches(payload, filters, project_id):
                continue
            score = 1.0 / (1.0 + float(raw_score)) if settings["distance"] in {"euclidean", "l2"} else float(raw_score)
            hits.append({"id": memory_id, "score": score, "rank": len(hits)})
            if len(hits) >= int(top_k):
                break
        return hits
    except Exception as exc:
        _handle_faiss_error(exc, settings, "search")
        return []


def _cassandra_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _cassandra_settings(project_id)
    if not _cassandra_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    cluster = None
    try:
        cluster, session = _cassandra_connect(settings)
        if settings.get("auto_create"):
            _cassandra_ensure_schema(session, settings)
        keyspace = _safe_cql_identifier(settings["keyspace"], "keyspace")
        table = _safe_cql_identifier(settings["table"], "table")
        prepared = session.prepare(f"INSERT INTO {keyspace}.{table} (id, vector, payload) VALUES (?, ?, ?)")
        session.execute(
            prepared,
            (
                str(memory["id"]),
                [float(value) for value in embedding],
                json.dumps(_cassandra_payload(memory, project_id)),
            ),
        )
        return {"ok": True, "provider": "cassandra", "operation": "upsert", "memory_id": str(memory["id"])}
    except Exception as exc:
        return _handle_cassandra_error(exc, settings, "upsert")
    finally:
        if cluster is not None:
            _cassandra_close(cluster)


def _cassandra_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _cassandra_settings(project_id)
    if not _cassandra_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    cluster = None
    try:
        cluster, session = _cassandra_connect(settings)
        keyspace = _safe_cql_identifier(settings["keyspace"], "keyspace")
        table = _safe_cql_identifier(settings["table"], "table")
        prepared = session.prepare(f"DELETE FROM {keyspace}.{table} WHERE id = ?")
        session.execute(prepared, (str(memory_id),))
        return {"ok": True, "provider": "cassandra", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_cassandra_error(exc, settings, "delete")
    finally:
        if cluster is not None:
            _cassandra_close(cluster)


def _cassandra_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _cassandra_settings(project_id)
    if not _cassandra_enabled(settings):
        return []
    cluster = None
    try:
        cluster, session = _cassandra_connect(settings)
        if settings.get("auto_create"):
            _cassandra_ensure_schema(session, settings)
        keyspace = _safe_cql_identifier(settings["keyspace"], "keyspace")
        table = _safe_cql_identifier(settings["table"], "table")
        rows = session.execute(f"SELECT id, vector, payload FROM {keyspace}.{table}")
        scored: list[tuple[str, float]] = []
        query_vector = [float(value) for value in query_embedding]
        for row in rows:
            memory_id = _cassandra_row_value(row, "id", 0)
            vector = _cassandra_row_value(row, "vector", 1)
            payload_text = _cassandra_row_value(row, "payload", 2)
            if memory_id is None or not vector:
                continue
            try:
                payload = json.loads(payload_text) if payload_text else {}
            except (TypeError, json.JSONDecodeError):
                continue
            if not _cassandra_payload_matches(payload, filters, project_id):
                continue
            scored.append((str(memory_id), _cosine_similarity(query_vector, [float(value) for value in vector])))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            {"id": memory_id, "score": float(score), "rank": index}
            for index, (memory_id, score) in enumerate(scored[: int(top_k)])
        ]
    except Exception as exc:
        _handle_cassandra_error(exc, settings, "search")
        return []
    finally:
        if cluster is not None:
            _cassandra_close(cluster)


def _azure_mysql_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _azure_mysql_settings(project_id)
    if not _azure_mysql_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    connection = None
    try:
        connection = _azure_mysql_connect(settings)
        if settings.get("auto_create"):
            _azure_mysql_ensure_schema(connection, settings)
        table = _safe_cql_identifier(settings["table"], "table")
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"INSERT INTO `{table}` (id, vector, payload) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE vector = VALUES(vector), payload = VALUES(payload)",
                (
                    str(memory["id"]),
                    json.dumps([float(value) for value in embedding]),
                    json.dumps(_azure_mysql_payload(memory, project_id)),
                ),
            )
            connection.commit()
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        return {"ok": True, "provider": "azure_mysql", "operation": "upsert", "memory_id": str(memory["id"])}
    except Exception as exc:
        rollback = getattr(connection, "rollback", None) if connection is not None else None
        if callable(rollback):
            rollback()
        return _handle_azure_mysql_error(exc, settings, "upsert")
    finally:
        if connection is not None:
            _azure_mysql_close(connection)


def _azure_mysql_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _azure_mysql_settings(project_id)
    if not _azure_mysql_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    connection = None
    try:
        connection = _azure_mysql_connect(settings)
        table = _safe_cql_identifier(settings["table"], "table")
        cursor = connection.cursor()
        try:
            cursor.execute(f"DELETE FROM `{table}` WHERE id = %s", (str(memory_id),))
            connection.commit()
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        return {"ok": True, "provider": "azure_mysql", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        rollback = getattr(connection, "rollback", None) if connection is not None else None
        if callable(rollback):
            rollback()
        return _handle_azure_mysql_error(exc, settings, "delete")
    finally:
        if connection is not None:
            _azure_mysql_close(connection)


def _azure_mysql_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _azure_mysql_settings(project_id)
    if not _azure_mysql_enabled(settings):
        return []
    connection = None
    try:
        connection = _azure_mysql_connect(settings)
        if settings.get("auto_create"):
            _azure_mysql_ensure_schema(connection, settings)
        table = _safe_cql_identifier(settings["table"], "table")
        cursor = connection.cursor()
        try:
            cursor.execute(f"SELECT id, vector, payload FROM `{table}`")
            rows = cursor.fetchall()
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        query_vector = [float(value) for value in query_embedding]
        scored: list[tuple[str, float]] = []
        for row in rows:
            memory_id = _azure_mysql_row_value(row, "id", 0)
            vector_text = _azure_mysql_row_value(row, "vector", 1)
            payload_text = _azure_mysql_row_value(row, "payload", 2)
            if memory_id is None or not vector_text:
                continue
            try:
                vector = json.loads(vector_text) if isinstance(vector_text, str) else vector_text
                payload = json.loads(payload_text) if isinstance(payload_text, str) else payload_text
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or not _cassandra_payload_matches(payload, filters, project_id):
                continue
            scored.append((str(memory_id), _cosine_similarity(query_vector, [float(value) for value in vector])))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            {"id": memory_id, "score": float(score), "rank": index}
            for index, (memory_id, score) in enumerate(scored[: int(top_k)])
        ]
    except Exception as exc:
        _handle_azure_mysql_error(exc, settings, "search")
        return []
    finally:
        if connection is not None:
            _azure_mysql_close(connection)


def _baidu_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _baidu_settings(project_id)
    if not _baidu_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        _client, table = _baidu_table(settings)
        _pymochow, _credentials_module, _configuration_module, table_module = _baidu_modules()
        row = table_module.Row(
            id=str(memory["id"]),
            vector=[float(value) for value in embedding],
            metadata=_baidu_payload(memory, project_id),
        )
        table.upsert(rows=[row])
        return {"ok": True, "provider": "baidu", "operation": "upsert", "memory_id": str(memory["id"])}
    except Exception as exc:
        return _handle_baidu_error(exc, settings, "upsert")


def _baidu_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _baidu_settings(project_id)
    if not _baidu_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        _client, table = _baidu_table(settings)
        table.delete(primary_key={"id": str(memory_id)})
        return {"ok": True, "provider": "baidu", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_baidu_error(exc, settings, "delete")


def _baidu_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _baidu_settings(project_id)
    if not _baidu_enabled(settings):
        return []
    try:
        _client, table = _baidu_table(settings)
        _pymochow, _credentials_module, _configuration_module, table_module = _baidu_modules()
        request = table_module.VectorTopkSearchRequest(
            vector_field="vector",
            vector=table_module.FloatVector([float(value) for value in query_embedding]),
            limit=int(top_k),
            filter=_baidu_filter(filters, project_id),
            config=table_module.VectorSearchConfig(ef=200),
        )
        response = table.vector_search(request=request, projections=["id", "metadata"])
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(getattr(response, "rows", []) or []):
            row_data = item.get("row", {}) if isinstance(item, dict) else {}
            memory_id = row_data.get("id")
            if memory_id is None:
                continue
            hits.append({"id": str(memory_id), "score": float(item.get("score", 0.0)), "rank": index})
        return hits
    except Exception as exc:
        _handle_baidu_error(exc, settings, "search")
        return []


def _neptune_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _neptune_settings(project_id)
    if not _neptune_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        graph = _neptune_graph(settings)
        label = _neptune_label(settings)
        params = {
            "rows": [
                {
                    "node_id": str(memory["id"]),
                    "properties": _neptune_payload(memory, project_id),
                    "embedding": [float(value) for value in embedding],
                }
            ]
        }
        graph.query(
            f"UNWIND $rows AS row MERGE (n :{label} {{`~id`: row.node_id}}) "
            "ON CREATE SET n = row.properties ON MATCH SET n += row.properties",
            params,
        )
        graph.query(
            f"UNWIND $rows AS row MATCH (n :{label} {{`~id`: row.node_id}}) "
            "WITH n, row.embedding AS embedding "
            "CALL neptune.algo.vectors.upsert(n, embedding) YIELD success RETURN success",
            params,
        )
        return {"ok": True, "provider": "neptune_analytics", "operation": "upsert", "memory_id": str(memory["id"])}
    except Exception as exc:
        return _handle_neptune_error(exc, settings, "upsert")


def _neptune_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _neptune_settings(project_id)
    if not _neptune_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        graph = _neptune_graph(settings)
        label = _neptune_label(settings)
        graph.query(f"MATCH (n :{label}) WHERE n.`~id` = $node_id DETACH DELETE n", {"node_id": str(memory_id)})
        return {"ok": True, "provider": "neptune_analytics", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_neptune_error(exc, settings, "delete")


def _neptune_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _neptune_settings(project_id)
    if not _neptune_enabled(settings):
        return []
    try:
        graph = _neptune_graph(settings)
        label = _neptune_label(settings)
        filter_clause = _neptune_filter_clause(filters, project_id, label)
        query = (
            "CALL neptune.algo.vectors.topKByEmbeddingWithFiltering({"
            f"topK: {int(top_k)}, embedding: {[float(value) for value in query_embedding]}{filter_clause}"
            "}) YIELD node, score RETURN node as n, score"
        )
        return _neptune_parse_search(graph.query(query, {}))
    except Exception as exc:
        _handle_neptune_error(exc, settings, "search")
        return []


def _vertex_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _vertex_settings(project_id)
    if not _vertex_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        index, _endpoint, aiplatform_v1, _endpoint_module = _vertex_clients(settings)
        memory_id = str(memory["id"])
        datapoint = _vertex_datapoint(
            aiplatform_v1,
            memory_id,
            [float(value) for value in embedding],
            _vertex_payload(memory, project_id),
        )
        index.upsert_datapoints(datapoints=[datapoint])
        return {"ok": True, "provider": "vertex_ai_vector_search", "operation": "upsert", "memory_id": memory_id}
    except Exception as exc:
        return _handle_vertex_error(exc, settings, "upsert")


def _vertex_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _vertex_settings(project_id)
    if not _vertex_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        index, _endpoint, _aiplatform_v1, _endpoint_module = _vertex_clients(settings)
        index.remove_datapoints(datapoint_ids=[str(memory_id)])
        return {
            "ok": True,
            "provider": "vertex_ai_vector_search",
            "operation": "delete",
            "memory_id": str(memory_id),
        }
    except Exception as exc:
        return _handle_vertex_error(exc, settings, "delete")


def _vertex_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _vertex_settings(project_id)
    if not _vertex_enabled(settings):
        return []
    try:
        _index, endpoint, _aiplatform_v1, endpoint_module = _vertex_clients(settings)
        response = endpoint.find_neighbors(
            deployed_index_id=settings["deployment_index_id"],
            queries=[[float(value) for value in query_embedding]],
            num_neighbors=int(top_k),
            filter=_vertex_namespaces(endpoint_module, filters, project_id),
            return_full_datapoint=True,
        )
        return _vertex_parse_neighbors(response)
    except Exception as exc:
        _handle_vertex_error(exc, settings, "search")
        return []


def _pinecone_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _pinecone_settings(project_id)
    if not _pinecone_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/vectors/delete",
                headers=_pinecone_headers(settings),
                json={"namespace": settings["namespace"], "ids": [str(memory_id)]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "pinecone", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_pinecone_error(exc, settings, "delete")


def _pinecone_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _pinecone_settings(project_id)
    if not _pinecone_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/query",
                headers=_pinecone_headers(settings),
                json={
                    "namespace": settings["namespace"],
                    "vector": query_embedding,
                    "filter": _pinecone_filter(filters, project_id),
                    "topK": int(top_k),
                    "includeValues": False,
                    "includeMetadata": True,
                },
            )
        response.raise_for_status()
        payload = response.json()
        matches = payload.get("matches") if isinstance(payload, dict) else []
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(matches or []):
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            hits.append({"id": str(item["id"]), "score": float(item.get("score") or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_pinecone_error(exc, settings, "search")
        return []


def _upstash_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _upstash_settings(project_id)
    if not _upstash_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _upstash_endpoint(settings, "upsert"),
                headers=_upstash_headers(settings),
                json=[
                    {
                        "id": point_id,
                        "vector": embedding,
                        "metadata": _pinecone_metadata(memory, project_id),
                        "data": memory.get("memory") or "",
                    }
                ],
            )
        response.raise_for_status()
        return {"ok": True, "provider": "upstash_vector", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_upstash_error(exc, settings, "upsert")


def _upstash_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _upstash_settings(project_id)
    if not _upstash_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.request(
                "DELETE",
                _upstash_endpoint(settings, "delete"),
                headers=_upstash_headers(settings),
                json={"ids": [str(memory_id)]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "upstash_vector", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_upstash_error(exc, settings, "delete")


def _upstash_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _upstash_settings(project_id)
    if not _upstash_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _upstash_endpoint(settings, "query"),
                headers=_upstash_headers(settings),
                json={
                    "vector": query_embedding,
                    "filter": _upstash_filter(filters, project_id),
                    "topK": int(top_k),
                    "includeMetadata": True,
                    "includeVectors": False,
                    "includeData": False,
                },
            )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("result") if isinstance(payload, dict) else []
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(results or []):
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            hits.append({"id": str(item["id"]), "score": float(item.get("score") or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_upstash_error(exc, settings, "search")
        return []


def _elastic_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _elastic_settings(project_id)
    if not _elastic_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        _elastic_ensure_index(settings, len(embedding))
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.put(
                _elastic_endpoint(settings, f"/_doc/{quote(point_id, safe='')}?refresh=true"),
                headers=_elastic_headers(settings),
                json=_elastic_document(memory, embedding, project_id),
            )
        response.raise_for_status()
        return {"ok": True, "provider": "elasticsearch", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_elastic_error(exc, settings, "upsert")


def _elastic_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _elastic_settings(project_id)
    if not _elastic_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.delete(
                _elastic_endpoint(settings, f"/_doc/{quote(str(memory_id), safe='')}"),
                headers=_elastic_headers(settings),
            )
        if getattr(response, "status_code", 200) != 404:
            response.raise_for_status()
        return {"ok": True, "provider": "elasticsearch", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_elastic_error(exc, settings, "delete")


def _elastic_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _elastic_settings(project_id)
    if not _elastic_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _elastic_endpoint(settings, "/_search"),
                headers=_elastic_headers(settings),
                json={
                    "size": int(top_k),
                    "_source": False,
                    "query": {
                        "script_score": {
                            "query": {"bool": {"filter": _elastic_filter(filters, project_id)}},
                            "script": {
                                "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                                "params": {"query_vector": query_embedding},
                            },
                        }
                    },
                },
            )
        response.raise_for_status()
        payload = response.json()
        hits_payload = payload.get("hits", {}).get("hits", []) if isinstance(payload, dict) else []
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(hits_payload or []):
            if not isinstance(item, dict) or item.get("_id") is None:
                continue
            hits.append({"id": str(item["_id"]), "score": float(item.get("_score") or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_elastic_error(exc, settings, "search")
        return []


def _turbopuffer_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _turbopuffer_settings(project_id)
    if not _turbopuffer_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _turbopuffer_endpoint(settings),
                headers=_turbopuffer_headers(settings),
                json={
                    "upsert_rows": [_turbopuffer_row(memory, embedding, project_id)],
                    "distance_metric": "cosine_distance",
                },
            )
        response.raise_for_status()
        return {"ok": True, "provider": "turbopuffer", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_turbopuffer_error(exc, settings, "upsert")


def _turbopuffer_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _turbopuffer_settings(project_id)
    if not _turbopuffer_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _turbopuffer_endpoint(settings),
                headers=_turbopuffer_headers(settings),
                json={"deletes": [str(memory_id)]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "turbopuffer", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_turbopuffer_error(exc, settings, "delete")


def _turbopuffer_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _turbopuffer_settings(project_id)
    if not _turbopuffer_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _turbopuffer_endpoint(settings, "/query"),
                headers=_turbopuffer_headers(settings),
                json={
                    "rank_by": ["vector", "ANN", query_embedding],
                    "filters": _turbopuffer_filter(filters, project_id),
                    "limit": int(top_k),
                    "include_attributes": ["id"],
                },
            )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("rows") if isinstance(payload, dict) else []
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(rows or []):
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            distance = float(item.get("$dist") or 0.0)
            hits.append({"id": str(item["id"]), "score": 1.0 / (1.0 + max(distance, 0.0)), "rank": index})
        return hits
    except Exception as exc:
        _handle_turbopuffer_error(exc, settings, "search")
        return []


def _opensearch_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _opensearch_settings(project_id)
    if not _opensearch_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        _opensearch_ensure_index(settings, len(embedding))
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.put(
                _elastic_endpoint(settings, f"/_doc/{quote(point_id, safe='')}?refresh=true"),
                headers=_opensearch_headers(settings),
                json=_turbopuffer_row(memory, embedding, project_id),
            )
        response.raise_for_status()
        return {"ok": True, "provider": "opensearch", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_opensearch_error(exc, settings, "upsert")


def _opensearch_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _opensearch_settings(project_id)
    if not _opensearch_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.delete(
                _elastic_endpoint(settings, f"/_doc/{quote(str(memory_id), safe='')}"),
                headers=_opensearch_headers(settings),
            )
        if getattr(response, "status_code", 200) != 404:
            response.raise_for_status()
        return {"ok": True, "provider": "opensearch", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_opensearch_error(exc, settings, "delete")


def _opensearch_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _opensearch_settings(project_id)
    if not _opensearch_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _elastic_endpoint(settings, "/_search"),
                headers=_opensearch_headers(settings),
                json={
                    "size": int(top_k),
                    "_source": False,
                    "query": {
                        "script_score": {
                            "query": {"bool": {"filter": _elastic_filter(filters, project_id)}},
                            "script": {
                                "source": "knn_score",
                                "lang": "knn",
                                "params": {
                                    "field": "vector",
                                    "query_value": query_embedding,
                                    "space_type": "cosinesimil",
                                },
                            },
                        }
                    },
                },
            )
        response.raise_for_status()
        payload = response.json()
        hits_payload = payload.get("hits", {}).get("hits", []) if isinstance(payload, dict) else []
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(hits_payload or []):
            if not isinstance(item, dict) or item.get("_id") is None:
                continue
            hits.append({"id": str(item["_id"]), "score": float(item.get("_score") or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_opensearch_error(exc, settings, "search")
        return []


def _weaviate_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _weaviate_settings(project_id)
    if not _weaviate_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        _weaviate_ensure_schema(settings)
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.put(
                f"{settings['url']}/v1/objects/{settings['class_name']}/{quote(point_id, safe='')}",
                headers=_weaviate_headers(settings),
                json={
                    "class": settings["class_name"],
                    "id": point_id,
                    "properties": _weaviate_properties(memory, project_id),
                    "vector": embedding,
                },
            )
        response.raise_for_status()
        return {"ok": True, "provider": "weaviate", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_weaviate_error(exc, settings, "upsert")


def _weaviate_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _weaviate_settings(project_id)
    if not _weaviate_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.delete(
                f"{settings['url']}/v1/objects/{settings['class_name']}/{quote(str(memory_id), safe='')}",
                headers=_weaviate_headers(settings),
            )
        if getattr(response, "status_code", 200) != 404:
            response.raise_for_status()
        return {"ok": True, "provider": "weaviate", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_weaviate_error(exc, settings, "delete")


def _weaviate_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _weaviate_settings(project_id)
    if not _weaviate_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/v1/graphql",
                headers=_weaviate_headers(settings),
                json={"query": _weaviate_query(settings, query_embedding, filters, top_k, project_id)},
            )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", {}).get("Get", {}).get(settings["class_name"], []) if isinstance(payload, dict) else []
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(rows or []):
            if not isinstance(item, dict):
                continue
            additional = item.get("_additional") or {}
            memory_id = item.get("memory_id") or additional.get("id")
            if memory_id is None:
                continue
            if additional.get("certainty") is not None:
                score = float(additional["certainty"])
            else:
                distance = float(additional.get("distance") or 0.0)
                score = 1.0 / (1.0 + max(distance, 0.0))
            hits.append({"id": str(memory_id), "score": score, "rank": index})
        return hits
    except Exception as exc:
        _handle_weaviate_error(exc, settings, "search")
        return []


def _chroma_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _chroma_settings(project_id)
    if not _chroma_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        collection_id = _chroma_collection_id(settings)
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/api/v1/collections/{quote(collection_id, safe='')}/upsert",
                headers=_chroma_headers(settings),
                json={
                    "ids": [point_id],
                    "embeddings": [embedding],
                    "metadatas": [_chroma_metadata(memory, project_id)],
                    "documents": [memory.get("memory") or ""],
                },
            )
        response.raise_for_status()
        return {"ok": True, "provider": "chroma", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_chroma_error(exc, settings, "upsert")


def _chroma_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _chroma_settings(project_id)
    if not _chroma_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        collection_id = _chroma_collection_id(settings)
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/api/v1/collections/{quote(collection_id, safe='')}/delete",
                headers=_chroma_headers(settings),
                json={"ids": [str(memory_id)]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "chroma", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_chroma_error(exc, settings, "delete")


def _chroma_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _chroma_settings(project_id)
    if not _chroma_enabled(settings):
        return []
    try:
        collection_id = _chroma_collection_id(settings)
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/api/v1/collections/{quote(collection_id, safe='')}/query",
                headers=_chroma_headers(settings),
                json={
                    "query_embeddings": [query_embedding],
                    "where": _chroma_where(filters, project_id),
                    "n_results": int(top_k),
                    "include": ["metadatas", "distances"],
                },
            )
        response.raise_for_status()
        payload = response.json()
        ids = payload.get("ids", [])
        distances = payload.get("distances", [])
        ids = ids[0] if ids and isinstance(ids[0], list) else ids
        distances = distances[0] if distances and isinstance(distances[0], list) else distances
        hits: list[dict[str, Any]] = []
        for index, memory_id in enumerate(ids or []):
            distance = distances[index] if isinstance(distances, list) and index < len(distances) else 0.0
            hits.append({"id": str(memory_id), "score": 1.0 / (1.0 + max(float(distance or 0.0), 0.0)), "rank": index})
        return hits
    except Exception as exc:
        _handle_chroma_error(exc, settings, "search")
        return []


def _milvus_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _milvus_settings(project_id)
    if not _milvus_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        _milvus_ensure_collection(settings, len(embedding))
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/v2/vectordb/entities/upsert",
                headers=_milvus_headers(settings),
                json={"collectionName": settings["collection"], "data": [_milvus_row(memory, embedding, project_id)]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "milvus", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_milvus_error(exc, settings, "upsert")


def _milvus_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _milvus_settings(project_id)
    if not _milvus_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/v2/vectordb/entities/delete",
                headers=_milvus_headers(settings),
                json={"collectionName": settings["collection"], "filter": f"id in [{_milvus_quote(str(memory_id))}]"},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "milvus", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_milvus_error(exc, settings, "delete")


def _milvus_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _milvus_settings(project_id)
    if not _milvus_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/v2/vectordb/entities/search",
                headers=_milvus_headers(settings),
                json={
                    "collectionName": settings["collection"],
                    "data": [query_embedding],
                    "annsField": "vector",
                    "filter": _milvus_filter(filters, project_id),
                    "limit": int(top_k),
                    "outputFields": ["id"],
                    "searchParams": {"metric_type": "COSINE"},
                },
            )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else []
        if rows and isinstance(rows[0], list):
            rows = rows[0]
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(rows or []):
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            score = item.get("distance", item.get("score", 0.0))
            hits.append({"id": str(item["id"]), "score": float(score or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_milvus_error(exc, settings, "search")
        return []


def _mongodb_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _mongodb_settings(project_id)
    if not _mongodb_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    client = None
    try:
        client, collection = _mongodb_collection(settings)
        _mongodb_ensure_index(collection, settings, len(embedding))
        collection.replace_one({"_id": point_id}, _mongodb_document(memory, embedding, project_id), upsert=True)
        return {"ok": True, "provider": "mongodb", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_mongodb_error(exc, settings, "upsert")
    finally:
        if client is not None:
            client.close()


def _mongodb_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _mongodb_settings(project_id)
    if not _mongodb_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    client = None
    try:
        client, collection = _mongodb_collection(settings)
        collection.delete_one({"_id": str(memory_id), "payload.project_id": project_id})
        return {"ok": True, "provider": "mongodb", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_mongodb_error(exc, settings, "delete")
    finally:
        if client is not None:
            client.close()


def _mongodb_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _mongodb_settings(project_id)
    if not _mongodb_enabled(settings):
        return []
    client = None
    try:
        client, collection = _mongodb_collection(settings)
        rows = collection.aggregate(_mongodb_pipeline(settings, query_embedding, filters, top_k, project_id))
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(rows or []):
            if not isinstance(item, dict) or item.get("_id") is None:
                continue
            hits.append({"id": str(item["_id"]), "score": float(item.get("score") or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_mongodb_error(exc, settings, "search")
        return []
    finally:
        if client is not None:
            client.close()


def _azure_search_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _azure_search_settings(project_id)
    if not _azure_search_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        _azure_search_ensure_index(settings, len(embedding))
        document = _azure_search_document(memory, embedding, project_id)
        document["@search.action"] = "mergeOrUpload"
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _azure_search_index_documents_url(settings),
                headers=_azure_search_headers(settings),
                json={"value": [document]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "azure_ai_search", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_azure_search_error(exc, settings, "upsert")


def _azure_search_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _azure_search_settings(project_id)
    if not _azure_search_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _azure_search_index_documents_url(settings),
                headers=_azure_search_headers(settings),
                json={"value": [{"@search.action": "delete", "id": str(memory_id)}]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "azure_ai_search", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_azure_search_error(exc, settings, "delete")


def _azure_search_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _azure_search_settings(project_id)
    if not _azure_search_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                _azure_search_query_url(settings),
                headers=_azure_search_headers(settings),
                json={
                    "vectorQueries": [
                        {
                            "kind": "vector",
                            "vector": [float(value) for value in query_embedding],
                            "fields": "vector",
                            "k": int(top_k),
                        }
                    ],
                    "filter": _azure_search_filter(filters, project_id),
                    "select": "id",
                    "top": int(top_k),
                },
            )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("value") if isinstance(payload, dict) else []
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(rows or []):
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            hits.append({"id": str(item["id"]), "score": float(item.get("@search.score") or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_azure_search_error(exc, settings, "search")
        return []


def _databricks_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _databricks_settings(project_id)
    if not _databricks_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    try:
        _databricks_ensure_index(settings, len(embedding))
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{_databricks_index_path(settings)}/upsert-data",
                headers=_databricks_headers(settings),
                json={"inputs_json": json_dumps([_databricks_row(memory, embedding, project_id)])},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "databricks", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_databricks_error(exc, settings, "upsert")


def _databricks_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _databricks_settings(project_id)
    if not _databricks_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.request(
                "DELETE",
                f"{_databricks_index_path(settings)}/delete-data",
                headers=_databricks_headers(settings),
                json={"primary_keys": [str(memory_id)]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "databricks", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_databricks_error(exc, settings, "delete")


def _databricks_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _databricks_settings(project_id)
    if not _databricks_enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{_databricks_index_path(settings)}/query",
                headers=_databricks_headers(settings),
                json={
                    "columns": _databricks_columns(),
                    "filters_json": _databricks_filters_json(filters, project_id),
                    "num_results": int(top_k),
                    "query_type": settings["query_type"],
                    "query_vector": [float(value) for value in query_embedding],
                },
            )
        response.raise_for_status()
        payload = response.json()
        return _databricks_hits(payload) if isinstance(payload, dict) else []
    except Exception as exc:
        _handle_databricks_error(exc, settings, "search")
        return []


def _pgvector_ensure_table(cursor: Any, settings: dict[str, Any], dimensions: int) -> None:
    if not settings.get("auto_create"):
        return
    size = dimensions or int(settings["dimensions"])
    table = settings["table"]
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id text PRIMARY KEY,
            project_id text NOT NULL,
            memory text,
            user_id text,
            agent_id text,
            app_id text,
            run_id text,
            categories jsonb NOT NULL DEFAULT '[]'::jsonb,
            metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            embedding vector({size}) NOT NULL,
            created_at text,
            updated_at text
        )
        """
    )
    cursor.execute(f"CREATE INDEX IF NOT EXISTS {table.strip(chr(34))}_project_idx ON {table} (project_id)")


def _pgvector_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _pgvector_settings(project_id)
    if not _pgvector_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        psycopg = _psycopg_module()
        table = settings["table"]
        vector = _pg_vector_literal(embedding)
        with psycopg.connect(settings["url"], connect_timeout=max(int(settings["timeout"]), 1)) as conn:
            with conn.cursor() as cursor:
                _pgvector_ensure_table(cursor, settings, len(embedding))
                cursor.execute(
                    f"""
                    INSERT INTO {table} (
                        id, project_id, memory, user_id, agent_id, app_id, run_id,
                        categories, metadata, embedding, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::vector, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        project_id = EXCLUDED.project_id,
                        memory = EXCLUDED.memory,
                        user_id = EXCLUDED.user_id,
                        agent_id = EXCLUDED.agent_id,
                        app_id = EXCLUDED.app_id,
                        run_id = EXCLUDED.run_id,
                        categories = EXCLUDED.categories,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        str(memory["id"]),
                        project_id,
                        memory.get("memory"),
                        memory.get("user_id"),
                        memory.get("agent_id"),
                        memory.get("app_id"),
                        memory.get("run_id"),
                        json_dumps(memory.get("categories", [])),
                        json_dumps(memory.get("metadata", {})),
                        vector,
                        memory.get("created_at"),
                        memory.get("updated_at"),
                    ),
                )
        return {"ok": True, "provider": settings["provider"], "operation": "upsert", "memory_id": str(memory["id"])}
    except Exception as exc:
        return _handle_pgvector_error(exc, settings, "upsert")


def _pgvector_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _pgvector_settings(project_id)
    if not _pgvector_enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        psycopg = _psycopg_module()
        with psycopg.connect(settings["url"], connect_timeout=max(int(settings["timeout"]), 1)) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {settings['table']} WHERE id = %s AND project_id = %s",
                    (str(memory_id), project_id),
                )
        return {"ok": True, "provider": settings["provider"], "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_pgvector_error(exc, settings, "delete")


def _pgvector_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _pgvector_settings(project_id)
    if not _pgvector_enabled(settings):
        return []
    try:
        psycopg = _psycopg_module()
        vector = _pg_vector_literal(query_embedding)
        where = ["project_id = %s"]
        params: list[Any] = [project_id]
        for field in ("user_id", "agent_id", "app_id", "run_id"):
            value = filters.get(field)
            if isinstance(value, str) and value:
                where.append(f"{field} = %s")
                params.append(value)
        sql = (
            f"SELECT id, 1 - (embedding <=> %s::vector) AS score "
            f"FROM {settings['table']} "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY embedding <=> %s::vector "
            f"LIMIT %s"
        )
        with psycopg.connect(settings["url"], connect_timeout=max(int(settings["timeout"]), 1)) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (vector, *params, vector, int(top_k)))
                rows = cursor.fetchall()
        hits: list[dict[str, Any]] = []
        for index, row in enumerate(rows or []):
            memory_id = row["id"] if isinstance(row, dict) else row[0]
            score = row["score"] if isinstance(row, dict) else row[1]
            hits.append({"id": str(memory_id), "score": float(score or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_pgvector_error(exc, settings, "search")
        return []


def vector_upsert_memory(memory: dict[str, Any], embedding: list[float], project_id: str) -> dict[str, Any]:
    settings = _qdrant_settings(project_id)
    if settings["provider"] == "pgvector":
        return _pgvector_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "supabase":
        return _pgvector_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "s3_vectors":
        return _s3_vectors_upsert_memory(memory, embedding, project_id)
    if settings["provider"] in {"redis", "valkey"}:
        return _redis_like_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "faiss":
        return _faiss_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "cassandra":
        return _cassandra_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "azure_mysql":
        return _azure_mysql_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "baidu":
        return _baidu_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "neptune_analytics":
        return _neptune_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "vertex_ai_vector_search":
        return _vertex_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "pinecone":
        return _pinecone_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "upstash_vector":
        return _upstash_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "elasticsearch":
        return _elastic_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "turbopuffer":
        return _turbopuffer_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "opensearch":
        return _opensearch_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "weaviate":
        return _weaviate_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "chroma":
        return _chroma_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "milvus":
        return _milvus_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "mongodb":
        return _mongodb_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "azure_ai_search":
        return _azure_search_upsert_memory(memory, embedding, project_id)
    if settings["provider"] == "databricks":
        return _databricks_upsert_memory(memory, embedding, project_id)
    if not _enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    point_id = str(memory["id"])
    payload = {
        "project_id": project_id,
        "memory": memory.get("memory"),
        "user_id": memory.get("user_id"),
        "agent_id": memory.get("agent_id"),
        "app_id": memory.get("app_id"),
        "run_id": memory.get("run_id"),
        "categories": memory.get("categories", []),
        "metadata": memory.get("metadata", {}),
        "created_at": memory.get("created_at"),
        "updated_at": memory.get("updated_at"),
    }
    try:
        _ensure_collection(settings, len(embedding))
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.put(
                f"{settings['url']}/collections/{settings['collection']}/points?wait=true",
                headers=_headers(settings),
                json={"points": [{"id": point_id, "vector": embedding, "payload": payload}]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "qdrant", "operation": "upsert", "memory_id": point_id}
    except Exception as exc:
        return _handle_error(exc, settings, "upsert")


def vector_delete_memory(memory_id: str, project_id: str) -> dict[str, Any]:
    settings = _qdrant_settings(project_id)
    if settings["provider"] == "pgvector":
        return _pgvector_delete_memory(memory_id, project_id)
    if settings["provider"] == "supabase":
        return _pgvector_delete_memory(memory_id, project_id)
    if settings["provider"] == "s3_vectors":
        return _s3_vectors_delete_memory(memory_id, project_id)
    if settings["provider"] in {"redis", "valkey"}:
        return _redis_like_delete_memory(memory_id, project_id)
    if settings["provider"] == "faiss":
        return _faiss_delete_memory(memory_id, project_id)
    if settings["provider"] == "cassandra":
        return _cassandra_delete_memory(memory_id, project_id)
    if settings["provider"] == "azure_mysql":
        return _azure_mysql_delete_memory(memory_id, project_id)
    if settings["provider"] == "baidu":
        return _baidu_delete_memory(memory_id, project_id)
    if settings["provider"] == "neptune_analytics":
        return _neptune_delete_memory(memory_id, project_id)
    if settings["provider"] == "vertex_ai_vector_search":
        return _vertex_delete_memory(memory_id, project_id)
    if settings["provider"] == "pinecone":
        return _pinecone_delete_memory(memory_id, project_id)
    if settings["provider"] == "upstash_vector":
        return _upstash_delete_memory(memory_id, project_id)
    if settings["provider"] == "elasticsearch":
        return _elastic_delete_memory(memory_id, project_id)
    if settings["provider"] == "turbopuffer":
        return _turbopuffer_delete_memory(memory_id, project_id)
    if settings["provider"] == "opensearch":
        return _opensearch_delete_memory(memory_id, project_id)
    if settings["provider"] == "weaviate":
        return _weaviate_delete_memory(memory_id, project_id)
    if settings["provider"] == "chroma":
        return _chroma_delete_memory(memory_id, project_id)
    if settings["provider"] == "milvus":
        return _milvus_delete_memory(memory_id, project_id)
    if settings["provider"] == "mongodb":
        return _mongodb_delete_memory(memory_id, project_id)
    if settings["provider"] == "azure_ai_search":
        return _azure_search_delete_memory(memory_id, project_id)
    if settings["provider"] == "databricks":
        return _databricks_delete_memory(memory_id, project_id)
    if not _enabled(settings):
        return {"ok": True, "provider": settings["provider"], "skipped": True}
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/collections/{settings['collection']}/points/delete?wait=true",
                headers=_headers(settings),
                json={"points": [str(memory_id)]},
            )
        response.raise_for_status()
        return {"ok": True, "provider": "qdrant", "operation": "delete", "memory_id": str(memory_id)}
    except Exception as exc:
        return _handle_error(exc, settings, "delete")


def vector_search_memories(
    query_embedding: list[float],
    filters: dict[str, Any],
    top_k: int,
    project_id: str,
) -> list[dict[str, Any]]:
    settings = _qdrant_settings(project_id)
    if settings["provider"] == "pgvector":
        return _pgvector_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "supabase":
        return _pgvector_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "s3_vectors":
        return _s3_vectors_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] in {"redis", "valkey"}:
        return _redis_like_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "faiss":
        return _faiss_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "cassandra":
        return _cassandra_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "azure_mysql":
        return _azure_mysql_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "baidu":
        return _baidu_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "neptune_analytics":
        return _neptune_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "vertex_ai_vector_search":
        return _vertex_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "pinecone":
        return _pinecone_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "upstash_vector":
        return _upstash_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "elasticsearch":
        return _elastic_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "turbopuffer":
        return _turbopuffer_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "opensearch":
        return _opensearch_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "weaviate":
        return _weaviate_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "chroma":
        return _chroma_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "milvus":
        return _milvus_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "mongodb":
        return _mongodb_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "azure_ai_search":
        return _azure_search_search_memories(query_embedding, filters, top_k, project_id)
    if settings["provider"] == "databricks":
        return _databricks_search_memories(query_embedding, filters, top_k, project_id)
    if not _enabled(settings):
        return []
    try:
        with httpx.Client(timeout=float(settings["timeout"])) as client:
            response = client.post(
                f"{settings['url']}/collections/{settings['collection']}/points/search",
                headers=_headers(settings),
                json={
                    "vector": query_embedding,
                    "limit": top_k,
                    "with_payload": True,
                    "filter": _payload_filter(filters, project_id),
                },
            )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("result") if isinstance(payload, dict) else []
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(results or []):
            if not isinstance(item, dict):
                continue
            memory_id = item.get("id") or (item.get("payload") or {}).get("id")
            if memory_id is None:
                continue
            hits.append({"id": str(memory_id), "score": float(item.get("score") or 0.0), "rank": index})
        return hits
    except Exception as exc:
        _handle_error(exc, settings, "search")
        return []
