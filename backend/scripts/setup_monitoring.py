"""Monitoring as code for the production services. Idempotent; prints a plan unless --apply.

Reads the specs in infra/monitoring/ (see infra/monitoring.md) and brings Cloud Monitoring,
Cloud Logging and Cloud Billing up to date, in this order:

1. log-based metrics (log-metrics.json), matched by metric name;
2. uptime checks (uptime-checks.json), matched by displayName;
3. custom services and their SLOs (services.json), matched by service and SLO id;
4. alert policies (alerts/*.json), matched by displayName;
5. the dashboard (dashboard.json), matched by displayName;
6. the monthly billing budget (budget.json, amount from --budget-inr), matched by displayName.

Without --apply nothing changes: each resource is listed as CREATE, UPDATE (with the fields
that differ) or OK. --validate adds read-only checks against the APIs: log filters through
entries.list, PromQL through the Prometheus query API, monitoring filters through
timeSeries.list, and the dashboard through dashboards.create?validateOnly=true.

Uses the REST APIs with the active gcloud account's access token. A missing billing
permission is reported and the other sections still run.

Run from backend/: python scripts/setup_monitoring.py [--validate] [--apply] [--budget-inr 2000]
"""

import argparse
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from deploy_integration import PROJECT, command

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "infra" / "monitoring"
MONITORING = f"https://monitoring.googleapis.com/v3/projects/{PROJECT}"
DASHBOARDS = f"https://monitoring.googleapis.com/v1/projects/{PROJECT}/dashboards"
PROMQL = f"https://monitoring.googleapis.com/v1/projects/{PROJECT}/location/global/prometheus/api/v1/query"
LOGGING = f"https://logging.googleapis.com/v2/projects/{PROJECT}"
BUDGETS = "https://billingbudgets.googleapis.com/v1"
BUDGET_API = "billingbudgets.googleapis.com"

UPTIME_FIELDS = [
    "displayName",
    "httpCheck",
    "period",
    "timeout",
    "selectedRegions",
    "contentMatchers",
]
SLO_FIELDS = ["displayName", "goal", "rollingPeriod", "serviceLevelIndicator"]
ALERT_FIELDS = [
    "displayName",
    "documentation",
    "combiner",
    "conditions",
    "alertStrategy",
    "severity",
    "notificationChannels",
    "enabled",
]
BUDGET_FIELDS = ["displayName", "budgetFilter", "amount", "thresholdRules", "notificationsRule"]


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:600]}")
        self.status = status
        self.body = body


class Api:
    def __init__(self):
        self.token = command("auth", "print-access-token").stdout.strip()

    def call(self, method, url, body=None, params=None, form=None):
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Authorization": f"Bearer {self.token}", "x-goog-user-project": PROJECT}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        # Only the fixed https Google API URLs above reach here.
        request = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                text = response.read().decode()
        except urllib.error.HTTPError as error:
            raise ApiError(error.code, error.read().decode(errors="replace")) from None
        return json.loads(text) if text else {}

    def list_all(self, url, key, params=None):
        items, token = [], None
        while True:
            page = self.call(
                "GET", url, params={**(params or {}), **({"pageToken": token} if token else {})}
            )
            items += page.get(key, [])
            token = page.get("nextPageToken")
            if not token:
                return items

    def get_or_none(self, url):
        try:
            return self.call("GET", url)
        except ApiError as error:
            if error.status == 404:
                return None
            raise


def load(name):
    return json.loads((SPECS / name).read_text(encoding="utf-8"))


def empty(value):
    return value in (None, False, 0, "", [], {})


def same_scalar(want, have):
    if isinstance(want, bool) or isinstance(have, bool):
        return bool(want) == bool(have)
    if isinstance(want, (int, float)) and isinstance(have, (int, float, str)):
        try:
            return float(want) == float(have)
        except ValueError:
            return False
    if isinstance(want, str) and isinstance(have, (int, float)):
        return same_scalar(have, want)
    return want == have


