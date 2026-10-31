"""Strict in-process JSON adapter. HTTP mounting and authentication are external."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
import sqlite3

from .runtime_types import CareError, CustomerEvent, TrustedRequestContext, canonical
from .storage_port import StorageError


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
            if (not isinstance(ctx, TrustedRequestContext)
                    or not isinstance(ctx.principal_id, str) or not ctx.principal_id.strip()
                    or type(ctx.staff_permissions) is not frozenset
                    or any(not isinstance(p, str) or not p.strip() for p in ctx.staff_permissions)):
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
            # Public customer operations never inherit staff read capabilities.
            if "session_id" in payload and operation != "get_trace":
                state = await self.harness.session(payload["session_id"])
                if state.principal_id != ctx.principal_id:
                    raise CareError("not_found", 404)
            if operation == "prepare_cancel":
                result = await self.harness._process_event(payload["session_id"],
                    CustomerEvent("prepare_cancel", payload["request_id"]), ctx)
            else:
                result = await getattr(self.harness, operation)(**payload, ctx=ctx)
            return ApiResponse(200, json.loads(canonical(result)))
        except CareError as error:
            # Keep staff capability refusal distinct; conceal resource authorization.
            staff_denial = (operation == "get_trace" and "care_trace" not in ctx.staff_permissions
                            or operation == "get_handoffs" and "care_handoffs" not in ctx.staff_permissions) if error.status == 403 and isinstance(ctx, TrustedRequestContext) else False
            if error.status == 403 and not staff_denial:
                return ApiResponse(404, {"error": "not_found"})
            return ApiResponse(error.status, {"error": error.code})
        except ValueError:
            return ApiResponse(400, {"error": "invalid_payload"})
        except (StorageError, sqlite3.DatabaseError, OSError):
            return ApiResponse(503, {"error": "service_error"})
