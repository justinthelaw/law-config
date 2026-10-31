import os
from django.conf import settings
settings.configure(INSTALLED_APPS=[], DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":":memory:"}})
import django
django.setup()
from django.db import connection, models
from django.db.models import Q
class Label(models.Model):
    value = models.TextField()
    class Meta: app_label = "panel"
class Item(models.Model):
    label = models.ForeignKey(Label, null=True, on_delete=models.SET_NULL)
    class Meta: app_label = "panel"
with connection.schema_editor() as editor:
    editor.create_model(Label)
    editor.create_model(Item)
tag = Label.objects.create(value="kept")
a = Item.objects.create(label=tag)
b = Item.objects.create(label=None)
c = Item.objects.create(label=tag)
by_tag, by_missing = Q(label__value="kept"), Q(pk=b.pk)
cases = [(by_tag & Q(pk=a.pk),[a.pk]), (by_tag | by_missing,[a.pk,b.pk,c.pk])]
if os.environ["PANEL_STAGE"] == "contract":
    cases = [(Q(label__value__isnull=False) ^ by_missing,[a.pk,b.pk,c.pk]),
             (~(Q(label__value__isnull=True) ^ by_missing),[a.pk,b.pk,c.pk])]
for condition, expected in cases:
    q = Item.objects.filter(condition).order_by("pk")
    got = list(q.values_list("pk", flat=True))
    if got != expected:
        print(q.query, got, expected)
        raise SystemExit(42)
