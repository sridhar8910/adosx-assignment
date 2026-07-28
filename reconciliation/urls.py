from django.urls import path

from . import views

urlpatterns = [
    path("disagreements/", views.disagreements, name="disagreements"),
    path("import-issues/", views.import_issues, name="import-issues"),
    path("reasons/", views.reasons, name="reasons"),
    path("orgs/", views.orgs, name="orgs"),
    path("reconcile/", views.trigger_reconcile, name="reconcile"),
]
