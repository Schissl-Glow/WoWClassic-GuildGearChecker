"""Gezielte Tests für den read-only CLM-Integrationskern."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.clm_detection import select_database, select_dkp_roster, validate_guild_realm
from app.clm_matching import character_key, match_characters, strip_realm_suffix
from app.clm_models import (
    ClmCharacterBalance, ClmDatabaseDescriptor, ClmIntegrationError, ClmRosterDescriptor,
)
from app.clm_replay import ClmLedgerReplayer, LedgerReplayRequest
from app.clm_refresh import ClmDkpRefreshService
from app.clm_savedvariables import (
    SavedVariablesParseError, load_saved_variables, parse_saved_variable,
)


class ClmBackendTests(unittest.TestCase):
    def test_saved_variables_parser_reads_data_without_executing_lua(self):
        parsed = parse_saved_variable('''
            -- SavedVariables fixture containing data literals only
            CLM2_DB = {
                ["exp0 alliance stitches bierstube"] = {
                    rosterId = 1730228604,
                    names = { "Waltørdin-Stitches", "Bierstubär-Stitches" },
                    active = true,
                },
            }
        ''')
        database = parsed["exp0 alliance stitches bierstube"]
        self.assertEqual(database["rosterId"], 1730228604)
        self.assertEqual(database["names"][1], "Waltørdin-Stitches")
        with self.assertRaises(SavedVariablesParseError):
            parse_saved_variable('CLM2_DB = os.execute("unsafe")')

    def test_guild_and_realm_must_match_exactly_ignoring_case(self):
        database = ClmDatabaseDescriptor("db1", "Bierstube", "Stitches")
        self.assertIs(validate_guild_realm("bIERSTUBE", "stitches", database), database)
        with self.assertRaises(ClmIntegrationError):
            validate_guild_realm("Andere Gilde", "Stitches", database)
        with self.assertRaises(ClmIntegrationError):
            validate_guild_realm("Bierstube", "Firemaw", database)
        self.assertEqual(
            select_database([database], "Bierstube", "Stitches").database_id, "db1",
        )

    def test_roster_selection_uses_stable_id_and_only_active_non_test_dkp(self):
        rosters = [
            ClmRosterDescriptor("old", "Historisch", "db1", 0, False),
            ClmRosterDescriptor("test", "ZTest", "db1", 0, True, is_test=True),
            ClmRosterDescriptor("epgp", "EPGP", "db1", 1, True),
            ClmRosterDescriptor("1730228604", "Bierstube", "db1", 0, True),
        ]
        selected = select_dkp_roster(rosters, database_id="db1")
        self.assertEqual(selected.roster_id, "1730228604")
        self.assertIs(
            select_dkp_roster(
                rosters, database_id="db1", requested_roster_id="1730228604",
            ),
            selected,
        )
        with self.assertRaises(ClmIntegrationError):
            select_dkp_roster(rosters, database_id="db1", requested_roster_id="old")

    def test_unicode_matching_preserves_accents_and_rejects_unknown_or_ambiguous(self):
        members = [
            SimpleNamespace(id="m1", name="Waltørdin"),
            SimpleNamespace(id="m2", name="Bífi"),
            SimpleNamespace(id="m3", name="bífi"),
        ]
        balances = [
            ClmCharacterBalance("WALTØRDIN-Stitches", 629),
            ClmCharacterBalance("Waltordin-Stitches", 999),
            ClmCharacterBalance("BÍFI-Stitches", 100),
        ]
        result = match_characters(balances, members)
        self.assertEqual([(match.member_id, match.points) for match in result.matches],
                         [("m1", 629)])
        self.assertEqual(result.unknown_names, ("Waltordin-Stitches",))
        self.assertEqual(result.ambiguous_names, ("BÍFI-Stitches",))
        self.assertEqual(strip_realm_suffix("Bierstubär-Stitches"), "Bierstubär")
        self.assertNotEqual(character_key("Bífi"), character_key("Bifi"))

    def test_ledger_replay_matches_verified_minimal_fixture(self):
        fixture = REPO_ROOT / "tests" / "fixtures" / "clm_replay_verified.lua"
        document = load_saved_variables(fixture)
        database_id = "exp0 alliance stitches bierstube"
        result = ClmLedgerReplayer().replay(LedgerReplayRequest(
            database_id, "1730228604", document.data[database_id]["ledger"],
        ))
        balances = {
            strip_realm_suffix(balance.name): balance.points
            for balance in result.balances
        }
        self.assertEqual(result.roster_name, "Bierstube")
        self.assertEqual(result.point_type, 0)
        self.assertTrue(result.active)
        self.assertEqual(len(result.balances), 5)
        self.assertEqual(result.ignored_entries, 1)
        self.assertEqual(balances, {
            "Waltørdin": 629,
            "Schneeflocke": 854,
            "Mourdogg": 374,
            "Dirksson": 1265,
            "Bierstubär": 242,
        })

    def test_explicit_refresh_keeps_previous_cache_after_failure(self):
        fixture = REPO_ROOT / "tests" / "fixtures" / "clm_replay_verified.lua"
        now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        service = ClmDkpRefreshService(clock=lambda: now)

        self.assertIsNone(service.cached_snapshot)
        snapshot = service.refresh(
            fixture,
            database_id="exp0 alliance stitches bierstube",
            roster_id="1730228604",
        )
        self.assertIs(service.cached_snapshot, snapshot)
        self.assertEqual(snapshot.refreshed_at, now)
        self.assertEqual(snapshot.source_modified_at, fixture.stat().st_mtime)

        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.lua"
            with self.assertRaises(FileNotFoundError):
                service.refresh(
                    missing,
                    database_id="exp0 alliance stitches bierstube",
                    roster_id="1730228604",
                )
        self.assertIs(service.cached_snapshot, snapshot)
        self.assertIsNotNone(service.state.last_error)

    def test_project_refresh_validates_identity_and_selects_single_dkp_roster(self):
        fixture = REPO_ROOT / "tests" / "fixtures" / "clm_replay_verified.lua"
        service = ClmDkpRefreshService()
        snapshot = service.refresh_for_project(
            fixture,
            project_guild_name="BIERSTUBE",
            project_realm="stitches",
        )
        self.assertEqual(snapshot.database_id, "exp0 alliance stitches bierstube")
        self.assertEqual(snapshot.guild_name, "bierstube")
        self.assertEqual(snapshot.realm, "stitches")
        self.assertEqual(snapshot.roster_id, "1730228604")
        with self.assertRaises(ClmIntegrationError):
            service.refresh_for_project(
                fixture,
                project_guild_name="Andere Gilde",
                project_realm="stitches",
            )
        self.assertIs(service.cached_snapshot, snapshot)


if __name__ == "__main__":
    unittest.main()
