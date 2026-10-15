"""Workflow state machine.

Outer loop is deliberately code-driven (deterministic): who runs next, when to
retry, when to stop, when to wait for a human. Only the *content* decisions
inside a role are delegated to an agent.
"""

from enum import Enum


class State(str, Enum):
    RECEIVED = "RECEIVED"
    PLANNING = "PLANNING"
    PLAN_VALIDATED = "PLAN_VALIDATED"
    DEVELOPING = "DEVELOPING"
    SOFTWARE_TESTING = "SOFTWARE_TESTING"
    HUMAN_GATE = "HUMAN_GATE"
    REVIEWING = "REVIEWING"
    DONE = "DONE"
    FAILED = "FAILED"


TERMINAL = {State.DONE, State.FAILED}

# WAITING_FOR_HUMAN_HARDWARE_TEST is not a terminal state: the run is resumable.
WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN_HARDWARE_TEST"

ALLOWED = {
    State.RECEIVED: {State.PLANNING, State.FAILED},
    State.PLANNING: {State.PLAN_VALIDATED, State.FAILED},
    State.PLAN_VALIDATED: {State.DEVELOPING, State.FAILED},
    State.DEVELOPING: {State.SOFTWARE_TESTING, State.FAILED},
    State.SOFTWARE_TESTING: {State.DEVELOPING, State.HUMAN_GATE, State.REVIEWING, State.FAILED},
    State.HUMAN_GATE: {State.REVIEWING, State.FAILED},
    State.REVIEWING: {State.DONE, State.DEVELOPING, State.FAILED},
    State.DONE: set(),
    State.FAILED: set(),
}


def can_transition(src, dst):
    return dst in ALLOWED.get(src, set())


class TransitionError(RuntimeError):
    pass
