# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity agents serializers.

Shapes (packages/types/src/jira-parity/agents.ts):
- agent  {id (workspace member id), member: {id, display_name, first_name, last_name, email,
          avatar_url}, role, project_count, tokens: [token]}
- token  {id, label, last_used, expired_at, is_active, created_at} (+ `token` only when created)
"""

# Third party imports
from rest_framework import serializers

__all__ = [
    "AgentCreateSerializer",
    "AgentUpdateSerializer",
    "AgentTokenCreateSerializer",
    "serialize_agent",
    "serialize_agent_token",
]


class AgentCreateSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=255, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    first_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    generate_token = serializers.BooleanField(required=False, default=True)
    token_label = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)


class AgentUpdateSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=255, required=False, trim_whitespace=True)
    first_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AgentTokenCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)


def serialize_agent_token(token, include_secret=False):
    data = {
        "id": str(token.id),
        "label": token.label,
        "last_used": token.last_used,
        "expired_at": token.expired_at,
        "is_active": token.is_active,
        "created_at": token.created_at,
    }
    if include_secret:
        data["token"] = token.token
    return data


def serialize_agent(workspace_member, *, project_count=0, tokens=()):
    user = workspace_member.member
    return {
        "id": str(workspace_member.id),
        "member": {
            "id": str(user.id),
            "display_name": user.display_name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "avatar_url": user.avatar_url,
        },
        "role": workspace_member.role,
        "project_count": project_count,
        "tokens": [serialize_agent_token(token) for token in tokens],
    }
