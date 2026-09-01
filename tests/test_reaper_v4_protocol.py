"""Task 0A is a codec/barrier skeleton and cannot attest or launch."""
from __future__ import annotations
import ast, pathlib, unittest
from unittest import mock

_ROOT=pathlib.Path(__file__).resolve().parents[1]
_SOURCES={"protocol":_ROOT/"tools/reaper_v4_protocol.py","attester":_ROOT/"tools/reaper_v4_attester.py"}
def _preimport_contract():
    expected={
        "protocol":({("from","__future__","annotations"),("import","dataclasses"),("import","enum"),("import","hashlib"),("import","json"),("import","struct"),("from","collections.abc","Mapping")},{"ProtocolError","FrameType","Frame","_json","config_sha256","encode_frame","decode_frame","_mapping","validate_config"}),
        "attester":({("from","__future__","annotations"),("import","ctypes"),("import","dataclasses"),("import","pathlib"),("from","collections.abc","Mapping"),("from","tools","reaper_v4_protocol")},{"AttestationError","AttesterConfig","_status_text","establish_protocol_barrier","validate_config"}),
    }
    for name,path in _SOURCES.items():
        tree=ast.parse(path.read_text(encoding="utf-8")); imports=set(); definitions=set()
        if not all(isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.ClassDef,ast.FunctionDef,ast.Expr)) for node in tree.body): raise AssertionError("unlisted top-level form")
        for index,node in enumerate(tree.body):
            if isinstance(node,ast.Import): imports|={("import",alias.name) for alias in node.names}
            elif isinstance(node,ast.ImportFrom): imports|={("from",node.module,alias.name) for alias in node.names}
            elif isinstance(node,(ast.ClassDef,ast.FunctionDef)): definitions.add(node.name)
            elif isinstance(node,ast.Expr) and not(index==0 and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str)): raise AssertionError("top-level expression")
            if isinstance(node,(ast.Assign,ast.AnnAssign)) and node.value is not None:
                calls={call.func.attr if isinstance(call.func,ast.Attribute) else call.func.id for call in ast.walk(node.value) if isinstance(call,ast.Call) and isinstance(call.func,(ast.Attribute,ast.Name))}
                if calls-{"Struct","frozenset"}: raise AssertionError("top-level call")
        if imports!=expected[name][0] or definitions!=expected[name][1]: raise AssertionError("import or definition contract")
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,(ast.Attribute,ast.Name)):
                call=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id
                if call in {"Popen","popen","run","call","system","getattr","__import__","posix_spawn","posix_spawnp"} or call.startswith(("spawn","exec","fork")): raise AssertionError("forbidden call")
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and (node.decorator_list or node.args.defaults or node.args.kw_defaults): raise AssertionError("function decorator/default")
            if isinstance(node,ast.ClassDef):
                base_ok=not node.bases or (len(node.bases)==1 and ((node.name=="FrameType" and isinstance(node.bases[0],ast.Attribute) and node.bases[0].attr=="IntEnum") or (node.name in {"ProtocolError","AttestationError"} and isinstance(node.bases[0],ast.Name) and node.bases[0].id in {"ValueError","RuntimeError"})))
                if node.keywords or not base_ok: raise AssertionError("class base/metaclass")
                for decorator in node.decorator_list:
                    if not(isinstance(decorator,ast.Call) and (decorator.func.attr if isinstance(decorator.func,ast.Attribute) else decorator.func.id)=="dataclass"): raise AssertionError("class decorator")
                for body in node.body:
                    if not isinstance(body,(ast.Assign,ast.AnnAssign,ast.FunctionDef,ast.Pass)): raise AssertionError("class body")
                    if isinstance(body,(ast.Assign,ast.AnnAssign)) and body.value is not None and any(isinstance(item,ast.Call) for item in ast.walk(body.value)): raise AssertionError("class body call")
_preimport_contract()
from tools import reaper_v4_attester as A
from tools import reaper_v4_protocol as P

def config_data():
    value={"schema":1,"namespace":"native-vst3-probe-v4-scan-isolated","nonce":"a"*32,"config_sha256":"b"*64,"inputs":{"project":"c"*64}}
    value["config_sha256"]=P.config_sha256(value); return value

class Tests(unittest.TestCase):
    def test_codec_and_digest_are_pure_and_bounded(self):
        data=P.validate_config(config_data()); raw=P.encode_frame(P.FrameType.PRE,0,{"x":True})
        self.assertEqual(P.decode_frame(raw)[0].payload,{"x":True})
        changed=dict(data); changed["nonce"]="d"*32
        with self.assertRaises(P.ProtocolError): P.validate_config(changed)
        invalid=config_data(); invalid["inputs"]={"":"c"*64}; invalid["config_sha256"]=P.config_sha256(invalid)
        with self.assertRaises(P.ProtocolError): P.validate_config(invalid)
        with self.assertRaises(P.ProtocolError): P.decode_frame(P.HEADER.pack(P.MAGIC,P.SCHEMA,1,0,2)+b"{")
    def test_barrier_mock_and_config_validation_have_no_control_api(self):
        status="\n".join(f"{key}:\t0000000000000000" for key in A.CAPABILITY_STATUS_FIELDS); libc=mock.Mock(); libc.prctl.return_value=0
        with mock.patch.object(A.ctypes,"CDLL",return_value=libc),mock.patch.object(A,"_status_text",return_value=status): A.establish_protocol_barrier(config_data())
        self.assertEqual(A.validate_config(A.AttesterConfig(config_data()))["schema"],1)
        self.assertFalse(hasattr(A,"AttesterControl")); self.assertFalse(hasattr(A,"run_attestation"))
        self.assertFalse(hasattr(P,"read_ack")); self.assertFalse(hasattr(P,"write_frame"))
    def test_barrier_refuses_prctl_error_and_missing_or_nonempty_caps(self):
        status="\n".join(f"{key}:\t0000000000000000" for key in A.CAPABILITY_STATUS_FIELDS)
        for result,contents in ((1,status),(0,""),(0,status.replace("CapEff:\t0000000000000000","CapEff:\t0000000000000001"))):
            with self.subTest(result=result,contents=contents),mock.patch.object(A.ctypes,"CDLL",return_value=mock.Mock(prctl=mock.Mock(return_value=result))),mock.patch.object(A,"_status_text",return_value=contents):
                with self.assertRaises(A.AttestationError): A.establish_protocol_barrier(config_data())
    def test_static_contract_has_no_launch_dynamic_or_main_path(self):
        self.assertIsNone(_preimport_contract())
        self.assertEqual(set(P.__all__),{"Frame","FrameType","ProtocolError","MAGIC","SCHEMA","MAX_PAYLOAD_BYTES","MAX_FRAME_BYTES","config_sha256","decode_frame","encode_frame","validate_config"})
        self.assertEqual(set(A.__all__),{"AttestationError","AttesterConfig","establish_protocol_barrier","validate_config"})