def differences(want, have, path=""):
    """Paths where `have` (from the API) does not match the spec `want`. Fields the API
    adds are ignored, and a spec value of false/0/empty matches an omitted field."""
    if isinstance(want, dict):
        if not isinstance(have, dict):
            return [] if empty(want) and empty(have) else [path or "."]
        found = []
        for key, value in want.items():
            if key not in have:
                if not empty(value):
                    found.append(f"{path}.{key}".lstrip("."))
                continue
            found += differences(value, have[key], f"{path}.{key}".lstrip("."))
        return found
    if isinstance(want, list):
        if not isinstance(have, list) or len(want) != len(have):
            return [] if empty(want) and empty(have) else [path or "."]
        found = []
        for index, (a, b) in enumerate(zip(want, have, strict=True)):
            found += differences(a, b, f"{path}[{index}]")
        return found
    return [] if same_scalar(want, have) else [path or "."]


def strip_conditions(policy):
    """Alert conditions come back with server-assigned names; compare without them."""
    copy = json.loads(json.dumps(policy))
    for condition in copy.get("conditions", []):
        condition.pop("name", None)
    return copy


class Plan:
    def __init__(self, apply):
        self.apply = apply
        self.counts = {"CREATE": 0, "UPDATE": 0, "OK": 0, "SKIP": 0, "ERROR": 0}

    def section(self, title):
        print(f"\n== {title}", flush=True)

    def item(self, verb, kind, name, detail="", action=None):
        self.counts[verb] += 1
        suffix = f"  ({detail})" if detail else ""
        print(f"  {verb:<6} {kind}: {name}{suffix}", flush=True)
        if self.apply and action is not None and verb in ("CREATE", "UPDATE"):
            try:
                action()
                print("         applied", flush=True)
            except ApiError as error:
                self.counts["ERROR"] += 1
                print(f"         FAILED: {error}", flush=True)

    def change(self, kind, name, want, have, create, update):
        if have is None:
            self.item("CREATE", kind, name, action=create)
            return
        diff = differences(want, have)
        if diff:
            shown = ", ".join(diff[:4]) + (f", +{len(diff) - 4} more" if len(diff) > 4 else "")
            self.item("UPDATE", kind, name, f"differs: {shown}", action=update)
        else:
            self.item("OK", kind, name)


def log_metrics(api, plan):
    plan.section("Log-based metrics (logging v2)")
    existing = {m["name"]: m for m in api.list_all(f"{LOGGING}/metrics", "metrics")}
    for spec in load("log-metrics.json"):
        name = spec["name"]
        plan.change(
            "log metric",
            name,
            spec,
            existing.get(name),
            lambda spec=spec: api.call("POST", f"{LOGGING}/metrics", spec),
            lambda spec=spec, name=name: api.call("PUT", f"{LOGGING}/metrics/{name}", spec),
        )


def uptime_checks(api, plan):
    plan.section("Uptime checks (monitoring v3)")
    existing = {}
    for check in api.list_all(f"{MONITORING}/uptimeCheckConfigs", "uptimeCheckConfigs"):
        existing.setdefault(check["displayName"], check)
    for spec in load("uptime-checks.json"):
        have = existing.get(spec["displayName"])
        mask = ",".join(field for field in UPTIME_FIELDS if field in spec)
        plan.change(
            "uptime check",
            spec["displayName"],
            spec,
            have,
            lambda spec=spec: api.call("POST", f"{MONITORING}/uptimeCheckConfigs", spec),
            lambda spec=spec, have=have, mask=mask: api.call(
                "PATCH",
                f"https://monitoring.googleapis.com/v3/{have['name']}",
                {k: v for k, v in spec.items() if k in UPTIME_FIELDS},
                params={"updateMask": mask},
            ),
        )


def services(api, plan):
    plan.section("Services and SLOs (monitoring v3)")
    for spec in load("services.json"):
        service_id = spec["serviceId"]
        body = {k: v for k, v in spec.items() if k in ("displayName", "custom")}
        url = f"{MONITORING}/services/{service_id}"
        have = api.get_or_none(url)
        plan.change(
            "service",
            service_id,
            body,
            have,
            lambda body=body, service_id=service_id: api.call(
                "POST", f"{MONITORING}/services", body, params={"serviceId": service_id}
            ),
            lambda body=body, url=url: api.call(
                "PATCH", url, body, params={"updateMask": "displayName"}
            ),
        )
        for slo in spec["slos"]:
            slo_id = slo["serviceLevelObjectiveId"]
            slo_body = {k: v for k, v in slo.items() if k in SLO_FIELDS}
            slo_url = f"{url}/serviceLevelObjectives/{slo_id}"
            slo_have = api.get_or_none(slo_url) if have is not None else None
            plan.change(
                "SLO",
                f"{service_id}/{slo_id}",
                slo_body,
                slo_have,
                lambda slo_body=slo_body, url=url, slo_id=slo_id: api.call(
                    "POST",
                    f"{url}/serviceLevelObjectives",
                    slo_body,
                    params={"serviceLevelObjectiveId": slo_id},
                ),
                lambda slo_body=slo_body, slo_url=slo_url: api.call(
                    "PATCH", slo_url, slo_body, params={"updateMask": ",".join(SLO_FIELDS)}
                ),
            )


