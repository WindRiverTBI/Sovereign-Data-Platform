"""Tribe-scoped access rules.

Replaces `TribeAccessHelper` from the original application. A user may read
records for any tribe they are a member of, and edit or export only where
their membership for *that* tribe allows it. Superusers can do everything.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet

from buffalo.models import Animal, Tribe, TribeMembership

type AnyUser = AbstractBaseUser | AnonymousUser


@dataclass(frozen=True)
class TribeAccess:
    user: AnyUser

    @cached_property
    def _memberships(self) -> list[TribeMembership]:
        if not self.user.is_authenticated:
            return []
        return list(TribeMembership.objects.filter(user_id=self.user.pk))

    @property
    def is_superuser(self) -> bool:
        return bool(getattr(self.user, "is_superuser", False)) and self.user.is_active

    @cached_property
    def readable_ids(self) -> frozenset[int]:
        if self.is_superuser:
            return frozenset(Tribe.objects.values_list("pk", flat=True))
        return frozenset(m.tribe_id for m in self._memberships)

    @cached_property
    def editable_ids(self) -> frozenset[int]:
        if self.is_superuser:
            return self.readable_ids
        return frozenset(m.tribe_id for m in self._memberships if m.can_edit)

    @cached_property
    def exportable_ids(self) -> frozenset[int]:
        if self.is_superuser:
            return self.readable_ids
        return frozenset(m.tribe_id for m in self._memberships if m.can_export)

    @property
    def has_any_access(self) -> bool:
        return bool(self.readable_ids)

    @property
    def can_edit_any(self) -> bool:
        return bool(self.editable_ids)

    def readable_tribes(self) -> QuerySet[Tribe]:
        return Tribe.objects.filter(pk__in=self.readable_ids)

    def editable_tribes(self) -> QuerySet[Tribe]:
        return Tribe.objects.filter(pk__in=self.editable_ids)

    def readable_animals(self) -> QuerySet[Animal]:
        return Animal.objects.filter(tribe_id__in=self.readable_ids)

    def editable_animals(self) -> QuerySet[Animal]:
        return Animal.objects.filter(tribe_id__in=self.editable_ids)

    def can_edit(self, tribe_id: int) -> bool:
        return tribe_id in self.editable_ids

    def can_export(self, tribe_id: int) -> bool:
        return tribe_id in self.exportable_ids

    def require_edit(self, tribe_id: int) -> None:
        if not self.can_edit(tribe_id):
            raise PermissionDenied("You do not have permission to edit this tribe's records.")

    def require_edit_any(self) -> None:
        if not self.can_edit_any:
            raise PermissionDenied("You do not have permission to edit records.")
