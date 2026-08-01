import json
import contextvars
from datetime import datetime, date
from decimal import Decimal

_current_msg_type = contextvars.ContextVar("current_msg_type", default=None)


def _json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def encode(msg_dict):
    return json.dumps(msg_dict, default=_json_serializer)


def decode(raw_message):
    return json.loads(raw_message)


def set_current_msg_type(msg_type):
    _current_msg_type.set(msg_type)


def make_response(code, message, data):
    resp = {"code": code, "message": message, "data": data}
    msg_type = _current_msg_type.get()
    if msg_type is not None:
        resp["type"] = msg_type
    return resp