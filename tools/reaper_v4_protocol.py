"""Non-admissible in-memory V4 frame and configuration grammar."""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import struct
from collections.abc import Mapping

__all__=("Frame","FrameType","ProtocolError","MAGIC","SCHEMA","MAX_PAYLOAD_BYTES","MAX_FRAME_BYTES","config_sha256","decode_frame","encode_frame","validate_config")

MAGIC=b"M3V4RCP!"; SCHEMA=1; HEADER=struct.Struct(">8sBBHI"); HEADER_BYTES=HEADER.size
MAX_PAYLOAD_BYTES=2048; MAX_FRAME_BYTES=HEADER_BYTES+MAX_PAYLOAD_BYTES; MAX_EXCHANGE_BYTES=MAX_FRAME_BYTES*2
IDENTITY_KEYS=frozenset(("schema","namespace","nonce","config_sha256","inputs"))
CONFIG_KEYS=IDENTITY_KEYS

class ProtocolError(ValueError): pass
class FrameType(enum.IntEnum): PRE=1; POST=2
@dataclasses.dataclass(frozen=True)
class Frame: frame_type:FrameType; sequence:int; payload:dict[str,object]

def _json(value: Mapping[str,object])->bytes:
    if not isinstance(value,Mapping): raise ProtocolError("frame payload is not an object")
    try: raw=json.dumps(dict(value),sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()
    except (TypeError,ValueError) as exc: raise ProtocolError("frame payload is not canonical JSON") from exc
    if len(raw)>MAX_PAYLOAD_BYTES: raise ProtocolError("frame payload exceeds 2 KiB")
    return raw
def config_sha256(config:Mapping[str,object])->str:
    if not isinstance(config,Mapping): raise ProtocolError("config is not an object")
    canonical=dict(config); canonical.pop("config_sha256",None)
    return hashlib.sha256(_json(canonical)).hexdigest()
def encode_frame(kind:FrameType,sequence:int,payload:Mapping[str,object])->bytes:
    if not isinstance(kind,FrameType) or type(sequence) is not int or not 0<=sequence<=0xffff: raise ProtocolError("frame header is invalid")
    body=_json(payload); return HEADER.pack(MAGIC,SCHEMA,int(kind),sequence,len(body))+body
def decode_frame(raw:bytes)->tuple[Frame,int]:
    if not isinstance(raw,bytes) or len(raw)<HEADER_BYTES: raise ProtocolError("frame header is truncated")
    magic,schema,kind,sequence,size=HEADER.unpack(raw[:HEADER_BYTES]); end=HEADER_BYTES+size
    if magic!=MAGIC or schema!=SCHEMA or size>MAX_PAYLOAD_BYTES: raise ProtocolError("frame header is invalid")
    if len(raw)<end: raise ProtocolError("frame payload is truncated")
    try: frame_type=FrameType(kind); payload=json.loads(raw[HEADER_BYTES:end].decode(),parse_constant=lambda value:(_ for _ in ()).throw(ValueError(value)))
    except (ValueError,UnicodeDecodeError,json.JSONDecodeError) as exc: raise ProtocolError("frame payload is not JSON") from exc
    if not isinstance(payload,dict) or _json(payload)!=raw[HEADER_BYTES:end]: raise ProtocolError("frame payload is not canonical JSON")
    return Frame(frame_type,sequence,payload),end
def _mapping(value:object,keys:frozenset[str],name:str)->dict[str,object]:
    if not isinstance(value,dict) or set(value)!=keys: raise ProtocolError(f"{name} schema is invalid")
    return value
def validate_config(config:object)->dict[str,object]:
    value=_mapping(config,CONFIG_KEYS,"config")
    if type(value["schema"]) is not int or value["schema"]!=SCHEMA or value["namespace"]!="native-vst3-probe-v4-scan-isolated": raise ProtocolError("config identity is invalid")
    if not isinstance(value["nonce"],str) or len(value["nonce"])!=32 or any(char not in "0123456789abcdef" for char in value["nonce"]): raise ProtocolError("config nonce is invalid")
    if not isinstance(value["config_sha256"],str) or len(value["config_sha256"])!=64 or any(char not in "0123456789abcdef" for char in value["config_sha256"]): raise ProtocolError("config hash is invalid")
    if not isinstance(value["inputs"],dict) or not value["inputs"] or any(not isinstance(k,str) or not k or not isinstance(v,str) or len(v)!=64 or any(char not in "0123456789abcdef" for char in v) for k,v in value["inputs"].items()): raise ProtocolError("config inputs are invalid")
    if value["config_sha256"]!=config_sha256(value): raise ProtocolError("config hash does not match canonical config")
    return value
