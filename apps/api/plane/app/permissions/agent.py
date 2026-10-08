# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity Agent role (ROLE.AGENT = 10): server-side default-deny write guard.

Agents are ordinary users whose workspace role (and project role) is 10. They can read whatever a
Member can read, and the ONLY writes they may perform are listed in AGENT_WRITE_POLICY:
- change a work item's state through an allowed transition (never on epics, no other field)
- create comments, edit their OWN comments (never delete), upload/link comment images
- subscribe / unsubscribe themselves, personal UI preferences, notifications, stickies, quick links
Every other non-safe request from an agent is answered with HTTP 403
{"error": "...", "code": "AGENT_ACTION_FORBIDDEN" | "AGENT_FIELD_NOT_ALLOWED" | ...}.

Enforcement layers:
1. `AgentPolicyMixin` (first base of all four base view classes: app BaseViewSet/BaseAPIView and
   v1 BaseAPIView/BaseViewSet) runs `enforce_agent_policy` before the permission classes and before
   allow_permission's creator bypass, so it also closes undecorated routes (e.g. DRF's default
   "put" -> update) for agents.
2. `with_agent_role` widens allow_permission / ProjectEntityPermission role lists: agents get every
   read a Member gets, and only the whitelisted writes.
"""

# Python imports
from dataclasses import dataclass
from typing import Callable, Optional

# Third party imports
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS

# Module imports
from plane.db.models import FileAsset, Issue, IssueComment, ProjectMember, WorkspaceMember
from plane.db.models.project import ROLE

AGENT = ROLE.AGENT.value

AGENT_ACTION_FORBIDDEN = "AGENT_ACTION_FORBIDDEN"
AGENT_FIELD_NOT_ALLOWED = "AGENT_FIELD_NOT_ALLOWED"
AGENT_NOT_COMMENT_OWNER = "AGENT_NOT_COMMENT_OWNER"
AGENT_NOT_OWNER = "AGENT_NOT_OWNER"


class AgentDenied(PermissionDenied):
    """HTTP 403 whose JSON body is {"error": message, "code": code, ...extra}."""

    def __init__(self, message, code=AGENT_ACTION_FORBIDDEN, **extra):
        super().__init__()
        self.detail = {"error": message, "code": code, **extra}


@dataclass(frozen=True)
class AgentRule:
    # True: add AGENT to allow_permission / ProjectEntityPermission role lists for this endpoint.
    grant_role: bool = True
    # check(request, view) -> None, or raise AgentDenied / an APIException.
    check: Optional[Callable] = None


# ------------------------------------------------------------------ payload checks

# Keys an agent may send when moving a work item (the kanban drop sends {id, project_id, sort_order, state_id}).
ISSUE_STATE_KEYS = frozenset({"state_id", "state"})
ISSUE_STATE_META_KEYS = frozenset({"id", "project_id", "sort_order"})
# Keys an agent may send when creating / editing a comment.
COMMENT_KEYS = frozenset({"comment_html", "comment_json", "comment_stripped", "access"})


def _payload(request):
    data = request.data
    if not hasattr(data, "keys"):
        raise AgentDenied("The request body must be a JSON object.", AGENT_FIELD_NOT_ALLOWED)
    return data


def _reject_extra_keys(data, allowed, what):
    extra = sorted(set(data.keys()) - set(allowed))
    if extra:
        raise AgentDenied(
            f"Agents can only {what}; these fields are not allowed: {', '.join(extra)}.",
            AGENT_FIELD_NOT_ALLOWED,
            fields=extra,
        )


def check_issue_state_change(request, view):
    """Work item PATCH: state change only, through an allowed transition, never on an epic."""
    data = _payload(request)
    _reject_extra_keys(data, ISSUE_STATE_KEYS | ISSUE_STATE_META_KEYS, "change the state of a work item")
    targets = {str(data[key]) for key in ISSUE_STATE_KEYS if data.get(key)}
    if len(targets) > 1:
        # "state" and "state_id" both map to Issue.state: never let one hide the other
        raise AgentDenied("Send the target state only once.", AGENT_FIELD_NOT_ALLOWED, fields=sorted(ISSUE_STATE_KEYS))
    to_state_id = data.get("state_id") or data.get("state")
    if not to_state_id:
        raise AgentDenied(
            "Agents can only change the state of a work item.",
            AGENT_FIELD_NOT_ALLOWED,
            fields=sorted(data.keys()),
        )
    issue = (
        Issue.objects.filter(pk=view.kwargs.get("pk"), project_id=view.kwargs.get("project_id"))
        .select_related("type")
        .first()
    )
    if issue is None:
        return  # the view answers 404
    # Lazy import: plane.utils.workflow imports the models package at module level.
    from plane.utils.workflow import assert_state_transition_allowed

    assert_state_transition_allowed(
        issue=issue, to_state_id=to_state_id, role=AGENT, user=request.user, project_id=issue.project_id
    )


def check_comment_payload(request, view):
    """Comment create: content fields only (blocks the v1 created_by/actor impersonation path)."""
    _reject_extra_keys(_payload(request), COMMENT_KEYS, "write the comment content")


def check_own_comment(request, view):
    """Comment edit: content fields only, and only the agent's own comment."""
    check_comment_payload(request, view)
    if not IssueComment.objects.filter(
        pk=view.kwargs.get("pk"),
        issue_id=view.kwargs.get("issue_id"),
        project_id=view.kwargs.get("project_id"),
        actor=request.user,
    ).exists():
        raise AgentDenied("Agents can only edit their own comments.", AGENT_NOT_COMMENT_OWNER)


