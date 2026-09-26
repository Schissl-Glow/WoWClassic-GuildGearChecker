"""Focused V2 cemetery projection, gravestone edit and persistence checks."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.identity_v2 import IdentityV2Store, IdentityV2ValidationError, Member, Player
from app.identity_v2_graveyard import (
    GravestoneUnavailableError, graveyard_entries, gravestone_visual_fields,
    repair_missing_individual_gravestones, set_member_gravestone_adjustment,
)
from app.identity_v2_character_service import mark_member_dead, set_member_burial_type
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.gravestone_templates import GravestoneTemplate


class IdentityV2GraveyardTests(unittest.TestCase):
    def setUp(self):
        self.store = IdentityV2Store(
            players=[Player("p1", "Spieler")],
            members=[
                Member("m1000", "Annî", "Mage", lifeStatus="dead",
                       burialType="individual", deathDate="2026-03-15",
                       playerId="p1"),
                Member("m1001", "Annî", "Mage", lifeStatus="dead",
                       burialType="collective", deathDate="2026-04-15"),
                Member("m1002", "Lebendig", "Priest"),
            ],
        )
        self.store.validate()
        self.templates = tuple(GravestoneTemplate(
            f"stone-{index}", f"stone-{index}.png", f"hash-{index}",
            Path(f"stone-{index}.png"), category="Menschen",
            default_portrait_offset_x=index / 10,
            default_portrait_offset_y=-index / 10,
            default_portrait_zoom=1 + index / 10,
        ) for index in range(1, 4))

    def test_new_individual_graves_reserve_distinct_existing_templates(self):
        store = IdentityV2Store(members=[
            Member("m1", "Sorap", "Mage"), Member("m2", "Sorap", "Mage")])
        before = store.to_payload()
        first = mark_member_dead(store, "m1", "2026-03-15", "individual",
                                 gravestone_templates=self.templates)
        second = mark_member_dead(first, "m2", "2026-03-15", "individual",
                                  gravestone_templates=self.templates)
        self.assertNotEqual(first.members[0].graveTemplateId,
                            second.members[1].graveTemplateId)
        self.assertEqual(store.to_payload(), before)
        by_id = {item.grave_template_id: item for item in self.templates}
        assigned = by_id[first.members[0].graveTemplateId]
        self.assertEqual((first.members[0].portraitOffsetX,
                          first.members[0].portraitOffsetY,
                          first.members[0].portraitZoom),
                         (assigned.default_portrait_offset_x,
                          assigned.default_portrait_offset_y,
                          assigned.default_portrait_zoom))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "individual.ggc"
            save_new_identity_v2(second, path)
            self.assertEqual(load_identity_v2(path).to_payload(), second.to_payload())

    def test_collective_reservations_and_living_reservations_are_occupied(self):
        store = IdentityV2Store(members=[
            Member("m1", "Collective", "Mage", lifeStatus="dead",
                   burialType="collective", deathDate="2026-03-14",
                   graveTemplateId=self.templates[0].grave_template_id),
            Member("m2", "Korrigiert", "Priest",
                   graveTemplateId=self.templates[1].grave_template_id),
            Member("m3", "Neu", "Warrior"),
        ])
        result = mark_member_dead(store, "m3", "2026-03-15", "individual",
                                  gravestone_templates=self.templates)
        self.assertEqual(result.members[2].graveTemplateId,
                         self.templates[2].grave_template_id)

    def test_no_free_stone_aborts_entire_death_or_burial_change(self):
        store = IdentityV2Store(members=[Member("m1", "Neu", "Mage")])
        before = store.to_payload()
        with self.assertRaises(GravestoneUnavailableError):
            mark_member_dead(store, "m1", "2026-03-15", "individual",
                             gravestone_templates=())
        self.assertEqual(store.to_payload(), before)
        collective = mark_member_dead(store, "m1", "2026-03-15", "collective")
        self.assertIsNone(collective.members[0].graveTemplateId)
        with self.assertRaises(GravestoneUnavailableError):
            set_member_burial_type(collective, "m1", "individual",
                                   gravestone_templates=())
        self.assertEqual(collective.members[0].burialType, "collective")

    def test_collective_to_individual_reuses_reserved_stone(self):
        assigned = set_member_burial_type(
            self.store, "m1001", "individual",
            gravestone_templates=self.templates)
        template_id = assigned.members[1].graveTemplateId
        self.assertIsNotNone(template_id)
        collective = set_member_burial_type(assigned, "m1001", "collective")
        self.assertEqual(collective.members[1].graveTemplateId, template_id)
        returned = set_member_burial_type(collective, "m1001", "individual")
        self.assertEqual(returned.members[1].graveTemplateId, template_id)

    def test_old_individual_repair_is_deterministic_and_atomic(self):
        before = self.store.to_payload()
        first = repair_missing_individual_gravestones(self.store, self.templates)
        second = repair_missing_individual_gravestones(self.store, self.templates)
        self.assertEqual(first.to_payload(), second.to_payload())
        self.assertIsNotNone(first.members[0].graveTemplateId)
        self.assertEqual(self.store.to_payload(), before)
        self.assertIs(repair_missing_individual_gravestones(first, self.templates), first)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repaired.ggc"
            save_new_identity_v2(first, path)
            self.assertEqual(load_identity_v2(path).to_payload(), first.to_payload())
        incomplete = IdentityV2Store(members=[
            Member("m1", "Alt1", "Mage", lifeStatus="dead",
                   burialType="individual", deathDate="2026-03-15"),
            Member("m2", "Alt2", "Priest", lifeStatus="dead",
                   burialType="individual", deathDate="2026-03-15"),
        ])
        original = incomplete.to_payload()
        with self.assertRaises(GravestoneUnavailableError):
            repair_missing_individual_gravestones(incomplete, self.templates[:1])
        self.assertEqual(incomplete.to_payload(), original)

    def test_projection_keeps_same_names_separate_and_excludes_living(self):
        before = self.store.to_payload()
        individual, collective = graveyard_entries(self.store)
        self.assertEqual([item.memberId for item in individual], ["m1000"])
        self.assertEqual([item.memberId for item in collective], ["m1001"])
        self.assertEqual(individual[0].playerName, "Spieler")
        self.assertEqual(individual[0].name, collective[0].name)
        self.assertEqual(self.store.to_payload(), before)

    def test_same_name_and_death_date_use_member_id_as_stable_tie_breaker(self):
        store = IdentityV2Store(members=[
            Member("m0001", "Sorap", "Mage", lifeStatus="dead",
                   burialType="individual", deathDate="2026-03-15"),
            Member("m0002", "Sorap", "Priest", lifeStatus="dead",
                   burialType="individual", deathDate="2026-03-15"),
        ])
        individual, collective = graveyard_entries(store)
        self.assertEqual([item.memberId for item in individual], ["m0002", "m0001"])
        self.assertEqual(collective, ())

    def test_old_v2_dead_without_burial_is_individual(self):
        old = self.store.to_payload()
        old["members"][0].pop("burialType")
        loaded = IdentityV2Store.from_payload(old)
        self.assertEqual(loaded.members[0].burialType, "individual")
        self.assertEqual(graveyard_entries(loaded)[0][0].memberId, "m1000")

    def test_gravestone_edit_keeps_other_data_and_roundtrips(self):
        template = SimpleNamespace(category="Menschen")
        before = self.store.to_payload()
        changed = set_member_gravestone_adjustment(
            self.store, "m1000", "grave-template-001",
            0.2, -0.3, 1.4, -0.1, 0.2, 1.1,
            {"grave-template-001": template},
        )
        self.assertEqual(changed.members[0].graveTemplateId, "grave-template-001")
        self.assertEqual(changed.members[0].deathDate, "2026-03-15")
        self.assertEqual(changed.members[1].to_dict(), self.store.members[1].to_dict())
        self.assertEqual(gravestone_visual_fields(changed.members[0])["id"], "m1000")
        self.assertEqual(self.store.to_payload(), before)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graveyard.ggc"
            save_new_identity_v2(changed, path)
            self.assertEqual(load_identity_v2(path).to_payload(), changed.to_payload())

        for member_id, template_id, category in (
                ("m1002", "grave-template-001", "Menschen"),
                ("m1000", "missing", "Menschen"),
                ("m1000", "grave-template-001", None)):
            with self.assertRaises(IdentityV2ValidationError):
                set_member_gravestone_adjustment(
                    self.store, member_id, template_id,
                    0, 0, 1, 0, 0, 1,
                    {"grave-template-001": SimpleNamespace(category=category)},
                )
        with self.assertRaises(IdentityV2ValidationError):
            set_member_gravestone_adjustment(
                self.store, "m1000", "grave-template-001",
                0, 0, 3.0, 0, 0, 1,
                {"grave-template-001": template},
            )

    def test_template_reservation_survives_collective_switch(self):
        template = SimpleNamespace(category="Menschen")
        changed = set_member_gravestone_adjustment(
            self.store, "m1000", "grave-template-001", 0, 0, 1, 0, 0, 1,
            {"grave-template-001": template},
        )
        changed.members[0].burialType = "collective"
        changed.validate()
        self.assertEqual(changed.members[0].graveTemplateId, "grave-template-001")
        with self.assertRaises(IdentityV2ValidationError):
            set_member_gravestone_adjustment(
                changed, "m1001", "grave-template-001", 0, 0, 1, 0, 0, 1,
                {"grave-template-001": template},
            )


if __name__ == "__main__":
    unittest.main()
