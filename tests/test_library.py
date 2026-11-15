"""Offline checks for the Orqen email workflow library (stdlib only).

Run:  python -m unittest discover -s tests -v

They catch what would otherwise only fail inside Orqen at run time:
broken @references, wrong branch names, literal secrets in the repo, and
request templates that do not render to valid JSON.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"\{\{(.*?)\}\}", re.S)
KNOWN_CAPABILITIES = {
    "text.analyze", "text.validate", "text.keyword", "ai.chat", "tool.external", "http.request",
    "text.template", "data.parse", "data.validate", "context.kv_set", "flow.if", "flow.switch",
    "mail.message.parse", "mail.metadata.extract", "mail.content.extract", "mail.security.assess",
    "mail.rules.classify", "mail.actions.plan", "mail.address.normalize",
}
FLOW = {"flow.if", "flow.switch"}
REF_ROOTS = ("run", "ctx", "env", "node", "kv", "input", "sys")


def load(folder):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / folder).glob("*.json"))}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def refs_of(folder, by_name=True):
    items = load(folder)
    names = set(items)
    if by_name:
        names |= {slug(v["name"]) for v in items.values()}
    return names


def skills():
    return {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}


def templates_of(node):
    """Every template string a node carries, with a label."""
    out = []
    p = node.get("params", {})
    for key in ("template", "url", "body", "condition", "key", "namespace"):
        if isinstance(p.get(key), str):
            out.append((f"params.{key}", p[key]))
    for case in p.get("cases", []):
        out.append((f"case {case['name']}", case["condition"]))
    for port, src in node.get("inputs", {}).items():
        if isinstance(src, dict) and isinstance(src.get("value"), str):
            out.append((f"inputs.{port}", src["value"]))
    pol = node.get("policy", {})
    if pol.get("runIf"):
        out.append(("policy.runIf", pol["runIf"]))
    return out


# ------------------------------------------------- tiny template renderer
# Mirrors Orqen's expr.rs closely enough to prove the JSON request bodies
# are well-formed for realistic (and hostile) values.
def navigate(value, path):
    for seg in path:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return None
        if isinstance(value, dict):
            value = value.get(seg)
        elif isinstance(value, list) and seg.isdigit() and int(seg) < len(value):
            value = value[int(seg)]
        else:
            return None
        if value is None:
            return None
    return value


def text(value):
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))


def render(template, scope):
    def one(match):
        parts = [p.strip() for p in match.group(1).split("|")]
        ref = parts[0].split(".")
        root = ref[0]
        if root == "node":
            value = navigate(scope["node"].get(ref[1], {}).get(ref[2]), ref[3:])
        elif root in ("ctx", "env"):
            value = scope["ctx"].get(ref[1])
        elif root == "run":
            value = navigate(scope["run"], ref[1:]) if len(ref) > 1 else json.dumps(scope["run"])
        elif root == "sys":
            value = "2026-11-14T08:00:00Z"
        elif root == "kv":
            value = None
        else:
            return match.group(0)
        for f in parts[1:]:
            if f.startswith("default:"):
                if value in (None, ""):
                    value = f[len("default:"):].strip().strip("'\"")
            elif value is None:
                raise KeyError(f"{match.group(0)} has no value")
            elif f == "json":
                value = json.dumps(value if not isinstance(value, (dict, list)) else value) if isinstance(value, str) else json.dumps(value)
            elif f == "escape":
                value = json.dumps(text(value))[1:-1]
            elif f == "fields":
                obj = value if isinstance(value, dict) else json.loads(value)
                value = json.dumps(obj)[1:-1]
            elif f == "trim":
                value = text(value).strip()
            elif f == "url":
                from urllib.parse import quote
                value = quote(text(value), safe="-_.~")
        if value is None:
            raise KeyError(f"{match.group(0)} has no value")
        return text(value)
    return TOKEN.sub(one, template)


HOSTILE = 'He said "hi" \\ then\nnew line\t{{not a ref}} </script>'
SCOPE = {
    "run": {"message_id": "<a\"b@mail>", "from": "ada@example.org", "from_name": "Ada", "subject": HOSTILE,
            "body": HOSTILE, "to": "ada@example.org", "template_id": "welcome", "variables": {"name": "Ada"},
            "idempotency_key": "evt-12345678", "uid": "42", "folder": "INBOX", "raw": HOSTILE},
    "ctx": {"SUPPORT_FROM": "support@example.com", "SUPPORT_TEAM_EMAIL": "team@example.com", "SUPPORT_SIGNATURE": "— Support",
            "NOTIFY_FROM": "no-reply@example.com", "DIGEST_TO": "ops@example.com", "EMAIL_AUDIT_LOG": "false", "CRM_ENABLED": "false"},
    "node": {},
}


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.workflows = load("workflows")
        self.connectors = refs_of("connectors")
        self.credentials = refs_of("credentials")
        self.types = refs_of("types")
        self.skills = skills()

    def resolve(self, ref, pool, what):
        self.assertTrue(ref.startswith("@"), f"{what} reference {ref!r} should use @slug")
        self.assertIn(ref[1:], pool, f"unknown {what} {ref}")

    def test_manifest(self):
        manifest = json.loads((ROOT / "orqen.json").read_text(encoding="utf-8"))
        for key in ("name", "version", "description", "orqen"):
            self.assertTrue(manifest.get(key), key)
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$", "library version must be semver")
        self.assertRegex(manifest["orqen"], r"^(>=|\^|=)?\d+\.\d+(\.\d+)?$", "orqen requirement")
        for package, requirement in manifest.get("packages", {}).items():
            self.assertRegex(package, r"^(core|mail)\.[a-z]+$", "package id")
            self.assertRegex(requirement, r"^(>=|\^|=)?\d+\.\d+(\.\d+)?$", f"{package} requirement")

    def test_mailbox_mutations_are_guarded(self):
        """Inbox intelligence can only change a mailbox behind every guard."""
        graph = self.workflows["email-inbox-intelligence"]["graph"]
        nodes = {n["id"]: n for n in graph["nodes"]}
        plan, apply = nodes["plan"], nodes["apply"]
        self.assertIn("default:dry-run", plan["inputs"]["mode"]["value"], "dry-run unless the context opts in")
        self.assertLessEqual(set(plan["params"]["allow"]), {"mark_read", "mark_unread", "archive"},
                             "no destructive action is allow-listed")
        self.assertEqual(apply["policy"]["runIf"], "{{ node.plan.mutate }} == true")
        # Bodies are rendered before the run even when run-if skips the node,
        # so a raw-message run (no uid) needs a default.
        self.assertIn("run.uid | default:''", nodes["fetch"]["params"]["body"])
        self.assertIn("run.account | default:''", nodes["fetch"]["params"]["body"],
                      "the run names the mailbox; the planner's apply request echoes it")
        self.assertEqual(apply["policy"].get("retries", 0), 0, "a move is not idempotent: never retry it blindly")
        self.assertEqual(apply["params"]["body"], "{{ node.plan.request }}",
                         "the request comes from the planner, not from run input")
        writers = [n["id"] for n in graph["nodes"]
                   if n["capability"] == "http.request" and "mailbox.get_raw" not in n["params"].get("body", "")]
        self.assertEqual(writers, ["apply"], "exactly one node can write")
        ctx = json.loads((ROOT / "contexts" / "email-local.json").read_text(encoding="utf-8"))
        mode = [v["value"] for v in ctx["variables"] if v["key"] == "MAIL_MODE"]
        self.assertEqual(mode, ["dry-run"])

    def test_credentials_hold_no_literal_secrets(self):
        for name, cred in load("credentials").items():
            self.assertIn(cred["kind"], {"bearer", "basic", "header", "query"}, name)
            secret = cred.get("secret", "")
            self.assertRegex(secret, r"^\{\{\s*ctx\.[A-Z0-9_]+\s*\}\}$", f"{name}: secrets must be context references")
        for name, ctx in load("contexts").items():
            for var in ctx["variables"]:
                if var.get("secret"):
                    self.assertFalse(var.get("value"), f"{name}.{var['key']}: secret values never ship in a repo")

    def test_connectors(self):
        for name, conn in load("connectors").items():
            url = conn["baseUrl"]
            self.assertTrue(url.startswith("https://") or re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", url), name)
            self.assertNotIn("?", url, name)
            if conn.get("credential"):
                self.resolve(conn["credential"], self.credentials, "credential")

    def test_workflow_structure_and_references(self):
        for wname, wf in self.workflows.items():
            graph = wf["graph"]
            nodes = {n["id"]: n for n in graph["nodes"]}
            self.assertEqual(len(nodes), len(graph["nodes"]), f"{wname}: duplicate node ids")
            self.assertLessEqual(len(wf.get("description", "")), 400, f"{wname}: Orqen rejects descriptions over 400 characters")
            if graph.get("inputType"):
                self.resolve(graph["inputType"], self.types, "type")
            for node in graph["nodes"]:
                label = f"{wname}.{node['id']}"
                self.assertIn(node["capability"], KNOWN_CAPABILITIES, label)
                p = node.get("params", {})
                if p.get("connector"):
                    self.resolve(p["connector"], self.connectors, "connector")
                for skill in p.get("skills", []):
                    self.resolve(skill, self.skills, "skill")
                pol = node.get("policy", {})
                self.assertIn(pol.get("onError", "fail"), {"fail", "continue", "fallback"}, label)
                self.assertLessEqual(pol.get("retries", 0), 5, label)
                for where, template in templates_of(node):
                    self.assertEqual(template.count("{{"), template.count("}}"), f"{label} {where}: unbalanced braces")
                    for token in TOKEN.findall(template):
                        ref = token.split("|")[0].strip()
                        root = ref.split(".")[0]
                        self.assertIn(root, REF_ROOTS, f"{label} {where}: unknown reference {{{{{token}}}}}")
                        if root == "node":
                            self.assertIn(ref.split(".")[1], nodes, f"{label} {where}: unknown node in {ref}")
            for edge in graph["edges"]:
                self.assertIn(edge["from"], nodes)
                self.assertIn(edge["to"], nodes)
                when = edge.get("when", "success")
                if when.startswith("case:"):
                    source = nodes[edge["from"]]
                    self.assertIn(source["capability"], FLOW, f"{wname}: case edge from non-flow node")
                    if source["capability"] == "flow.switch":
                        names = {c["name"] for c in source["params"]["cases"]} | {source["params"].get("default", "default")}
                    else:
                        names = {"true", "false"}
                    self.assertIn(when[5:], names, f"{wname}: {edge}")
                else:
                    self.assertIn(when, {"success", "failure", "always"}, f"{wname}: {edge}")

    def test_every_failure_path_is_handled(self):
        """Nodes that talk to the outside world either retry, tolerate failure, or have a failure branch."""
        for wname, wf in self.workflows.items():
            graph = wf["graph"]
            handled = {e["from"] for e in graph["edges"] if e.get("when") in ("failure", "always")}
            for node in graph["nodes"]:
                if node["capability"] in ("http.request", "ai.chat"):
                    pol = node.get("policy", {})
                    ok = node["id"] in handled or pol.get("onError") in ("continue", "fallback") or pol.get("retries", 0) > 0
                    self.assertTrue(ok, f"{wname}.{node['id']} has no failure handling")

    def test_request_templates_render_valid_json(self):
        """Every JSON body/template renders to valid JSON, even for hostile input."""
        node_outputs = {
            "draft": {"text": HOSTILE}, "intake": {"error": "Validation failed: 'from' is not a valid email"},
            "route": {"branch": "auto-reply"}, "preflight": {"body": '{"valid": true}'}, "send": {"text": "exec_1", "status": 200},
            "notify-team": {"text": "exec_2"}, "summarize": {"text": HOSTILE}, "digest": {"text": "exec_3"},
            "fetch": {"body": "[]", "error": "HTTP 503", "text": "{}"}, "check": {"error": "bad"},
            "classify": {"text": json.dumps({"message": {"fingerprint": "fnv1a64:1"}}), "category": HOSTILE,
                         "confidence": 80, "priority": "low", "labels": HOSTILE},
            "security": {"verdict": "neutral", "risk_score": 5, "suspicious": False,
                         "text": json.dumps({"security": {"signals": [{"id": "x", "weight": 5, "detail": HOSTILE}]}})},
            "plan": {"text": json.dumps({"mode": "dry-run", "actions": [{"kind": "archive", "status": "dry_run", "reason": HOSTILE}]}),
                     "needs_review": False, "mutate": False,
                     "request": json.dumps({"action": "mailbox.apply", "uid": "42", "operations": [{"op": "archive"}]})},
            "apply": {"text": json.dumps({"applied": 1}), "error": HOSTILE},
        }
        for wname, wf in self.workflows.items():
            scope = dict(SCOPE, node=dict(node_outputs))
            graph = wf["graph"]
            # Compose nodes first so later bodies can splice their output.
            for node in graph["nodes"]:
                if node["capability"] == "text.template" and node["params"]["template"].lstrip().startswith("{"):
                    rendered = render(node["params"]["template"], scope)
                    try:
                        json.loads(rendered)
                    except ValueError as error:
                        self.fail(f"{wname}.{node['id']} template is not JSON: {error}\n{rendered}")
                    scope["node"][node["id"]] = {"text": rendered}
            for node in graph["nodes"]:
                candidates = []
                if node["capability"] == "http.request" and node["params"].get("body"):
                    candidates.append(("body", node["params"]["body"]))
                for port, src in node.get("inputs", {}).items():
                    value = src.get("value", "").lstrip() if isinstance(src, dict) else ""
                    # A JSON body starts with one brace; "{{" is an expression.
                    if value.startswith("{") and not value.startswith("{{"):
                        candidates.append((f"inputs.{port}", src["value"]))
                for where, template in candidates:
                    rendered = render(template, scope)
                    try:
                        json.loads(rendered)
                    except ValueError as error:
                        self.fail(f"{wname}.{node['id']} {where} is not JSON: {error}\n{rendered}")

    def test_missions(self):
        wf_refs = set(self.workflows) | {slug(w["name"]) for w in self.workflows.values()}
        for name, ms in load("missions").items():
            self.assertIn(ms["mode"], {"manual", "scheduled", "webhook", "agent"}, name)
            for ref in ms["workflows"]:
                self.resolve(ref, wf_refs, "workflow")
            feed = ms.get("feed")
            if feed:
                self.resolve(feed["connector"], self.connectors, "connector")
                self.assertTrue(feed["path"].startswith("/"), name)
                self.assertRegex(feed["key"], r"^[A-Za-z0-9_-]+$", name)
                self.assertLessEqual(feed.get("max", 10), 50, name)
                self.assertEqual(ms["mode"], "scheduled", f"{name}: a feed is polled by the scheduler")
                self.assertFalse(ms.get("enabled", True), f"{name}: a polling mission must install disabled")
            if ms["mode"] == "scheduled":
                self.assertTrue(ms.get("scheduleAt") or ms.get("scheduleEverySecs"), name)
                if ms.get("scheduleAt"):
                    self.assertRegex(ms["scheduleAt"], r"^([01]\d|2[0-3]):[0-5]\d$", name)

    def test_examples_match_their_types(self):
        types = load("types")
        for example, type_name in [("inbound-email", "inbound-email"), ("inbound-email-escalate", "inbound-email"),
                                   ("transactional-email", "transactional-email")]:
            doc = json.loads((ROOT / "examples" / f"{example}.json").read_text(encoding="utf-8"))
            for field in types[type_name]["required"]:
                self.assertTrue(doc.get(field), f"{example} misses {field}")


if __name__ == "__main__":
    unittest.main()
