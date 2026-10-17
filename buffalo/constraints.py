"""Database constraints whose violations are reported against a form field.

Django files every `CheckConstraint` violation, and every expression-based
`UniqueConstraint` violation, under a form's non-field errors (the top of the
form). These variants take a `field` and attach the message to that field
instead, so a constraint can replace a field-level check in `clean()`.

`field` must be one the constraint refers to. Forms skip constraints that refer
to fields they don't include, which keeps Django from attaching an error to a
field the form doesn't show. The database still enforces the constraint.
"""

from collections.abc import Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS
from django.db.models import BaseConstraint, CheckConstraint, Model, UniqueConstraint


class ReportedOnField(BaseConstraint):
    field: str

    def __init__(self, *args: Any, field: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.field = field

    def validate(
        self,
        model: type[Model],
        instance: Model,
        exclude: set[str] | None = None,
        using: str = DEFAULT_DB_ALIAS,
    ) -> None:
        try:
            super().validate(model, instance, exclude=exclude, using=using)
        except ValidationError as error:
            raise ValidationError({self.field: error}) from None

    def deconstruct(self) -> tuple[str, Sequence[Any], dict[str, Any]]:
        path, args, kwargs = super().deconstruct()
        return path, args, {**kwargs, "field": self.field}

    def __eq__(self, other: object) -> bool:
        equal = super().__eq__(other)
        if equal is NotImplemented or not equal:
            return equal
        return getattr(other, "field", None) == self.field


class FieldCheckConstraint(ReportedOnField, CheckConstraint):
    pass


class FieldUniqueConstraint(ReportedOnField, UniqueConstraint):
    pass
