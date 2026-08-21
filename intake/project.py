"""GitHub Projects v2 GraphQL client, without external dependencies."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class ProjectError(RuntimeError):
    pass


def _error_summary(payload: object) -> str:
    """GitHub's error type and message only, never our own request data."""
    if not isinstance(payload, dict):
        return "unreadable response"
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return "no data returned"
    parts = []
    for error in errors[:3]:
        if not isinstance(error, dict):
            continue
        kind = error.get("type") or "ERROR"
        message = str(error.get("message", ""))[:200]
        parts.append(f"{kind}: {message}")
    return "; ".join(parts) or "unspecified error"


class ProjectClient:
    def __init__(self, token: str, owner: str, number: int) -> None:
        self._token, self.owner, self.number = token, owner, number

    def _graphql(self, query: str, variables: dict) -> dict:
        request = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
            headers={"Authorization": f"bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # GitHub's own status text names permission problems and never
            # echoes our request body, so it is safe to surface.
            raise ProjectError(f"GitHub GraphQL HTTP {exc.code} {exc.reason}") from exc
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise ProjectError("GitHub GraphQL request failed") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict) or payload.get("errors"):
            raise ProjectError(f"GitHub GraphQL returned an error: {_error_summary(payload)}")
        return payload["data"]

    def resolve_project(self) -> str:
        data = self._graphql("""
          query($login:String!, $number:Int!) {
            user(login:$login) { projectV2(number:$number) { id } }
          }""", {"login": self.owner, "number": self.number})
        project = (data.get("user") or {}).get("projectV2")
        if not isinstance(project, dict) or not project.get("id"):
            raise ProjectError("GitHub project could not be resolved")
        return project["id"]

    def resolve_fields(self, project_id: str) -> dict[str, dict]:
        data = self._graphql("""
          query($id:ID!) { node(id:$id) { ... on ProjectV2 { fields(first:100) { nodes {
            ... on ProjectV2Field { id name }
            ... on ProjectV2SingleSelectField { id name options { id name } }
          } } } } }""", {"id": project_id})
        project = data.get("node")
        if not isinstance(project, dict):
            raise ProjectError("GitHub project fields could not be resolved")
        fields = {field["name"]: field for field in project.get("fields", {}).get("nodes", [])
                  if isinstance(field, dict) and field.get("name") and field.get("id")}
        return fields

    def add_draft_issue(self, project_id: str, title: str, body: str) -> str:
        data = self._graphql("""
          mutation($project:ID!, $title:String!, $body:String!) {
            addProjectV2DraftIssue(input:{projectId:$project, title:$title, body:$body}) {
              projectItem { id }
            }
          }""", {"project": project_id, "title": title, "body": body})
        item = (data.get("addProjectV2DraftIssue") or {}).get("projectItem")
        if not isinstance(item, dict) or not item.get("id"):
            raise ProjectError("GitHub did not return a created project item")
        return item["id"]

    def set_single_select(self, project_id: str, item_id: str, field_id: str, option_id: str) -> None:
        self._graphql("""
          mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) {
            updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,
              value:{singleSelectOptionId:$option}}) { projectV2Item { id } }
          }""", {"project": project_id, "item": item_id, "field": field_id, "option": option_id})
