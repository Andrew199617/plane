# Jira-parity: cycles are sprints with an explicit lifecycle and modules are releases (fix versions).
# - Cycle.started_at / completed_at: a sprint is future until started and active until completed. Existing cycles
#   keep the state their dates implied: running ones are active, ended ones are closed.
# - Module.status: only "unreleased" (default) and "released". Completed modules become released, all others
#   unreleased. The reverse maps released -> completed and unreleased -> planned.

from django.db import migrations, models
from django.db.models import F, Q
from django.utils import timezone


def backfill_sprint_states(apps, schema_editor):
    Cycle = apps.get_model("db", "Cycle")
    now = timezone.now()
    Cycle.objects.filter(start_date__lte=now, end_date__lt=now).update(
        started_at=F("start_date"), completed_at=F("end_date")
    )
    Cycle.objects.filter(start_date__lte=now, end_date__gte=now).update(started_at=F("start_date"))


def map_module_statuses(apps, schema_editor):
    Module = apps.get_model("db", "Module")
    Module.objects.filter(status="completed").update(status="released")
    Module.objects.filter(~Q(status__in=["released", "unreleased"])).update(status="unreleased")


def unmap_module_statuses(apps, schema_editor):
    Module = apps.get_model("db", "Module")
    Module.objects.filter(status="released").update(status="completed")
    Module.objects.filter(status="unreleased").update(status="planned")


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0132_jp_agent_security_cleanup"),
    ]

    operations = [
        migrations.AddField(
            model_name="cycle",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="cycle",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_sprint_states, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="module",
            name="status",
            field=models.CharField(
                choices=[("unreleased", "Unreleased"), ("released", "Released")],
                default="unreleased",
                max_length=20,
            ),
        ),
        migrations.RunPython(map_module_statuses, unmap_module_statuses),
    ]