def check_self_member(request, view):
    """Per-member preferences: only the agent's own row."""
    if str(view.kwargs.get("member_id")) != str(request.user.id):
        raise AgentDenied("Agents can only change their own preferences.", AGENT_NOT_OWNER)


def check_comment_asset(request, view):
    """Project asset upload (POST) / upload confirmation (PATCH): comment images only."""
    comment_type = FileAsset.EntityTypeContext.COMMENT_DESCRIPTION
    if request.method == "POST":
        if _payload(request).get("entity_type") != comment_type:
            raise AgentDenied("Agents can only upload comment images.", AGENT_ACTION_FORBIDDEN)
        return
    if not FileAsset.objects.filter(
        pk=view.kwargs.get("pk"), created_by=request.user, entity_type=comment_type
    ).exists():
        raise AgentDenied("Agents can only update their own comment images.", AGENT_NOT_OWNER)


def check_comment_asset_link(request, view):
    """Bulk asset link: the agent's own comment images, attached to the agent's own comment."""
    asset_ids = _payload(request).get("asset_ids") or []
    if not isinstance(asset_ids, list) or not asset_ids:
        return  # the view answers 400
    own_comment_assets = FileAsset.objects.filter(
        id__in=asset_ids,
        created_by=request.user,
        entity_type=FileAsset.EntityTypeContext.COMMENT_DESCRIPTION,
    ).count()
    if own_comment_assets != len(set(map(str, asset_ids))):
        raise AgentDenied("Agents can only link their own comment images.", AGENT_NOT_OWNER)
    if not IssueComment.objects.filter(
        pk=view.kwargs.get("entity_id"), project_id=view.kwargs.get("project_id"), actor=request.user
    ).exists():
        raise AgentDenied("Agents can only link images to their own comments.", AGENT_NOT_COMMENT_OWNER)


# ------------------------------------------------------------------ the whitelist

# Keys: (module-qualified view class, DRF action for viewsets or lower-case HTTP method for API views);
# "*" matches every non-safe action of that view. Anything not listed is denied to agents.
_APP = "plane.app.views"
_V1 = "plane.api.views"
_PERSONAL = AgentRule()

AGENT_WRITE_POLICY = {
    # --- internal web API (session) ---
    (f"{_APP}.issue.base.IssueViewSet", "partial_update"): AgentRule(True, check_issue_state_change),
    (f"{_APP}.issue.comment.IssueCommentViewSet", "create"): AgentRule(True, check_comment_payload),
    # grant_role=False: allow_permission([ADMIN], creator=True) already limits edits to the author.
    (f"{_APP}.issue.comment.IssueCommentViewSet", "partial_update"): AgentRule(False, check_own_comment),
    (f"{_APP}.issue.subscriber.IssueSubscriberViewSet", "subscribe"): _PERSONAL,
    (f"{_APP}.issue.subscriber.IssueSubscriberViewSet", "unsubscribe"): _PERSONAL,
    (f"{_APP}.asset.v2.ProjectAssetEndpoint", "post"): AgentRule(True, check_comment_asset),
    (f"{_APP}.asset.v2.ProjectAssetEndpoint", "patch"): AgentRule(True, check_comment_asset),
    (f"{_APP}.asset.v2.ProjectBulkAssetEndpoint", "post"): AgentRule(True, check_comment_asset_link),
    # personal UI state
    (f"{_APP}.issue.base.ProjectUserDisplayPropertyEndpoint", "patch"): _PERSONAL,
    (f"{_APP}.project.member.ProjectMemberPreferenceEndpoint", "patch"): AgentRule(True, check_self_member),
    (f"{_APP}.cycle.base.CycleUserPropertiesEndpoint", "patch"): _PERSONAL,
    (f"{_APP}.module.base.ModuleUserPropertiesEndpoint", "patch"): _PERSONAL,
    (f"{_APP}.notification.base.NotificationViewSet", "*"): _PERSONAL,
    (f"{_APP}.notification.base.MarkAllReadNotificationViewSet", "create"): _PERSONAL,
    (f"{_APP}.workspace.user.WorkspaceUserPropertiesEndpoint", "patch"): _PERSONAL,
    (f"{_APP}.workspace.user_preference.WorkspaceUserPreferenceViewSet", "patch"): _PERSONAL,
    (f"{_APP}.workspace.home.WorkspaceHomePreferenceViewSet", "patch"): _PERSONAL,
    (f"{_APP}.workspace.member.WorkspaceMemberUserViewsEndpoint", "post"): _PERSONAL,
    (f"{_APP}.workspace.sticky.WorkspaceStickyViewSet", "*"): _PERSONAL,
    (f"{_APP}.workspace.quick_link.QuickLinkViewSet", "*"): _PERSONAL,
    # --- public API v1 (X-Api-Key) ---
    (f"{_V1}.issue.IssueDetailAPIEndpoint", "patch"): AgentRule(True, check_issue_state_change),
    (f"{_V1}.issue.IssueCommentListCreateAPIEndpoint", "post"): AgentRule(True, check_comment_payload),
    (f"{_V1}.issue.IssueCommentDetailAPIEndpoint", "patch"): AgentRule(True, check_own_comment),
}

