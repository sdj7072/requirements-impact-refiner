from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "scripts" / "rir_delta_protocol.py"


def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


PROTOCOL = load_module("_test_rir_delta_protocol", PROTOCOL_PATH)


class DeltaProtocolTest(unittest.TestCase):
    def test_control_frame_bytes_and_round_trip_are_canonical(self):
        token = "a" * 32
        payload = {"effective_max_seconds": 2}
        body = (
            b'{"kind":"control","payload":{"effective_max_seconds":2},"token":"'
            + token.encode("ascii")
            + b'"}'
        )
        expected = f"{len(body):08x}\n".encode("ascii") + body

        frame = PROTOCOL.encode_frame("control", payload, token)

        self.assertEqual(frame, expected)
        self.assertEqual(PROTOCOL.decode_frame(frame, token), ("control", payload))

    def test_protocol_rejects_unknown_kind_and_foreign_token(self):
        token = "b" * 32
        with self.assertRaisesRegex(ValueError, "^delta worker output frame type is invalid$"):
            PROTOCOL.encode_frame("unknown", {}, token)

        frame = PROTOCOL.encode_frame("control", {"effective_max_seconds": 1}, token)
        with self.assertRaisesRegex(
            ValueError,
            "^delta worker frame authentication is invalid$",
        ):
            PROTOCOL.decode_frame(frame, "c" * 32)

    def test_protocol_rejects_oversized_and_malformed_frames(self):
        token = "d" * 32

        with self.assertRaisesRegex(
            ValueError,
            "^delta worker output frame exceeds its byte limit$",
        ):
            PROTOCOL.encode_frame("control", {"padding": "x" * 1024}, token)

        def body(kind, payload):
            return json.dumps(
                {"kind": kind, "payload": payload, "token": token},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")

        cases = (
            (PROTOCOL.decode_body, (b"", token), "delta worker frame body size is invalid"),
            (PROTOCOL.decode_body, (b"{", token), "delta worker frame payload is invalid"),
            (PROTOCOL.decode_body, (body(1, {}), token), "delta worker frame type is invalid"),
            (
                PROTOCOL.decode_body,
                (body("unknown", {}), token),
                "delta worker frame type or bound is invalid",
            ),
            (PROTOCOL.decode_frame, (b"", token), "delta worker frame size is invalid"),
            (
                PROTOCOL.decode_frame,
                (b"zzzzzzzz\n{}", token),
                "delta worker frame header is invalid",
            ),
            (
                PROTOCOL.decode_frame,
                (b"00000001\n{}", token),
                "delta worker frame length is invalid",
            ),
        )
        for operation, arguments, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, f"^{message}$"):
                    operation(*arguments)


if __name__ == "__main__":
    unittest.main()
