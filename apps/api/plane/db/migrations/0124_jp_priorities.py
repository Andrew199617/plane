# Jira-parity priorities: highest / high / medium (default) / low / lowest.
# Data: urgent -> highest, none -> medium on every priority column (issues, draft_issues,
# issue_versions), on priority activity rows, and inside saved filter JSON (views, user
# properties, analytics, legacy member view props). Reverse is best effort:
# highest -> urgent, lowest -> low (medium stays medium; the original "none" is lost).

from django.db import migrations, models


PRIORITY_CHOICES = [
    ("highest", "Highest"),
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
    ("lowest", "Lowest"),
]

FORWARD_MAP = {"urgent": "highest", "none": "medium"}
BACKWARD_MAP = {"highest": "urgent", "lowest": "low"}

PRIORITY_MODELS = ["Issue", "DraftIssue", "IssueVersion"]

# (model name, JSON fields that may hold saved priority filters)
FILTER_MODELS = [
    ("IssueView", ["filters", "rich_filters", "query"]),
    ("ProjectUserProperty", ["filters", "rich_filters"]),
    ("IssueUserProperty", ["filters", "rich_filters"]),
    ("CycleUserProperties", ["filters", "rich_filters"]),
    ("ModuleUserProperties", ["filters", "rich_filters"]),
    ("WorkspaceUserProperties", ["filters", "rich_filters"]),
    ("AnalyticView", ["query", "query_dict"]),
    ("ProjectMember", ["view_props", "default_props"]),
]

PRIORITY_KEYS = {"priority", "priority__in", "priority__exact"}


def _dedupe(values):
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _remap_value(value, mapping):
    if isinstance(value, str):
        return ",".join(_dedupe([mapping.get(part, part) for part in value.split(",")]))
    if isinstance(value, list):
        return _dedupe([mapping.get(v, v) if isinstance(v, str) else v for v in value])
    return value


def remap_priority_tree(node, mapping):
    """Walk dicts/lists (and/or/not trees included) and remap values under priority keys."""
    if isinstance(node, dict):
        return {
            key: (_remap_value(value, mapping) if key in PRIORITY_KEYS else remap_priority_tree(value, mapping))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [remap_priority_tree(item, mapping) for item in node]
    return node


def _get_model(apps, name):
    try:
        return apps.get_model("db", name)
    except LookupError:
        return None


def _remap(apps, mapping):
    for name in PRIORITY_MODELS:
        model = apps.get_model("db", name)
        for old, new in mapping.items():
            model._base_manager.filter(priority=old).update(priority=new)

    IssueActivity = apps.get_model("db", "IssueActivity")
    for old, new in mapping.items():
        IssueActivity._base_manager.filter(field="priority", old_value=old).update(old_value=new)
        IssueActivity._base_manager.filter(field="priority", new_value=old).update(new_value=new)

    for name, candidate_fields in FILTER_MODELS:
        model = _get_model(apps, name)
        if model is None:
            continue
        model_fields = {f.name for f in model._meta.get_fields()}
        fields = [f for f in candidate_fields if f in model_fields]
        if not fields:
            continue
        changed = []
        for obj in model._base_manager.only("pk", *fields).iterator(chunk_size=1000):
            dirty = False
            for field in fields:
                value = getattr(obj, field)
                if not value:
                    continue
                new_value = remap_priority_tree(value, mapping)
                if new_value != value:
                    setattr(obj, field, new_value)
                    dirty = True
            if dirty:
                changed.append(obj)
        if changed:
            model._base_manager.bulk_update(changed, fields, batch_size=1000)


def forwards(apps, schema_editor):
    _remap(apps, FORWARD_MAP)


def backwards(apps, schema_editor):
    _remap(apps, BACKWARD_MAP)


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0123_jp_agent_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="draftissue",
            name="priority",
            field=models.CharField(
                choices=PRIORITY_CHOICES, default="medium", max_length=30, verbose_name="Issue Priority"
            ),
        ),
        migrations.AlterField(
            model_name="issue",
            name="priority",
            field=models.CharField(
                choices=PRIORITY_CHOICES, default="medium", max_length=30, verbose_name="Issue Priority"
            ),
        ),
        migrations.AlterField(
            model_name="issueversion",
            name="priority",
            field=models.CharField(
                choices=PRIORITY_CHOICES, default="medium", max_length=30, verbose_name="Issue Priority"
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
