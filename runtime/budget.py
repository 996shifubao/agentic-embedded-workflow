"""Cost governance: token budget, prompt cache and route selection.

The point is not to guess a price, it is to make spending *observable and
stoppable*: every agent call is estimated, routed, cached when identical, and
refused once the task budget is gone. Numbers land in the trace, so the metrics
dashboard can report cache hit rate and cost per task.
"""

import hashlib
import json

CHARS_PER_TOKEN = 3.5          # same ratio the metrics dashboard uses
ROUTES = ("small", "standard", "large")
# Illustrative list prices per 1k tokens; swap for the provider of the day.
ROUTE_PRICE_PER_1K = {"small": 0.0003, "standard": 0.0015, "large": 0.006}


class BudgetExceeded(RuntimeError):
    pass


def estimate_tokens(text):
    return max(1, int(len(str(text)) / CHARS_PER_TOKEN))


def route_for(tokens):
    if tokens <= 900:
        return "small"
    if tokens <= 3500:
        return "standard"
    return "large"


def cost_of(tokens, route):
    return round(tokens / 1000.0 * ROUTE_PRICE_PER_1K.get(route, 0.0), 6)


class Budget:
    def __init__(self, limit_tokens):
        self.limit = int(limit_tokens)
        self.spent = 0
        self.calls = 0
        self.refused = 0
        self.by_route = {}
        self.cost = 0.0

    def spend(self, tokens, route, role=""):
        """-> True when the call fits, False once the budget is exhausted."""
        if self.spent + tokens > self.limit:
            self.refused += 1
            return False
        self.spent += tokens
        self.calls += 1
        self.by_route[route] = self.by_route.get(route, 0) + 1
        self.cost = round(self.cost + cost_of(tokens, route), 6)
        return True

    def summary(self):
        return {
            "limit_tokens": self.limit,
            "spent_tokens": self.spent,
            "calls": self.calls,
            "refused": self.refused,
            "routes": dict(self.by_route),
            "cost_estimate_usd": self.cost,
            "remaining_tokens": max(0, self.limit - self.spent),
        }


class PromptCache:
    """Identical (role, payload) pairs are answered from cache, not re-billed."""

    def __init__(self):
        self.store = {}
        self.hits = 0
        self.misses = 0
        self.saved_tokens = 0

    @staticmethod
    def key(role, payload):
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return "%s:%s" % (role, hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20])

    def get(self, role, payload, tokens=0):
        key = self.key(role, payload)
        if key in self.store:
            self.hits += 1
            self.saved_tokens += tokens
            return self.store[key]
        self.misses += 1
        return None

    def put(self, role, payload, value):
        self.store[self.key(role, payload)] = value
        return value

    def summary(self):
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "entries": len(self.store),
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
            "saved_tokens": self.saved_tokens,
        }


class BudgetedRuntime:
    """Drop-in wrapper: same `.name` / `.run(spec, payload)` surface."""

    def __init__(self, runtime, budget, cache, on_event=None):
        self.runtime = runtime
        self.name = getattr(runtime, "name", "runtime")
        self.budget = budget
        self.cache = cache
        self.on_event = on_event or (lambda kind, data: None)

    def run(self, spec, payload):
        role = getattr(spec, "name", None) or getattr(spec, "role", None) or "agent"
        tokens = estimate_tokens(json.dumps(payload, ensure_ascii=False, default=str))
        route = route_for(tokens)
        cached = self.cache.get(role, payload, tokens)
        if cached is not None:
            self.on_event("cache", {"role": role, "decision": "hit", "tokens_saved": tokens,
                                    "summary": self.cache.summary()})
            return cached
        if not self.budget.spend(tokens, route, role):
            self.on_event("budget", {"role": role, "decision": "refused",
                                     "estimated_tokens": tokens, "summary": self.budget.summary()})
            raise BudgetExceeded(
                "token budget exhausted: %d/%d tokens" % (self.budget.spent, self.budget.limit)
            )
        self.on_event("budget", {"role": role, "decision": "allow", "route": route,
                                 "estimated_tokens": tokens,
                                 "cost_estimate_usd": cost_of(tokens, route),
                                 "summary": self.budget.summary()})
        result = self.runtime.run(spec, payload)
        self.cache.put(role, payload, result)
        return result


def wrap_runtime(runtime, budget, cache, on_event=None):
    return BudgetedRuntime(runtime, budget, cache, on_event=on_event)
