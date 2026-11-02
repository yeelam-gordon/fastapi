import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_context as native
import runtime_pair
import test_runtime_pair


class NativeContextTests(unittest.TestCase):
    def test_readonly_sdk_resolver_rejects_missing_arm_lib_and_version_mismatch(self):
        vs, kit = Path("VS"), Path("Kits")
        vc = vs / "VC" / "Tools" / "MSVC" / "14.44.35207"
        version = kit / "Include" / "10.0.28000.0"
        directories = {
            vc.parent,
            vc,
            vc / "include",
            vc / "lib" / "arm64",
            version.parent,
            version,
            *[version / n for n in ("ucrt", "shared", "um")],
            *[kit / "Lib" / version.name / n / "arm64" for n in ("ucrt", "um")],
        }
        with (
            patch.object(
                Path, "is_dir", side_effect=lambda p: p in directories, autospec=True
            ),
            patch.object(
                Path,
                "iterdir",
                side_effect=lambda p: iter([vc] if p == vc.parent else [version]),
                autospec=True,
            ),
        ):
            includes, libraries, identity = native.windows_sdk(vs, [kit])
            self.assertEqual(identity["sdk_version"], version.name)
            self.assertEqual(len(includes), 4)
            self.assertEqual(len(libraries), 3)
            with self.assertRaisesRegex(RuntimeError, "only ARM64"):
                native.windows_sdk(vs, [kit], "x64")
            directories.remove(vc / "lib" / "arm64")
            with self.assertRaisesRegex(RuntimeError, "coherent installed SDK"):
                native.windows_sdk(vs, [kit])
            directories.add(vc / "lib" / "arm64")
            directories.remove(kit / "Lib" / version.name / "um" / "arm64")
            directories.add(kit / "Lib" / "10.0.26000.0" / "um" / "arm64")
            with self.assertRaisesRegex(RuntimeError, "coherent installed SDK"):
                native.windows_sdk(vs, [kit])

    def test_platform_recipes_use_matching_native_abi_without_lto(self):
        windows = native.commands(
            Path("clang-cl.exe"),
            Path("lld-link.exe"),
            Path("headers"),
            Path("libs") / "python313.lib",
            ".cp313-win_arm64.pyd",
            {"LIB": "sdk;crt"},
        )
        self.assertEqual(len(windows), 5)
        self.assertTrue(
            all("--target=aarch64-pc-windows-msvc" in c for c in windows[:4])
        )
        self.assertIn("/MACHINE:ARM64", windows[-1])
        mac = native.commands(
            Path("clang"),
            None,
            Path("headers"),
            Path("unused"),
            ".cpython-313-darwin.so",
            {},
        )
        self.assertIn("dynamic_lookup", mac[0])
        self.assertEqual(mac[0][mac[0].index("-arch") + 1], "arm64")
        for commands in (windows, mac):
            self.assertFalse(
                any(
                    "lto" in arg.lower() or arg == "/GL"
                    for command in commands
                    for arg in command
                )
            )
        self.assertNotIn("/MD", mac[0])

    def test_owned_compile_failure_retains_receipt_and_never_accepts(self):
        receipt = native.owned_process.Receipt(
            1, False, 1, 0, True, False, True, ("compile failed",)
        )
        with (
            patch.object(
                native.owned_process, "run_owned", return_value=receipt
            ) as run,
            patch.object(native, "save") as save,
            self.assertRaisesRegex(RuntimeError, "owned preparation failed"),
        ):
            native.run(["clang", "input.c"], Path("owned"), "compile")
        self.assertEqual(run.call_args.kwargs["timeout"], 180)
        self.assertTrue(save.called)

    def test_zero_exit_with_owned_survivor_is_not_preparation_success(self):
        receipt = native.owned_process.Receipt(0, False, 1, 0, True, True, True, ())
        with (
            patch.object(native.owned_process, "run_owned", return_value=receipt),
            patch.object(native, "save"),
            self.assertRaisesRegex(RuntimeError, "owned preparation failed"),
        ):
            native.run(["cmd.exe", "sdk.cmd"], Path("owned"), "sdk")

    def test_preparation_diagnostics_are_retained_and_rejected(self):
        receipt = native.owned_process.Receipt(0, False, 1, 0, True, False, True, ())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "compile.stdout").write_text("", encoding="utf-8")
            diagnostics = root / "compile.stderr"
            diagnostics.write_text(
                "warning: unexpected build setting", encoding="utf-8"
            )
            with (
                patch.object(native.owned_process, "run_owned", return_value=receipt),
                self.assertRaisesRegex(RuntimeError, "preparation diagnostics"),
            ):
                native.run(["clang", "input.c"], root, "compile")
            self.assertTrue((root / "compile.receipt.json").is_file())
            self.assertEqual(
                diagnostics.read_text(encoding="utf-8"),
                "warning: unexpected build setting",
            )

    def exercise(self, style="windows", stderr=False):
        owner = test_runtime_pair.RuntimePairTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        fixture = owner.fixture
        root = fixture.source / "native"
        root.mkdir()
        (root / "build-spec.json").write_text("{}")
        fixture.args.native_context = root
        fixture.args.style = style
        versions = []

        def probe(python, action, source, argument, env, folder):
            if action == "identity":
                versions.append(argument)
                self.assertIn(str(root / "overlays"), env["PYTHONPATH"])
                return {"packages": {"coverage": "7.17.0"}, "executable": str(python)}
            return owner.current

        def phase(*args):
            value = fixture.fake_phase(*args)
            if stderr and args[-1] == "test":
                (args[-2] / "test.stderr").write_text("coverage warning")
            return value

        with (
            patch.object(runtime_pair, "probe", side_effect=probe),
            patch.object(native, "verify") as verify,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            calls = fixture.exercise_paired(side_effect=phase).call_args_list
        self.assertEqual(versions, ["3.13.15", "3.13.15"])
        self.assertEqual(verify.call_count, 28)
        return fixture, calls

    def test_native_pipeline_common313_overlays_and_pending_lifecycle(self):
        fixture, calls = self.exercise("macos")
        for call in calls[1::2]:
            env = call.args[2]
            self.assertIn("overlays", env["PYTHONPATH"])
            self.assertEqual(call.args[0], ["bash", "scripts/test.sh"])
            self.assertIn('command coverage "$@"', Path(env["BASH_ENV"]).read_text())
        result = json.loads((fixture.output / "result.json").read_bytes())
        self.assertEqual(result["status"], "pending-owned-lifecycle")
        self.assertFalse(result["candidate_screen_pass"])
        self.assertEqual(len(result["pair_savings_seconds"]), 5)
        self.assertEqual(
            result["labels"],
            {
                "stock": "compiled stock cp313",
                "candidate": "compiled native guard cp313",
            },
        )
        self.assertIn("owned coverage overlay only", result["preparation"])
        self.assertNotIn("no overlays", result["preparation"])

    def test_native_stderr_fails_before_success(self):
        with self.assertRaisesRegex(RuntimeError, "native test stderr"):
            self.exercise(stderr=True)
