import copy
import json
import shutil
import unittest
import uuid
from itertools import permutations
from pathlib import Path

import timing_model
import typed_events
from test_typed_events import row


def switch(qpc, old, new, state=5, cpu=0):
    return dict(
        row("cswitch", qpc, pid=999, tid=new),
        schema=2,
        sourceType=typed_events.TYPES["cswitch"],
        payload={
            "oldTid": old,
            "newTid": new,
            "oldThreadState": state,
            "oldThreadWaitReason": 6,
            "oldThreadWaitMode": 1,
            "processorNumber": cpu,
        },
    )


def ready(qpc, target, flags=0):
    return dict(
        row("readyThread", qpc, pid=999, tid=888),
        schema=2,
        sourceType=typed_events.TYPES["readyThread"],
        payload={
            "awakenedTid": target,
            "adjustReason": 0,
            "adjustIncrement": 0,
            "flags": flags,
            "processorNumber": 0,
        },
    )


class Timing(unittest.TestCase):
    def setUp(self):
        self.folder = Path(__file__).parent / ("test-private-" + uuid.uuid4().hex)
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "dto.jsonl"
        self.life = {"tid": 11, "owner": "observed-owner", "start": 0, "end": 100}

    def analyze(self, records, **kwargs):
        self.path.write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        arguments = {
            "lifetimes": [self.life],
            "owner_keys": {"observed-owner"},
            "window": (0, 100),
            "frequency": 10,
        }
        arguments.update(kwargs)
        return timing_model.model(self.path, **arguments)

    def test_preemption_wait_ready_repeat_and_foreign_headers(self):
        records = [
            switch(10, 90, 11),
            switch(20, 11, 90, state=1),
            ready(25, 11),
            switch(30, 90, 11),
            switch(40, 11, 90),
            ready(60, 11),
            ready(65, 11),
            switch(70, 90, 11),
            switch(90, 11, 90),
        ]
        result = self.analyze(records)
        thread = result["threads"][0]
        self.assertEqual(
            thread["ticks"],
            {"UNKNOWN": 20, "WAITING": 20, "RUNNABLE": 20, "SCHEDULED": 40},
        )
        self.assertEqual(sum(thread["ticks"].values()), 100)
        self.assertEqual(timing_model.seconds(15, 10), 1.5)
        self.assertEqual(thread["lifetime"]["owner"], "observed-owner")

    def test_migration_reuse_and_clipped_missing_boundaries(self):
        records = [
            switch(10, 90, 11),
            switch(20, 11, 90, state=1),
            switch(30, 90, 11, cpu=2),
            switch(40, 11, 90, cpu=2),
            switch(60, 90, 11),
            switch(80, 11, 90),
        ]
        second = {"tid": 11, "owner": "second", "start": 50, "end": 100}
        result = self.analyze(
            records,
            lifetimes=[dict(self.life, end=50), second],
            owner_keys={"observed-owner", "second"},
            window=(15, 90),
        )
        self.assertEqual(
            result["threads"][0]["ticks"],
            {"UNKNOWN": 10, "WAITING": 0, "RUNNABLE": 10, "SCHEDULED": 15},
        )
        self.assertEqual(
            result["threads"][1]["ticks"],
            {"UNKNOWN": 20, "WAITING": 0, "RUNNABLE": 0, "SCHEDULED": 20},
        )
        for thread in result["threads"]:
            intervals = thread["intervals"]
            self.assertTrue(
                all(
                    a["end"] == b["start"]
                    for a, b in zip(intervals, intervals[1:], strict=False)
                )
            )
            self.assertEqual(
                sum(thread["ticks"].values()), thread["window"][1] - thread["window"][0]
            )

    def test_flags_unknown_states_and_conflicting_processor_are_unknown(self):
        result = self.analyze(
            [
                switch(10, 90, 11),
                switch(20, 11, 90, cpu=2),
                ready(30, 11, flags=1),
                switch(40, 90, 11),
                switch(50, 11, 90, state=7),
                ready(60, 11),
                switch(70, 90, 11),
                switch(80, 11, 90),
            ]
        )
        self.assertEqual(
            result["threads"][0]["ticks"],
            {"UNKNOWN": 70, "WAITING": 0, "RUNNABLE": 10, "SCHEDULED": 20},
        )

    def test_foreign_cpu_switch_exposes_missing_owned_switch_out(self):
        result = self.analyze(
            [switch(10, 90, 11), switch(20, 91, 92), switch(30, 11, 90)]
        )
        self.assertEqual(result["threads"][0]["ticks"]["UNKNOWN"], 100)

    def test_stale_processor_association_cannot_invalidate_reused_tid_lifetime(self):
        old = dict(self.life, owner="old", end=20)
        new = dict(self.life, owner="new", start=30)
        result = self.analyze(
            [
                switch(10, 90, 11),
                switch(35, 91, 11, cpu=1),
                switch(40, 92, 93),
                switch(60, 11, 91, cpu=1),
            ],
            lifetimes=[old, new],
            owner_keys={"old", "new"},
        )
        self.assertEqual(result["threads"][0]["ticks"]["UNKNOWN"], 20)
        self.assertEqual(
            result["threads"][1]["ticks"],
            {"UNKNOWN": 45, "WAITING": 0, "RUNNABLE": 0, "SCHEDULED": 25},
        )
        self.assertIn(
            {
                "start": 35,
                "end": 60,
                "state": "SCHEDULED",
                "reason": "bracketed_observations",
            },
            result["threads"][1]["intervals"],
        )

    def test_independent_same_qpc_observations_are_permutation_invariant(self):
        lives = [self.life, dict(self.life, tid=12), dict(self.life, tid=13)]
        simultaneous = [switch(20, 90, 11), switch(20, 91, 12, cpu=1), ready(20, 13)]
        ending = [
            switch(40, 11, 90),
            switch(50, 12, 91, cpu=1),
            switch(60, 92, 13, cpu=2),
            switch(80, 13, 92, cpu=2),
        ]
        expected = self.analyze(simultaneous + ending, lifetimes=lives)
        for ordering in permutations(simultaneous):
            self.assertEqual(
                self.analyze(list(ordering) + ending, lifetimes=lives), expected
            )
        self.assertEqual(expected["threads"][0]["ticks"]["SCHEDULED"], 20)
        self.assertEqual(expected["threads"][1]["ticks"]["SCHEDULED"], 30)
        self.assertEqual(expected["threads"][2]["ticks"]["RUNNABLE"], 40)
        ambiguous = []
        for ordering in permutations([switch(20, 91, 92), ready(20, 11)]):
            result = self.analyze([switch(10, 90, 11)] + list(ordering))
            self.assertEqual(result["threads"][0]["ticks"]["UNKNOWN"], 100)
            self.assertEqual(result["threads"][0]["diagnostics"]["ambiguous_subject_qpc"], 1)
            ambiguous.append(result)
        self.assertEqual(*ambiguous)

    def test_invalid_order_lifetimes_schema_and_legacy_policy(self):
        with self.assertRaisesRegex(ValueError, "out_of_order"):
            self.analyze([ready(20, 11), ready(10, 11)])
        with self.assertRaisesRegex(ValueError, "overlapping"):
            self.analyze([], lifetimes=[self.life, dict(self.life, owner="other")])
        for kwargs, reason in (
            ({"frequency": 0}, "frequency"),
            ({"window": (50, 20)}, "window"),
            ({"lifetimes": None}, "lifetimes"),
            ({"lifetimes": [dict(self.life, tid=True)]}, "tid"),
        ):
            with self.assertRaisesRegex(ValueError, reason):
                self.analyze([], **kwargs)
        malformed = copy.deepcopy(ready(10, 11))
        malformed["payload"]["flags"] = -1
        with self.assertRaisesRegex(ValueError, "schema"):
            self.analyze([malformed])
        malformed["kind"] = []
        with self.assertRaisesRegex(ValueError, "schema"):
            self.analyze([malformed])
        legacy = dict(
            row("readyThread", 10), sourceType=typed_events.TYPES["readyThread"]
        )
        result = self.analyze([legacy])
        self.assertEqual(result["status"], "UNAVAILABLE_LEGACY")
        self.assertEqual(result["threads"][0]["ticks"]["UNKNOWN"], 100)
        header = row(
            "header",
            0,
            None,
            None,
            {
                "perfFreq": 10,
                "reservedFlags": 1,
                "eventsLost": 0,
                "buffersLost": 0,
                "sessionStartFileTime": 0,
                "sessionEndFileTime": 100,
                "lastQpc": 100,
            },
        )
        result = self.analyze([switch(10, 90, 11), switch(20, 11, 90), header])
        self.assertEqual(result["threads"][0]["ticks"]["SCHEDULED"], 10)

    def test_foreign_self_switches_do_not_abort_selected_lifetime(self):
        baseline = [switch(40, 90, 11), switch(60, 11, 90)]
        foreign = dict(self.life, tid=12, owner="unselected")
        result = self.analyze(
            [switch(10, 11, 11), switch(20, 12, 12), switch(30, 13, 13, cpu=2)]
            + baseline,
            lifetimes=[dict(self.life, start=30), foreign],
        )
        self.assertEqual(
            result,
            self.analyze(baseline, lifetimes=[dict(self.life, start=30), foreign]),
        )

    def test_foreign_self_switch_on_owned_processor_invalidates_bracket(self):
        result = self.analyze(
            [switch(10, 90, 11), switch(20, 92, 92), switch(30, 11, 90)]
        )
        self.assertEqual(
            result["threads"][0]["ticks"],
            {"UNKNOWN": 100, "WAITING": 0, "RUNNABLE": 0, "SCHEDULED": 0},
        )

    def test_unrelated_processor_ties_do_not_abort_owned_other_processor(self):
        baseline = [switch(10, 90, 11, cpu=1), switch(60, 11, 90, cpu=1)]
        foreign = dict(self.life, tid=12, owner="unselected")
        for ordering in permutations([switch(20, 12, 92), switch(20, 93, 94)]):
            self.assertEqual(
                self.analyze(
                    baseline[:1] + list(ordering) + baseline[1:],
                    lifetimes=[self.life, foreign],
                ),
                self.analyze(baseline, lifetimes=[self.life, foreign]),
            )

    def test_unsupported_self_and_relevant_processor_ties_are_unknown(self):
        thread = self.analyze([switch(10, 11, 11)])["threads"][0]
        self.assertEqual(thread["ticks"]["UNKNOWN"], 100)
        self.assertEqual(thread["diagnostics"], {
            "unsupported_self": 1, "ambiguous_subject_qpc": 0, "ambiguous_processor_qpc": 0,
        })
        results = []
        for ordering in permutations([switch(20, 11, 90), switch(20, 92, 93)]):
            result = self.analyze([switch(10, 90, 11)] + list(ordering))
            thread = result["threads"][0]
            self.assertEqual(thread["ticks"]["UNKNOWN"], 100)
            self.assertEqual(thread["diagnostics"], {
                "unsupported_self": 0, "ambiguous_subject_qpc": 1, "ambiguous_processor_qpc": 1,
            })
            results.append(result)
        self.assertEqual(*results)

    def test_bracketed_atomic_self_switches_preserve_scheduled_accounting(self):
        result = self.analyze(
            [
                switch(10, 90, 11),
                switch(20, 11, 11, state=1),
                switch(25, 11, 11, state=5),
                switch(30, 11, 90),
            ]
        )
        thread = result["threads"][0]
        self.assertEqual(
            thread["ticks"],
            {"UNKNOWN": 80, "WAITING": 0, "RUNNABLE": 0, "SCHEDULED": 20},
        )
        self.assertEqual(thread["atomic_self_switches"], 2)
        self.assertEqual(thread["diagnostics"], {
            "unsupported_self": 0, "ambiguous_subject_qpc": 0, "ambiguous_processor_qpc": 0,
        })
        self.assertEqual(sum(thread["ticks"].values()), 100)
        self.assertEqual(
            [item["reason"] for item in thread["intervals"][1:3]],
            ["atomic_self_switch_accounting", "atomic_self_switch_accounting"],
        )

    def test_atomic_self_cannot_repair_missing_conflicting_or_reused_boundary(self):
        cases = [
            ([switch(20, 11, 11)], [self.life]),
            ([switch(10, 90, 11), switch(20, 11, 11, cpu=1)], [self.life]),
            ([switch(10, 90, 11), ready(15, 11), switch(20, 11, 11)], [self.life]),
            (
                [switch(10, 90, 11), switch(35, 91, 11, cpu=1), switch(40, 11, 11)],
                [dict(self.life, end=20), dict(self.life, start=30)],
            ),
        ]
        for records, lives in cases:
            with self.subTest(records=records):
                result = self.analyze(records, lifetimes=lives)
                self.assertEqual(result["threads"][-1]["diagnostics"]["unsupported_self"], 1)
                for thread in result["threads"]:
                    self.assertEqual(thread["ticks"]["SCHEDULED"], 0)
                    self.assertEqual(sum(thread["ticks"].values()),
                                     thread["window"][1] - thread["window"][0])
                self.assertTrue(any(
                    item["reason"] == "unsupported_self"
                    for item in result["threads"][-1]["intervals"]
                ))

    def test_atomic_self_same_subject_tie_is_unknown_not_normalized(self):
        results = []
        for ordering in permutations([switch(20, 11, 11), ready(20, 11)]):
            result = self.analyze([switch(10, 90, 11)] + list(ordering))
            thread = result["threads"][0]
            self.assertEqual(thread["ticks"]["UNKNOWN"], 100)
            self.assertEqual(thread["atomic_self_switches"], 0)
            self.assertEqual(thread["diagnostics"]["ambiguous_subject_qpc"], 1)
            results.append(result)
        self.assertEqual(*results)

    def test_early_unsupported_self_counts_outside_window_without_poisoning_others(self):
        result = self.analyze(
            [switch(5, 11, 11), switch(10, 90, 12, cpu=1), switch(20, 91, 11),
             switch(40, 11, 91), switch(50, 12, 90, cpu=1)],
            lifetimes=[self.life, dict(self.life, tid=12)], window=(30, 80),
        )
        self.assertEqual(result["threads"][0]["ticks"],
                         {"UNKNOWN": 40, "WAITING": 0, "RUNNABLE": 0, "SCHEDULED": 10})
        self.assertEqual(result["threads"][1]["ticks"],
                         {"UNKNOWN": 30, "WAITING": 0, "RUNNABLE": 0, "SCHEDULED": 20})
        self.assertEqual(result["threads"][0]["diagnostics"]["unsupported_self"], 1)
        self.assertEqual(result["threads"][1]["diagnostics"], {
            "unsupported_self": 0, "ambiguous_subject_qpc": 0, "ambiguous_processor_qpc": 0,
        })

    def test_ambiguous_boundary_clears_processor_cache_before_positive_recovery(self):
        results = []
        for ordering in permutations([ready(20, 11), switch(20, 11, 90)]):
            result = self.analyze(
                [switch(10, 90, 11)] + list(ordering)
                + [switch(30, 91, 11, cpu=1), switch(40, 92, 93),
                   switch(60, 11, 91, cpu=1)]
            )
            thread = result["threads"][0]
            self.assertEqual(thread["ticks"],
                             {"UNKNOWN": 70, "WAITING": 0, "RUNNABLE": 0, "SCHEDULED": 30})
            self.assertEqual(thread["diagnostics"]["ambiguous_subject_qpc"], 1)
            results.append(result)
        self.assertEqual(*results)

    def test_processor_tie_without_subject_tie_does_not_seed_running(self):
        results = []
        for ordering in permutations([switch(20, 90, 11), switch(20, 92, 93)]):
            result = self.analyze(list(ordering) + [switch(40, 11, 90)])
            thread = result["threads"][0]
            self.assertEqual(thread["ticks"]["UNKNOWN"], 100)
            self.assertEqual(thread["diagnostics"], {
                "unsupported_self": 0, "ambiguous_subject_qpc": 0, "ambiguous_processor_qpc": 1,
            })
            self.assertTrue(any(item["reason"] == "ambiguous_processor_qpc"
                                for item in thread["intervals"]))
            results.append(result)
        self.assertEqual(*results)

    def test_unsupported_self_state_conflict_clears_old_processor_association(self):
        thread = self.analyze(
            [switch(10, 90, 11), ready(15, 11), switch(20, 11, 11),
             switch(30, 91, 11, cpu=1), switch(40, 92, 93),
             switch(60, 11, 91, cpu=1)]
        )["threads"][0]
        self.assertEqual(thread["ticks"],
                         {"UNKNOWN": 70, "WAITING": 0, "RUNNABLE": 0, "SCHEDULED": 30})
        self.assertEqual(thread["diagnostics"]["unsupported_self"], 1)


if __name__ == "__main__":
    unittest.main()
