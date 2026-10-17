from django.urls import path

from buffalo import views

app_name = "buffalo"

urlpatterns = [
    path("", views.index, name="index"),
    path("entry/intake/", views.entry_intake, name="entry_intake"),
    path("entry/condition/", views.entry_condition, name="entry_condition"),
    path("entry/sample/", views.entry_sample, name="entry_sample"),
    path("options/animals/", views.animal_options, name="animal_options"),
    path("animals/", views.animal_table, name="animal_table"),
    path("animals/<int:pk>/row/", views.animal_row, name="animal_row"),
    path("animals/<int:pk>/detail/", views.animal_detail, name="animal_detail"),
    path("animals/<int:pk>/edit/", views.animal_edit, name="animal_edit"),
    path("animals/<int:pk>/death/", views.animal_death, name="animal_death"),
    path("animals/<int:pk>/history/", views.animal_history, name="animal_history"),
    path("animals/<int:pk>/attachments/", views.attachment_upload, name="attachment_upload"),
    path("conditions/<int:pk>/edit/", views.condition_edit, name="condition_edit"),
    path("samples/<int:pk>/edit/", views.sample_edit, name="sample_edit"),
    path("attachments/<int:pk>/", views.attachment_delete, name="attachment_delete"),
    path("attachments/<int:pk>/download/", views.attachment_download, name="attachment_download"),
    path(
        "attachments/<int:pk>/thumbnail/", views.attachment_thumbnail, name="attachment_thumbnail"
    ),
    path("lookups/<slug:kind>/add/", views.lookup_add, name="lookup_add"),
    path("export/", views.export_csv, name="export_csv"),
]
