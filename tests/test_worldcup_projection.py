import copy
import itertools
import json
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tournament
import worldcup


class WorldCupProjectionTests(unittest.TestCase):
    def setUp(self):
        self.stage = dict(id='cup', groupStageId='groups', comparatorId='thirds',
                          slots=worldcup.slots('groups', 'thirds'))
        self.tables = {('groups', g): dict(complete=False, rows=[
            dict(teamId=g*4+r, tied=True) for r in range(1, 5)]) for g in range(12)}

    def comparison(self, groups):
        ordered = list(groups) + [g for g in range(12) if g not in groups]
        return {('groups', 'thirds'): dict(complete=False, rows=[
            dict(group=g, teamId=g*4+3) for g in ordered])}

    def test_all_495_combinations_have_32_unique_teams_and_legal_third_routes(self):
        for groups in itertools.combinations(range(12), 8):
            with self.subTest(groups=groups):
                result = worldcup.projection(self.stage, self.tables, self.comparison(groups))
                matches = result['matches']
                ids = [m['team_'+side] for m in matches for side in ('a', 'b')]
                expected = {g*4+r for g in range(12) for r in (1, 2)} | {g*4+3 for g in groups}
                self.assertEqual(len(ids), 32)
                self.assertEqual(set(ids), expected)
                self.assertEqual((matches[0]['seed_a'], matches[0]['seed_b']), ('A2', 'B2'))
                for match in matches:
                    if match['seed_b'].endswith('3'):
                        self.assertIn(match['seed_b'][0], worldcup.THIRD_GROUPS[match['seed_a'][0]])

    def test_third_ranking_order_does_not_change_fifa_allocation(self):
        first = worldcup.projection(self.stage, self.tables, self.comparison(list(range(8))))
        second = worldcup.projection(self.stage, self.tables, self.comparison(list(reversed(range(8)))))
        self.assertEqual(first, second)
        self.assertEqual(first['matches'][1]['seed_b'], 'C3')
        self.assertEqual(first['matches'][6]['seed_b'], 'H3')

    def test_projection_tracks_standings_without_mutating_them(self):
        comparison = self.comparison(list(range(8)))
        before = copy.deepcopy((self.tables, comparison))
        first = worldcup.projection(self.stage, self.tables, comparison)
        self.assertEqual((self.tables, comparison), before)
        self.tables['groups', 0]['rows'][:2] = reversed(self.tables['groups', 0]['rows'][:2])
        second = worldcup.projection(self.stage, self.tables, comparison)
        self.assertNotEqual(first['matches'][0]['team_a'], second['matches'][0]['team_a'])

    def test_missing_roster_does_not_produce_a_partial_bracket(self):
        self.tables['groups', 0]['rows'].pop()
        self.assertIsNone(worldcup.projection(self.stage, self.tables, self.comparison(list(range(8)))))

    def test_real_event_state_does_not_assign_official_matches_or_write_database(self):
        path = Path(__file__).resolve().parents[1] / 'data/tournament.sqlite3'
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as con:
            con.row_factory = sqlite3.Row
            matches = tournament.load_matches(con)
            before = copy.deepcopy(matches)
            cfg = json.loads(con.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
            result = tournament.state(con, matches, cfg)
            self.assertEqual(matches, before)
            self.assertEqual(tournament.load_matches(con), before)
            self.assertEqual(con.total_changes, 0)
            self.assertEqual(len(result['projections'][0]['matches']), 16)


if __name__ == '__main__':
    unittest.main()
