"""Strict in-process JSON adapter. HTTP mounting and authentication are external."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
import sqlite3

from .runtime_types import CareError, CustomerEvent, TrustedRequestContext, canonical


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status: int
    body: dict


SCHEMAS = {
    "open_chat": ({"order_id", "request_id"}, set()),
    "handle_message": ({"session_id", "message_id", "text"}, {"reply_to"}),
    "prepare_cancel": ({"session_id", "request_id"}, set()),
    "confirm_cancel": ({"confirmation_id", "request_id", "reply_to", "confirmed"}, set()),
    "request_handoff": ({"session_id", "request_id"}, set()),
    "get_messages": ({"session_id"}, set()),
    "get_trace": ({"session_id"}, set()),
    "get_handoffs": (set(), set()),
}


class CareApi:
    def __init__(self, harness):
        self.harness = harness

    async def handle(self, operation: str, payload: Mapping[str, object], ctx: TrustedRequestContext) -> ApiResponse:
        try:
            if not isinstance(ctx, TrustedRequestContext) or not ctx.principal_id:
                raise CareError("unauthenticated", 401)
            if not isinstance(operation, str) or operation not in SCHEMAS or not isinstance(payload, Mapping):
                raise CareError("invalid_operation", 400)
            required, optional = SCHEMAS[operation]
            if not required <= payload.keys() or not payload.keys() <= required | optional:
                raise CareError("invalid_payload", 400)
            for key, value in payload.items():
                if key == "confirmed":
                    if type(value) is not bool:
                        raise CareError("invalid_payload", 400)
                    continue
                if key == "reply_to" and value is None:
                    continue
                if not isinstance(value, str) or not value.strip() or len(value) > (4000 if key == "text" else 200):
                    raise CareError("invalid_payload", 400)
            if operation == "prepare_cancel":
                result = await self.harness._process_event(payload["session_id"],
                    CustomerEvent("prepare_cancel", payload["request_id"]), ctx)
            else:
                result = await getattr(self.harness, operation)(**payload, ctx=ctx)
            return ApiResponse(200, json.loads(canonical(result)))
        except CareError as error:
            return ApiResponse(error.status, {"error": error.code})
        except ValueError:
            return ApiResponse(400, {"error": "invalid_payload"})
        except (sqlite3.DatabaseError, OSError):
            return ApiResponse(503, {"error": "service_error"})
