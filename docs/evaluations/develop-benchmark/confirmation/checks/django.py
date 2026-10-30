import os
from django.conf import settings
settings.configure(USE_I18N=False, SECRET_KEY="test", INSTALLED_APPS=[], TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates","APP_DIRS": True}])
import django
django.setup()
from django import forms

class RequiredForm(forms.Form):
    required_css_class = "required"
    name = forms.CharField()

field = RequiredForm({"name": "ok"})["name"]
attrs = {"class": "user-class"}
before = dict(attrs)
first = str(field.legend_tag(attrs=attrs))
second = str(field.legend_tag(attrs=attrs))
expected = (attrs == before and first == second and 'class="user-class required"' in first)
if os.environ["PANEL_STAGE"] == "preserve":
    expected = ("<legend" in first and "user-class" in first and "Name" in first)
print(first, second, attrs)
raise SystemExit(0 if expected else 42)