def alert_specs():
    return [
        (path.name, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((SPECS / "alerts").glob("*.json"))
    ]


def alert_policies(api, plan):
    plan.section("Alert policies (monitoring v3)")
    existing = {}
    for policy in api.list_all(f"{MONITORING}/alertPolicies", "alertPolicies"):
        if policy["displayName"] in existing:
            print(f"  WARN   duplicate alert policy {policy['displayName']!r}: updating the first")
        existing.setdefault(policy["displayName"], policy)
    for filename, spec in alert_specs():
        have = existing.get(spec["displayName"])
        mask = ",".join(field for field in ALERT_FIELDS if field in spec)
        plan.change(
            "alert policy",
            f"{spec['displayName']} [{filename}]",
            spec,
            strip_conditions(have) if have else None,
            lambda spec=spec: api.call("POST", f"{MONITORING}/alertPolicies", spec),
            lambda spec=spec, have=have, mask=mask: api.call(
                "PATCH",
                f"https://monitoring.googleapis.com/v3/{have['name']}",
                spec,
                params={"updateMask": mask},
            ),
        )


def dashboard(api, plan):
    plan.section("Dashboard (monitoring v1)")
    spec = load("dashboard.json")
    have = None
    for item in api.list_all(DASHBOARDS, "dashboards"):
        if item.get("displayName") == spec["displayName"]:
            have = item
            break
    plan.change(
        "dashboard",
        f"{spec['displayName']} ({len(spec['mosaicLayout']['tiles'])} tiles)",
        spec,
        have,
        lambda: api.call("POST", DASHBOARDS, spec),
        lambda: api.call(
            "PATCH",
            f"https://monitoring.googleapis.com/v1/{have['name']}",
            {**spec, "name": have["name"], "etag": have.get("etag", "")},
        ),
    )


def budget(api, plan, amount_inr):
    plan.section("Billing budget (billingbudgets v1)")
    found = command(
        "billing",
        "projects",
        "describe",
        PROJECT,
        "--format=value(billingAccountName)",
        optional=True,
    )
    account = found.stdout.strip()
    if found.returncode or not account:
        plan.item(
            "SKIP",
            "budget",
            "billing account",
            f"cannot read the project's billing account: {found.stderr.strip()[:300]}",
        )
        return
    currency = command(
        "billing",
        "accounts",
        "describe",
        account.split("/")[-1],
        "--format=value(currencyCode)",
        optional=True,
    ).stdout.strip()
    spec = load("budget.json")
    if currency and currency != spec["amount"]["specifiedAmount"]["currencyCode"]:
        plan.item(
            "SKIP",
            "budget",
            spec["displayName"],
            f"billing account currency is {currency}, spec uses INR",
        )
        return
    number = command(
        "projects", "describe", PROJECT, "--format=value(projectNumber)"
    ).stdout.strip()
    spec["budgetFilter"]["projects"] = [f"projects/{number}"]
    spec["amount"]["specifiedAmount"]["units"] = str(amount_inr)
    url = f"{BUDGETS}/{account}/budgets"
    try:
        budgets = api.list_all(url, "budgets")
    except ApiError as error:
        if error.status == 403 and "SERVICE_DISABLED" in error.body:
            if not plan.apply:
                plan.item(
                    "CREATE",
                    "budget",
                    f"{spec['displayName']} ({amount_inr} INR/month on {account})",
                    f"first enables {BUDGET_API} on {PROJECT}; budget permissions are checked then",
                )
                return
            print(f"  enabling {BUDGET_API} on {PROJECT}...", flush=True)
            command("services", "enable", BUDGET_API)
            budgets = None
            for _ in range(12):
                try:
                    budgets = api.list_all(url, "budgets")
                    break
                except ApiError as retry:
                    if retry.status == 403 and "SERVICE_DISABLED" in retry.body:
                        time.sleep(10)
                        continue
                    budget_denied(plan, spec, retry)
                    return
            if budgets is None:
                plan.item(
                    "SKIP",
                    "budget",
                    spec["displayName"],
                    f"{BUDGET_API} not active yet; rerun later",
                )
                return
        elif error.status == 403:
            budget_denied(plan, spec, error)
            return
        else:
            raise
    have = next((b for b in budgets if b.get("displayName") == spec["displayName"]), None)
    plan.change(
        "budget",
        f"{spec['displayName']} ({amount_inr} INR/month on {account})",
        spec,
        have,
        lambda: api.call("POST", url, spec),
        lambda: api.call(
            "PATCH",
            f"{BUDGETS}/{have['name']}",
            spec,
            params={"updateMask": ",".join(BUDGET_FIELDS)},
        ),
    )


def budget_denied(plan, spec, error):
    plan.item(
        "SKIP",
        "budget",
        spec["displayName"],
        "the active gcloud account lacks billing budget permissions (needs Billing Account "
        f"Administrator or Costs Manager on the billing account): {error.body[:200]}",
    )


# ---------------------------------------------------------------- read-only validation


def required(kind, name, spec, fields):
    missing = [field for field in fields if field not in spec]
    return [f"{kind} {name}: missing {', '.join(missing)}"] if missing else []


def structure_problems():
    problems = []
    for spec in load("log-metrics.json"):
        problems += required(
            "log metric", spec.get("name"), spec, ["name", "filter", "metricDescriptor"]
        )
        descriptor = spec.get("metricDescriptor", {})
        if descriptor.get("valueType") == "DISTRIBUTION":
            problems += required(
                "log metric", spec["name"], spec, ["valueExtractor", "bucketOptions"]
            )
        declared = {label["key"] for label in descriptor.get("labels", [])}
        if declared != set(spec.get("labelExtractors", {})):
            problems.append(f"log metric {spec['name']}: labels and labelExtractors differ")
        if declared & {"job_id", "line_id", "host"}:
            problems.append(f"log metric {spec['name']}: high-cardinality label")
    for spec in load("uptime-checks.json"):
        problems += required(
            "uptime check",
            spec.get("displayName"),
            spec,
            ["displayName", "monitoredResource", "httpCheck", "period", "timeout"],
        )
        if len(spec.get("selectedRegions", [])) < 3:
            problems.append(f"uptime check {spec['displayName']}: fewer than 3 regions")
    for spec in load("services.json"):
        problems += required(
            "service", spec.get("serviceId"), spec, ["serviceId", "displayName", "slos"]
        )
        for slo in spec.get("slos", []):
            problems += required(
                "SLO",
                slo.get("serviceLevelObjectiveId"),
                slo,
                ["serviceLevelObjectiveId", "goal", "rollingPeriod", "serviceLevelIndicator"],
            )
    for filename, spec in alert_specs():
        problems += required(
            "alert",
            filename,
            spec,
            ["displayName", "combiner", "conditions", "notificationChannels", "documentation"],
        )
        if "runbooks.md#" not in spec.get("documentation", {}).get("content", ""):
            problems.append(f"alert {filename}: documentation has no runbook link")
        for condition in spec.get("conditions", []):
            kinds = [k for k in condition if k.startswith("condition")]
            if len(kinds) != 1 or "displayName" not in condition:
                problems.append(
                    f"alert {filename}: condition needs displayName and one condition type"
                )
    spec = load("budget.json")
    problems += required("budget", spec.get("displayName"), spec, BUDGET_FIELDS)
    return problems


def promql_queries():
    queries = []
    for filename, spec in alert_specs():
        for condition in spec["conditions"]:
            if "conditionPrometheusQueryLanguage" in condition:
                queries.append(
                    (f"alert {filename}", condition["conditionPrometheusQueryLanguage"]["query"])
                )
    for tile in load("dashboard.json")["mosaicLayout"]["tiles"]:
        chart = tile["widget"].get("xyChart")
        for data_set in chart.get("dataSets", []) if chart else []:
            query = data_set["timeSeriesQuery"].get("prometheusQuery")
            if query:
                queries.append((f"dashboard {tile['widget']['title']}", query))
    return queries


def monitoring_filters():
    filters = []
    for filename, spec in alert_specs():
        for condition in spec["conditions"]:
            threshold = condition.get("conditionThreshold")
            if threshold:
                filters.append((f"alert {filename}", threshold["filter"]))
    for spec in load("services.json"):
        for slo in spec["slos"]:
            sli = slo["serviceLevelIndicator"]["requestBased"]
            for key, value in (
                sli.get("goodTotalRatio") or sli.get("distributionCut") or {}
            ).items():
                if key.endswith("Filter"):
                    filters.append((f"SLO {slo['serviceLevelObjectiveId']} {key}", value))
    for tile in load("dashboard.json")["mosaicLayout"]["tiles"]:
        scorecard = tile["widget"].get("scorecard")
        if scorecard:
            filters.append(
                (
                    f"dashboard {tile['widget']['title']}",
                    scorecard["timeSeriesQuery"]["timeSeriesFilter"]["filter"],
                )
            )
    return filters


def validate(api):
    print("\n== Validation (read-only)")
    failures = 0
    problems = structure_problems()
    for problem in problems:
        print(f"  FAIL   {problem}")
    failures += len(problems)
    print(f"  {'OK' if not problems else 'FAIL':<6} spec structure ({len(problems)} problems)")

    since = (dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for spec in load("log-metrics.json"):
        try:
            found = api.call(
                "POST",
                "https://logging.googleapis.com/v2/entries:list",
                {
                    "resourceNames": [f"projects/{PROJECT}"],
                    "filter": f'({spec["filter"]}) AND timestamp>="{since}"',
                    "pageSize": 5,
                },
            )
            print(
                f"  OK     log filter {spec['name']}: "
                f"{len(found.get('entries', []))} sample entries in 24 h"
            )
        except ApiError as error:
            failures += 1
            print(f"  FAIL   log filter {spec['name']}: {error}")

    for source, query in promql_queries():
        try:
            result = api.call("POST", PROMQL, form={"query": query})
            print(
                f"  OK     PromQL {source}: "
                f"{len(result.get('data', {}).get('result', []))} series now"
            )
        except ApiError as error:
            failures += 1
            print(f"  FAIL   PromQL {source}: {error}")

    end = dt.datetime.now(dt.UTC)
    for source, flt in monitoring_filters():
        params = {
            "filter": flt,
            "interval.startTime": (end - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval.endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "view": "HEADERS",
        }
        try:
            api.call("GET", f"{MONITORING}/timeSeries", params=params)
            print(f"  OK     filter {source}")
        except ApiError as error:
            pending = "select_slo_" in flt or "logging.googleapis.com/user/" in flt
            if pending and error.status in (400, 404):
                print(
                    f"  PEND   filter {source}: "
                    f"needs the metric or SLO to exist first ({error.status})"
                )
            else:
                failures += 1
                print(f"  FAIL   filter {source}: {error}")

    try:
        api.call("POST", DASHBOARDS, load("dashboard.json"), params={"validateOnly": "true"})
        print("  OK     dashboard validateOnly")
    except ApiError as error:
        failures += 1
        print(f"  FAIL   dashboard validateOnly: {error}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="make the changes (default: print the plan only)"
    )
    parser.add_argument(
        "--validate", action="store_true", help="also run read-only API validation of the specs"
    )
    parser.add_argument(
        "--budget-inr", type=int, default=2000, help="monthly budget amount in INR (default 2000)"
    )
    args = parser.parse_args()
    if args.budget_inr <= 0:
        parser.error("--budget-inr must be positive")

    api = Api()
    plan = Plan(args.apply)
    print(
        f"Project {PROJECT}: "
        f"{'APPLYING changes' if args.apply else 'plan only (no changes; pass --apply)'}"
    )
    log_metrics(api, plan)
    uptime_checks(api, plan)
    services(api, plan)
    alert_policies(api, plan)
    dashboard(api, plan)
    budget(api, plan, args.budget_inr)
    summary = ", ".join(f"{count} {verb.lower()}" for verb, count in plan.counts.items())
    print(f"\nSummary: {summary}")
    failures = validate(api) if args.validate else 0
    if args.validate:
        print(f"\nValidation: {'passed' if not failures else f'{failures} failure(s)'}")
    if plan.counts["ERROR"] or failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
