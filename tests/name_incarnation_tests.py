# -*- coding: utf-8 -*-
"""Regression tests for Hardcore character incarnations, without starting a GUI.

Run TESTEN_NAMENSINKARNATIONEN.bat. Fixtures are synthetic; every file write
is confined to a TemporaryDirectory. CSV tests call the real UI import method,
replacing only dialogs, display callbacks, and the autosave destination.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


g = None


def member_record(member_id, status, name="Janos"):
    """Complete, distinct historical records make accidental merging visible."""
    return dict(
        id=member_id, name=name, className="Warrior", spec="Fury",
        classSpec="Warrior / Fury", lifeStatus=status,
        gearStatus="BiS", note=f"Notiz {member_id}: Bífi / Tazgø",
        lastChecked="2026-08-20", deathDate="2026-08-21" if status == "dead" else "",
        addedDate="2026-08-01", source=f"Legacy-Projekt {member_id}",
    )


def member_bytes(model, member_id):
    """Compare stable record bytes, excluding project-level savedAt metadata."""
    matches = [row for row in model.to_payload()["members"] if row["id"] == member_id]
    if len(matches) != 1:
        raise AssertionError(f"Member-ID {member_id}: {len(matches)} Datensaetze")
    return json.dumps(matches[0], ensure_ascii=False, sort_keys=True).encode("utf-8")


class IncarnationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-incarnations-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dead = member_record("m0042", "dead")
        self.dead2 = member_record("m0087", "dead")
        self.dead2.update(className="Mage", spec="Frost", classSpec="Mage / Frost",
                          gearStatus="Pre-BiS", deathDate="2026-08-30")
        self.active = member_record("m0113", "active")

    def fixture_model(self, records):
        # Deliberately bypass loading: CSV tests must not lose their history in
        # a broken loader before reaching the actual import operation.
        model = g.GuildModel()
        model.members = [g.Member(**copy.deepcopy(row)) for row in records]
        model.next_id = 1000
        return model

    def assert_records(self, model, expected):
        rows = model.to_payload()["members"]
        self.assertEqual(len(rows), len(expected), "Keine Inkarnation darf verschwinden")
        self.assertEqual(len({row["id"] for row in rows}), len(rows), "IDs muessen eindeutig sein")
        comparable = []
        for row in rows:
            if row.get("lifeStatus") == "dead" and row.get("gravestoneTemplate"):
                self.assertTrue(g.valid_gravestone_template_id(row.get("gravestoneTemplate")))
            item = dict(row)
            item.pop("gravestoneTemplate", None)
            comparable.append(item)
        canonical_expected = []
        for row in expected:
            item = g.Member.from_dict(copy.deepcopy(row), row["id"]).to_dict()
            item.setdefault("raidStatus", "")
            item.pop("gravestoneTemplate", None)
            canonical_expected.append(item)
        self.assertEqual(
            {row["id"]: row for row in comparable},
            {row["id"]: row for row in canonical_expected},
        )

    def assert_load_preserves(self, records):
        # Ordering must never decide which historical record survives.
        for ordering in itertools.permutations(records):
            with self.subTest(ids=[row["id"] for row in ordering]):
                model = g.GuildModel()
                model.load_payload({"members": copy.deepcopy(list(ordering)),
                                    "region": "EU", "realm": "stitches"})
                self.assert_records(model, records)
                for row in records:
                    self.assertEqual(model.find_by_id(row["id"]).name, row["name"])

    def import_csv(self, model, names):
        csv_path = self.root / "raid.csv"
        csv_path.write_text("Name;Amount\n" + "".join(f"{name};1\n" for name in names),
                            encoding="utf-8-sig")
        autosave_path = self.root / "autosave.json"

        def autosave():
            autosave_path.write_text(json.dumps(model.to_payload(), ensure_ascii=False),
                                     encoding="utf-8")

        view = SimpleNamespace(model=model, autosave=autosave, current_tab="Friedhof",
                               _update_tab_styles=Mock(), refresh_all=Mock(),
                               status_var=SimpleNamespace(set=Mock()))
        with patch.object(g.filedialog, "askopenfilename", return_value=str(csv_path)), \
             patch.object(g.messagebox, "askyesno", return_value=True), \
             patch.object(g.messagebox, "showinfo"), \
             patch.object(g.messagebox, "showerror") as error:
            g.GuildGearCheckerApp.import_csv(view)
            self.assertFalse(error.called, f"CSV-Importfehler: {error.call_args}")

    def test_load_dead_and_active_janos(self):
        self.assert_load_preserves([self.dead, self.active])

    def test_load_two_dead_janos(self):
        self.assert_load_preserves([self.dead, self.dead2])

    def test_load_two_dead_and_active_janos(self):
        self.assert_load_preserves([self.dead, self.dead2, self.active])

    def test_import_only_dead_janos_creates_new_active(self):
        model = self.fixture_model([self.dead])
        before = member_bytes(model, self.dead["id"])
        self.import_csv(model, ["Janos"])
        self.assertEqual(member_bytes(model, self.dead["id"]), before)
        active = [m for m in model.members if m.lifeStatus == "active"]
        self.assertEqual(len(active), 1, "Toter Janos blockiert keine neue Inkarnation")
        self.assertEqual(active[0].name, "Janos")
        self.assertNotEqual(active[0].id, self.dead["id"])

    def test_import_two_dead_janos_creates_one_new_active(self):
        model = self.fixture_model([self.dead, self.dead2])
        before = {m.id: member_bytes(model, m.id) for m in model.members}
        self.import_csv(model, ["Janos", "JANOS", "Janos"])
        for member_id, data in before.items():
            self.assertEqual(member_bytes(model, member_id), data)
        active = [m for m in model.members if m.lifeStatus == "active"]
        self.assertEqual(len(active), 1)
        self.assertNotIn(active[0].id, before)
        self.assertEqual(len({m.id for m in model.members}), len(model.members))

    def test_import_existing_active_janos_reuses_id_and_data(self):
        for ordering in itertools.permutations([self.dead, self.dead2, self.active]):
            with self.subTest(ids=[row["id"] for row in ordering]):
                model = self.fixture_model(ordering)
                before = {m.id: member_bytes(model, m.id) for m in model.members}
                self.import_csv(model, ["JANOS", "Janos"])
                self.assertEqual({m.id: member_bytes(model, m.id) for m in model.members}, before)
                self.assertEqual([m.id for m in model.members if m.lifeStatus == "active"], ["m0113"])

    def test_import_unknown_name_creates_active_and_is_idempotent(self):
        model = self.fixture_model([])
        self.import_csv(model, ["Janos", "JANOS"])
        self.assertEqual(len(model.members), 1)
        self.assertEqual(model.members[0].lifeStatus, "active")
        before = member_bytes(model, model.members[0].id)
        self.import_csv(model, ["janos"])
        self.assertEqual(len(model.members), 1)
        self.assertEqual(member_bytes(model, model.members[0].id), before)

    def test_save_load_preserves_all_incarnations_and_backup(self):
        records = [self.dead, self.dead2, self.active]
        model = self.fixture_model(records)
        path = self.root / "historie.ggc"
        model.save(path)
        first_bytes = path.read_bytes()
        loaded = g.GuildModel()
        loaded.load(path)
        self.assert_records(loaded, records)
        loaded.save(path)
        self.assertEqual((self.root / "backups" / "historie_backup.ggc").read_bytes(), first_bytes)
        reloaded = g.GuildModel()
        reloaded.load(path)
        self.assert_records(reloaded, records)

    def test_import_does_not_modify_graveyard_data_project_or_portrait_bytes(self):
        model = self.fixture_model([self.dead, self.dead2, self.active])
        project = self.root / "historie.ggc"
        model.save(project)
        project_before = project.read_bytes()
        portrait_dir = self.root / "portraits"
        portrait_dir.mkdir()
        portraits = [portrait_dir / "m0042.png", portrait_dir / "m0087.png"]
        for index, portrait in enumerate(portraits):
            g.Image.new("RGB", (10, 20), (20, 60 + index, 90)).save(portrait)
        portrait_before = {portrait: portrait.read_bytes() for portrait in portraits}
        before = {row["id"]: member_bytes(model, row["id"]) for row in (self.dead, self.dead2)}
        with patch.object(g, "shared_portrait_folder", return_value=self.root / "shared"):
            view = SimpleNamespace(model=model)
            def portrait_links():
                return {member_id: tuple(str(p) for p in
                        g.GuildGearCheckerApp.portrait_candidates(view, model.find_by_id(member_id))
                        if p.is_file()) for member_id in before}
            links_before = portrait_links()
            self.assertTrue(all(links_before.values()), "Fixture muss einen Portraitbezug besitzen")
            self.import_csv(model, ["Janos", "Neuefigur"])
            self.assertEqual(portrait_links(), links_before)
        self.assertIsNotNone(model.find_by_name("Neuefigur"), "Import muss wirklich Daten hinzufuegen")
        for member_id, data in before.items():
            self.assertEqual(member_bytes(model, member_id), data)
        self.assertEqual(project.read_bytes(), project_before)
        self.assertEqual(
            {portrait: portrait.read_bytes() for portrait in portraits}, portrait_before,
        )

    def test_two_active_same_name_same_context_are_a_load_conflict(self):
        second = member_record("m0114", "active", "JANOS")
        model = self.fixture_model([member_record("m0001", "active", "Bestand")])
        before = copy.deepcopy(model.to_payload()["members"])
        with self.assertRaises(ValueError, msg="Aktiv-Duplikate nicht still deduplizieren"):
            model.load_payload({"region": "EU", "realm": "stitches",
                                "members": [self.active, second]})
        self.assertEqual(model.to_payload()["members"], before)

    def test_duplicate_member_ids_are_a_load_conflict(self):
        second = member_record(self.dead["id"], "dead", "Anderefigur")
        with self.assertRaises(ValueError, msg="Historische Datensaetze brauchen eindeutige IDs"):
            g.GuildModel().load_payload({"members": [self.dead, second]})

    def test_new_id_never_collides_when_legacy_next_id_is_missing(self):
        for counter in ({}, {"nextId": 1}):
            with self.subTest(counter=counter):
                model = g.GuildModel()
                model.load_payload({"members": [member_record("m1001", "dead")], **counter})
                self.import_csv(model, ["Neuefigur"])
                ids = [m.id for m in model.members]
                self.assertEqual(len(ids), 2)
                self.assertEqual(len(set(ids)), 2, "Neue Member-ID kollidiert mit historischem Mitglied")

    def test_similar_unicode_names_are_not_merged(self):
        names = ["Bífi", "Bifibifi", "Soregdrei", "Soregzwei"]
        model = self.fixture_model([])
        self.import_csv(model, names)
        self.assertEqual([m.name for m in model.members], names)
        self.assertEqual(len({m.id for m in model.members}), len(names))


def main():
    global g
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    os.environ["GGC_DISABLE_ICON_DOWNLOAD"] = "1"
    module_path = args.repo_root.resolve() / "app" / "GuildGearChecker.py"
    spec = importlib.util.spec_from_file_location("ggc_incarnation_target", module_path)
    g = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = g
    spec.loader.exec_module(g)
    print(f"Python {sys.version.split()[0]} | Ziel: {module_path}", flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IncarnationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
