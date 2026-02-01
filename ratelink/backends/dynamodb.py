import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from ..core.abstractions import Backend
from ..core.types import RateLimitState, BackendError

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class DynamoDBBackend(Backend):
    def __init__(
        self,
        region: str = "us-east-1",
        table_name: str = "rate_limits",
        billing_mode: str = "PAY_PER_REQUEST",
        ttl_attribute: str = "ttl",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,  # For local testing
        auto_create_table: bool = True,
        consistent_reads: bool = False,
    ) -> None:
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 not installed. Install with: pip install boto3"
            )
        self.table_name = table_name
        self.ttl_attribute = ttl_attribute
        self.billing_mode = billing_mode
        self.consistent_reads = consistent_reads
        session_params = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            session_params["aws_access_key_id"] = aws_access_key_id
            session_params["aws_secret_access_key"] = aws_secret_access_key
        if endpoint_url:
            session_params["endpoint_url"] = endpoint_url
        try:
            self.dynamodb = boto3.resource("dynamodb", **session_params)
            self.client = boto3.client("dynamodb", **session_params)
        except Exception as e:
            raise BackendError(f"Failed to create DynamoDB client: {e}")
        if auto_create_table:
            self._create_table()
        self.table = self.dynamodb.Table(table_name)

    def _create_table(self) -> None:
        try:
            self.client.describe_table(TableName=self.table_name)
            return
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise BackendError(f"Error checking table: {e}")
        try:
            table_params: Dict[str, Any] = {
                "TableName": self.table_name,
                "KeySchema": [{"AttributeName": "key", "KeyType": "HASH"}],
                "AttributeDefinitions": [
                    {"AttributeName": "key", "AttributeType": "S"}
                ],
            }
            if self.billing_mode == "PAY_PER_REQUEST":
                table_params["BillingMode"] = "PAY_PER_REQUEST"
            else:
                table_params["BillingMode"] = "PROVISIONED"
                table_params["ProvisionedThroughput"] = {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                }
            table = self.dynamodb.create_table(**table_params)
            table.wait_until_exists()
            self.client.update_time_to_live(
                TableName=self.table_name,
                TimeToLiveSpecification={
                    "Enabled": True,
                    "AttributeName": self.ttl_attribute,
                },
            )

        except Exception as e:
            raise BackendError(f"Failed to create DynamoDB table: {e}")

    def check(self, key: str) -> RateLimitState:
        try:
            response = self.table.get_item(
                Key={"key": key}, ConsistentRead=self.consistent_reads
            )
            if "Item" not in response:
                return RateLimitState(
                    limit=0,
                    remaining=0,
                    reset_at=datetime.now(),
                    retry_after=0.0,
                    violated=False,
                    metadata={"backend": "dynamodb"},
                )
            item = response["Item"]
            ttl = item.get(self.ttl_attribute, 0)
            if ttl > 0 and ttl < time.time():
                return RateLimitState(
                    limit=0,
                    remaining=0,
                    reset_at=datetime.now(),
                    retry_after=0.0,
                    violated=False,
                    metadata={"backend": "dynamodb"},
                )
            remaining = item.get("remaining", 0)
            limit_value = item.get("limit_value", 0)
            reset_timestamp = item.get("reset_at", time.time())
            reset_at = datetime.fromtimestamp(reset_timestamp)
            retry_after = 0.0
            if remaining <= 0:
                retry_after = max(0.0, reset_timestamp - time.time())
            return RateLimitState(
                limit=limit_value,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
                violated=remaining <= 0,
                metadata=item.get("metadata", {"backend": "dynamodb"}),
            )
        except Exception as e:
            raise BackendError(f"DynamoDB check failed: {e}")

    def consume(self, key: str, weight: int) -> RateLimitState:
        if weight <= 0:
            raise ValueError("weight must be positive")
        try:
            current_time = time.time()
            reset_timestamp = current_time + 3600
            ttl = int(reset_timestamp) + 86400
            try:
                response = self.table.update_item(
                    Key={"key": key},
                    UpdateExpression="""
                        SET remaining = remaining - :weight,
                            updated_at = :now
                    """,
                    ConditionExpression="remaining >= :weight AND #ttl > :now",
                    ExpressionAttributeNames={"#ttl": self.ttl_attribute},
                    ExpressionAttributeValues={
                        ":weight": weight,
                        ":now": current_time,
                    },
                    ReturnValues="ALL_NEW",
                )
                item = response["Attributes"]
                return RateLimitState(
                    limit=item["limit_value"],
                    remaining=item["remaining"],
                    reset_at=datetime.fromtimestamp(item["reset_at"]),
                    retry_after=0.0,
                    violated=False,
                    metadata=item.get("metadata", {"backend": "dynamodb"}),
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    state = self.check(key)
                    if state.limit == 0:
                        limit_value = 10000
                        remaining = limit_value - weight
                        self.table.put_item(
                            Item={
                                "key": key,
                                "limit_value": limit_value,
                                "remaining": remaining,
                                "reset_at": reset_timestamp,
                                "created_at": current_time,
                                "updated_at": current_time,
                                self.ttl_attribute: ttl,
                                "metadata": {"backend": "dynamodb"},
                            }
                        )
                        return RateLimitState(
                            limit=limit_value,
                            remaining=remaining,
                            reset_at=datetime.fromtimestamp(reset_timestamp),
                            retry_after=0.0,
                            violated=False,
                            metadata={"backend": "dynamodb"},
                        )
                    else:
                        return RateLimitState(
                            limit=state.limit,
                            remaining=state.remaining,
                            reset_at=state.reset_at,
                            retry_after=state.retry_after,
                            violated=True,
                            metadata=state.metadata,
                        )
                else:
                    raise

        except Exception as e:
            raise BackendError(f"DynamoDB consume failed: {e}")

    def peek(self, key: str) -> RateLimitState:
        return self.check(key)

    def reset(self, key: Optional[str] = None) -> None:
        try:
            if key is None:
                scan_kwargs = {"ProjectionExpression": "key"}
                done = False
                start_key = None
                while not done:
                    if start_key:
                        scan_kwargs["ExclusiveStartKey"] = start_key
                    response = self.table.scan(**scan_kwargs)
                    items = response.get("Items", [])
                    with self.table.batch_writer() as batch:
                        for item in items:
                            batch.delete_item(Key={"key": item["key"]})
                    start_key = response.get("LastEvaluatedKey", None)
                    done = start_key is None
            else:
                self.table.delete_item(Key={"key": key})

        except Exception as e:
            raise BackendError(f"DynamoDB reset failed: {e}")

    async def check_async(self, key: str) -> RateLimitState:
        return self.check(key)

    async def consume_async(self, key: str, weight: int) -> RateLimitState:
        return self.consume(key, weight)

    async def peek_async(self, key: str) -> RateLimitState:
        return self.peek(key)

    async def reset_async(self, key: Optional[str] = None) -> None:
        self.reset(key)
