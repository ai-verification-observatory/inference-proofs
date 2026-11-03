"""The issue forms ask for every field RFC-0001 and RFC-0007 require."""

from pathlib import Path

import yaml

FORMS = Path(__file__).resolve().parents[3] / ".github/ISSUE_TEMPLATE"


def required(name: str) -> set[str]:
    form = yaml.safe_load((FORMS / name).read_text())
    return {b["id"] for b in form["body"] if b.get("validations", {}).get("required")}


def test_inclusion_requires_the_rfc_0001_fields() -> None:
    assert required("system-inclusion.yml") == {
        "repository", "commit", "workloads", "maintainers", "consent"
    }  # fmt: skip


def test_objection_names_a_review_check() -> None:
    form = yaml.safe_load((FORMS / "review-objection.yml").read_text())
    check = next(b for b in form["body"] if b.get("id") == "check")
    assert check["attributes"]["options"] == [
        "pins", "configuration", "logs", "derived_numbers", "controls"
    ]  # fmt: skip
    assert required("review-objection.yml") == {"run_id", "check", "text", "organisation"}


def test_security_reports_go_to_the_policy() -> None:
    config = yaml.safe_load((FORMS / "config.yml").read_text())
    assert config["contact_links"][0]["url"].endswith("/SECURITY.md")