# Endpoints without a workspace in the URL that an agent-only account may not use.
AGENT_USER_DENY = frozenset({(f"{_APP}.workspace.base.WorkSpaceViewSet", "create")})


def _view_path(view):
    cls = view.__class__
    return f"{cls.__module__}.{cls.__qualname__}"


def _action(view, request):
    return getattr(view, "action", None) or request.method.lower()


def get_agent_rule(view, request):
    path = _view_path(view)
    return AGENT_WRITE_POLICY.get((path, _action(view, request))) or AGENT_WRITE_POLICY.get((path, "*"))


def agent_write_grant(view, request):
    """True when this (view, action) is a whitelisted agent write that needs the AGENT role added."""
    rule = get_agent_rule(view, request)
    return bool(rule and rule.grant_role)


def with_agent_role(allowed_role_values, view, request):
    """Role list for allow_permission / permission classes with the Agent role added when due:
    reads that Members may do, and whitelisted writes."""
    values = list(allowed_role_values)
    if AGENT in values:
        return values
    if request.method in SAFE_METHODS:
        if ROLE.MEMBER.value in values:
            values.append(AGENT)
    elif agent_write_grant(view, request):
        values.append(AGENT)
    return values


# ------------------------------------------------------------------ agent detection


def _view_project_id(view):
    project_id = view.kwargs.get("project_id")
    if project_id:
        return project_id
    try:
        return getattr(view, "project_id", None)
    except Exception:  # noqa: BLE001 - the property resolves the URL; never fail the guard on it
        return None


def is_agent_request(request, view):
    """True when the requester acts as an Agent in the URL's project or workspace (cached per request).

    Endpoints without a workspace in the URL (users/me/*, personal API tokens) are personal and are
    not treated as agent requests.
    """
    cached = getattr(request, "_jp_is_agent", None)
    if cached is not None:
        return cached
    user = request.user
    is_agent = False
    project_id = _view_project_id(view)
    if project_id:
        is_agent = ProjectMember.objects.filter(member=user, project_id=project_id, is_active=True, role=AGENT).exists()
    if not is_agent:
        slug = view.kwargs.get("slug")
        workspace_id = view.kwargs.get("workspace_id")
        if slug or workspace_id:
            workspace_filter = {"workspace__slug": slug} if slug else {"workspace_id": workspace_id}
            is_agent = WorkspaceMember.objects.filter(
                member=user, is_active=True, role=AGENT, **workspace_filter
            ).exists()
    request._jp_is_agent = is_agent
    return is_agent


def is_agent_only_user(user):
    """True when every active workspace membership of `user` has the Agent role."""
    roles = set(WorkspaceMember.objects.filter(member=user, is_active=True).values_list("role", flat=True))
    return bool(roles) and roles == {AGENT}


def enforce_agent_policy(view, request):
    """Raise AgentDenied unless the request is a read, not from an agent, or whitelisted."""
    if request.method in SAFE_METHODS:
        return
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return
    if not is_agent_request(request, view):
        if (_view_path(view), _action(view, request)) in AGENT_USER_DENY and is_agent_only_user(user):
            raise AgentDenied("Agent accounts cannot perform this action.")
        return
    rule = get_agent_rule(view, request)
    if rule is None:
        raise AgentDenied("Agents are not allowed to perform this action.")
    if rule.check is not None:
        rule.check(request, view)


class AgentPolicyMixin:
    """First base of every API base view: runs the agent guard ahead of the permission classes."""

    def check_permissions(self, request):
        enforce_agent_policy(self, request)
        super().check_permissions(request)
