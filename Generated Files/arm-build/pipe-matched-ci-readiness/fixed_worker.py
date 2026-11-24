"""Pinned whole-group worker assignment for matched performance experiments."""

import hashlib
import importlib.metadata
import json
import os
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest
from xdist.scheduler import loadgroup, loadscope
from xdist.workermanage import WorkerController

SOURCE_HASHES = {
    loadscope.__name__: "1eb3b1031d74b120e0537593a7cfcedc9ca8142d41eda0eb22c3df6dc8dc0951",
    loadgroup.__name__: "9ac209b15c0dffffa74ddad508bd6f83393583d27cc4e234844f9f906f36bdef",
}


def worker_number(name: str) -> int:
    if not re.fullmatch(r"gw\d+", name):
        raise ValueError(f"Unsupported worker identity: {name}")
    return int(name[2:])


def group_plan(
    collection: list[str],
    workers: list[str],
    split_scope: Callable[[str], str],
    reorder: bool,
) -> dict[str, str]:
    if not workers or len(set(workers)) != len(workers):
        raise ValueError("Unique nonempty workers required")
    if not collection or len(set(collection)) != len(collection):
        raise ValueError("Unique nonempty collection required")
    workers = sorted(workers, key=worker_number)
    sizes = Counter(split_scope(nodeid) for nodeid in collection)
    if len(sizes) < len(workers):
        raise ValueError("This controlled protocol requires work for every worker")
    scopes = sorted(sizes, key=lambda scope: -sizes[scope]) if reorder else list(sizes)
    weights = dict.fromkeys(workers, 0)
    result = {}
    for scope in scopes:
        owner = min(workers, key=lambda name: (weights[name], worker_number(name)))
        result[scope] = owner
        weights[owner] += sizes[scope]
    return result


class FixedLoadGroup(loadgroup.LoadGroupScheduling):
    def __init__(self, config: pytest.Config, log=None) -> None:
        super().__init__(config, log)
        self.owners: dict[str, str] = {}
        self.sent: dict[str, list[str]] = {}

    def schedule(self) -> None:
        if self.collection is None:
            if not self.collection_is_completed:
                raise RuntimeError("Cannot plan incomplete worker collections")
            collection = list(next(iter(self.registered_collections.values())))
            self.owners = group_plan(
                collection,
                [node.gateway.id for node in self.nodes],
                self._split_scope,
                self.config.option.loadscopereorder,
            )
        super().schedule()

    def _assign_work_unit(self, node: WorkerController) -> None:
        owner = node.gateway.id
        scope = next(
            (scope for scope in self.workqueue if self.owners[scope] == owner), None
        )
        if scope is None:
            node.shutdown()
            return
        work_unit = self.workqueue.pop(scope)
        self.assigned_work.setdefault(node, {})[scope] = work_unit
        nodeids = [nodeid for nodeid, completed in work_unit.items() if not completed]
        self.sent.setdefault(owner, []).extend(nodeids)
        collection = self.registered_collections[node]
        node.send_runtest_some([collection.index(nodeid) for nodeid in nodeids])

    def _reschedule(self, node: WorkerController) -> None:
        if node.shutting_down:
            return
        if not any(self.owners[scope] == node.gateway.id for scope in self.workqueue):
            node.shutdown()
            return
        if self._pending_of(self.assigned_work[node]) <= 2:
            self._assign_work_unit(node)

    def remove_node(self, node: WorkerController) -> str | None:
        if self._pending_of(self.assigned_work[node]):
            raise RuntimeError("Fixed-assignment worker failed; remapping is forbidden")
        return super().remove_node(node)


SCHEDULER = pytest.StashKey[FixedLoadGroup]()


@pytest.hookimpl(tryfirst=True)
def pytest_xdist_make_scheduler(config: pytest.Config, log):
    if config.option.dist != "loadgroup":
        raise pytest.UsageError("Fixed-worker control requires --dist=loadgroup")
    if importlib.metadata.version("pytest-xdist") != "3.8.0":
        raise pytest.UsageError("Fixed-worker control requires pinned xdist3.8.0")
    for module in (loadscope, loadgroup):
        actual = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        if actual != SOURCE_HASHES[module.__name__]:
            raise pytest.UsageError(f"Scheduler source changed: {module.__name__}")
    scheduler = FixedLoadGroup(config, log)
    config.stash[SCHEDULER] = scheduler
    return scheduler


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus) -> None:
    scheduler = session.config.stash.get(SCHEDULER, None)
    if scheduler is None:
        return
    collection = scheduler.collection or []
    sent = [nodeid for nodeids in scheduler.sent.values() for nodeid in nodeids]
    exact = bool(collection) and Counter(sent) == Counter(collection)
    evidence = {
        "status": "EXACT_DISPATCH" if exact else "INCOMPLETE",
        "source_hashes": SOURCE_HASHES,
        "group_owners": scheduler.owners,
        "sent_by_worker": scheduler.sent,
        "collected_cases": len(collection),
        "scheduled_cases": len(sent),
        "exitstatus": int(exitstatus),
    }
    output = Path(os.environ["CORRECTNESS_OUTPUT"]) / "fixed-worker-plan.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    if not exact:
        raise RuntimeError("Fixed-worker dispatch did not preserve the full collection")
