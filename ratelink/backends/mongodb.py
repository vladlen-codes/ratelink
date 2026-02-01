import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from ..core.abstractions import Backend
from ..core.types import RateLimitState, BackendError

try:
    import pymongo
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import PyMongoError, DuplicateKeyError
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

class MongoDBBackend(Backend):
    def __init__(
        self,
        connection_string: str = "mongodb://localhost:27017/",
        database: str = "rate_limits",
        collection: str = "limits",
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_source: str = "admin",
        ssl: bool = False,
        connect_timeout: int = 10000,
        server_selection_timeout: int = 5000,
        auto_create_indexes: bool = True,
    ) -> None:
        if not PYMONGO_AVAILABLE:
            raise ImportError(
                "pymongo not installed. Install with: pip install pymongo"
            )
        client_params: Dict[str, Any] = {
            "connectTimeoutMS": connect_timeout,
            "serverSelectionTimeoutMS": server_selection_timeout,
        }
        if username and password:
            client_params["username"] = username
            client_params["password"] = password
            client_params["authSource"] = auth_source
        if ssl:
            client_params["tls"] = True
        try:
            self.client = MongoClient(connection_string, **client_params)
            self.db = self.client[database]
            self.collection = self.db[collection]
            self.client.admin.command("ping")
        except Exception as e:
            raise BackendError(f"Failed to connect to MongoDB: {e}")
        if auto_create_indexes:
            self._create_indexes()

    def _create_indexes(self) -> None:
        try:
            self.collection.create_index([("key", ASCENDING)], unique=True)
            self.collection.create_index(
                [("reset_at", ASCENDING)], expireAfterSeconds=0
            )
            self.collection.create_index([("updated_at", ASCENDING)])
        except Exception as e:
            raise BackendError(f"Failed to create MongoDB indexes: {e}")

    def check(self, key: str) -> RateLimitState:
        try:
            doc = self.collection.find_one(
                {"key": key, "reset_at": {"$gt": datetime.now()}}
            )
            if doc is None:
                return RateLimitState(
                    limit=0,
                    remaining=0,
                    reset_at=datetime.now(),
                    retry_after=0.0,
                    violated=False,
                    metadata={"backend": "mongodb"},
                )
            remaining = doc.get("remaining", 0)
            reset_at = doc.get("reset_at", datetime.now())
            retry_after = 0.0
            if remaining <= 0:
                retry_after = max(0.0, (reset_at - datetime.now()).total_seconds())
            return RateLimitState(
                limit=doc.get("limit_value", 0),
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
                violated=remaining <= 0,
                metadata=doc.get("metadata", {"backend": "mongodb"}),
            )
        except Exception as e:
            raise BackendError(f"MongoDB check failed: {e}")

    def consume(self, key: str, weight: int) -> RateLimitState:
        if weight <= 0:
            raise ValueError("weight must be positive")
        try:
            current_time = datetime.now()
            reset_at = current_time + timedelta(seconds=3600)
            result = self.collection.find_one_and_update(
                {
                    "key": key,
                    "reset_at": {"$gt": current_time},
                    "remaining": {"$gte": weight},
                },
                {
                    "$inc": {"remaining": -weight},
                    "$set": {"updated_at": current_time},
                },
                return_document=pymongo.ReturnDocument.AFTER,
            )
            if result is not None:
                return RateLimitState(
                    limit=result["limit_value"],
                    remaining=result["remaining"],
                    reset_at=result["reset_at"],
                    retry_after=0.0,
                    violated=False,
                    metadata=result.get("metadata", {"backend": "mongodb"}),
                )
            else:
                existing = self.collection.find_one({"key": key})
                if existing is None or existing["reset_at"] <= current_time:
                    limit_value = 10000
                    remaining = limit_value - weight
                    doc = {
                        "key": key,
                        "limit_value": limit_value,
                        "remaining": remaining,
                        "reset_at": reset_at,
                        "created_at": current_time,
                        "updated_at": current_time,
                        "metadata": {"backend": "mongodb"},
                    }
                    try:
                        self.collection.insert_one(doc)
                    except DuplicateKeyError:
                        return self.consume(key, weight)
                    return RateLimitState(
                        limit=limit_value,
                        remaining=remaining,
                        reset_at=reset_at,
                        retry_after=0.0,
                        violated=False,
                        metadata={"backend": "mongodb"},
                    )
                else:
                    retry_after = max(
                        0.0, (existing["reset_at"] - current_time).total_seconds()
                    )
                    return RateLimitState(
                        limit=existing["limit_value"],
                        remaining=existing["remaining"],
                        reset_at=existing["reset_at"],
                        retry_after=retry_after,
                        violated=True,
                        metadata=existing.get("metadata", {"backend": "mongodb"}),
                    )

        except Exception as e:
            raise BackendError(f"MongoDB consume failed: {e}")

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: Optional[str] = None) -> None:
        try:
            if key is None:
                self.collection.delete_many({})
            else:
                self.collection.delete_one({"key": key})

        except Exception as e:
            raise BackendError(f"MongoDB reset failed: {e}")

    async def check_async(self, key: str) -> RateLimitState:
        return self.check(key)

    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        return self.consume(key, weight)

    async def peek_async(self, key: str) -> RateLimitState:
        return self.peek(key)

    async def reset_async(self, key: Optional[str] = None) -> None:
        self.reset(key)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
