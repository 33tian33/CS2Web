import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tournament

class SimulationTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/'data/tournament.sqlite3'
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as con:
            con.row_factory=sqlite3.Row
            self.plan=json.loads(con.execute('SELECT active FROM flow').fetchone()[0])
            self.cfg=json.loads(con.execute('SELECT value FROM settings').fetchone()[0])
            self.names={r['id']:r['name'] for r in con.execute('SELECT id,name FROM teams')}
            self.matches=tournament.load_matches(con)
        # Isolate from live results while retaining the real tournament structure.
        for m in self.matches:
            if m['stage']=='group':
                m['status']='scheduled';m['maps']=[]
        self.match=next(m for m in self.matches if m['stage']=='group')

    def simulate(self,entries):
        return tournament.simulate(self.plan,self.matches,self.cfg,self.names,entries)

    def entry(self,a=2,b=0,rd=20):
        return dict(id=self.match['id'],scoreA=a,scoreB=b,roundDiff=rd)

    def row(self,result,tid):
        return next(r for g in result['tables'] for r in g['rows'] if r['teamId']==tid)

    def test_score_diff_and_head_to_head_share_official_ranking(self):
        result=self.simulate([self.entry()])
        a=self.row(result,self.match['team_a']);b=self.row(result,self.match['team_b'])
        self.assertEqual((a['w'],a['mw'],a['rd'],a['pts']),(1,2,20,self.cfg['winPoints']))
        self.assertEqual((b['l'],b['ml'],b['rd']),(1,2,-20))
        official=copy.deepcopy(self.matches)
        match=next(m for m in official if m['id']==self.match['id'])
        match.update(status='finished',maps=[dict(scoreA=13,scoreB=3)]*2)
        expected=tournament.simulate(self.plan,official,self.cfg,self.names,[])
        self.assertEqual(result,expected)

    def test_round_diff_updates_table_and_draw_allows_negative_diff(self):
        result=self.simulate([self.entry(1,1,-5)])
        a=self.row(result,self.match['team_a'])
        self.assertEqual((a['d'],a['rd'],a['pts']),(1,-5,self.cfg['drawPoints']))
        changed=self.simulate([self.entry(1,1,8)])
        self.assertEqual(self.row(changed,self.match['team_a'])['rd'],8)

    def test_results_change_bracket_and_reset_without_mutation(self):
        before=copy.deepcopy((self.matches,self.plan))
        base=self.simulate([])
        first=self.simulate([self.entry()])
        second=self.simulate([self.entry(0,2,-20)])
        self.assertNotEqual(first['projections'],second['projections'])
        self.assertEqual(self.simulate([]),base)
        self.assertEqual((self.matches,self.plan),before)

    def test_third_place_comparison_tracks_updated_group_rows(self):
        entries=[dict(id=m['id'],scoreA=1,scoreB=1,roundDiff=(m['id']%5)-2) for m in self.matches if m['stage']=='group']
        result=self.simulate(entries)
        for comparison in result['comparisons']:
            for row in comparison['rows']:
                group=next(g for g in result['tables'] if g['stageId']==comparison['stageId'] and g['group']==row['group'])
                self.assertEqual(row['teamId'],group['rows'][2]['teamId'])
                self.assertEqual(row['rd'],group['rows'][2]['rd'])
        self.assertEqual(len(result['projections'][0]['matches']),16)

    def test_all_simulated_results_complete_groups_and_match_official_results(self):
        entries=[];official=copy.deepcopy(self.matches)
        for m in official:
            if m['stage']!='group':continue
            a_wins=m['team_a']<m['team_b']
            entries.append(dict(id=m['id'],scoreA=2 if a_wins else 0,scoreB=0 if a_wins else 2,roundDiff=20 if a_wins else -20))
            m.update(status='finished',maps=[dict(scoreA=13 if a_wins else 3,scoreB=3 if a_wins else 13)]*2)
        result=self.simulate(entries)
        self.assertTrue(all(g['complete'] for g in result['tables']))
        for group in result['tables']:
            self.assertEqual([r['qualification'] for r in group['rows'][:2]],['qualified','qualified'])
            self.assertEqual(group['rows'][3]['qualification'],'eliminated')
        for comparison in result['comparisons']:
            self.assertTrue(all(r['qualification']=='qualified' for r in comparison['rows'][:8]))
            self.assertTrue(all(r['qualification']=='eliminated' for r in comparison['rows'][8:]))
        self.assertTrue(any(g['rows'][2]['qualification']=='third' for g in result['tables']))
        self.assertTrue(all(c['complete'] for c in result['comparisons']))
        self.assertEqual(result,tournament.simulate(self.plan,official,self.cfg,self.names,[]))
        for comparison in result['comparisons']:
            for row in comparison['rows'][:8]:
                self.assertIn('worldcupOpponent',row)
                seed=row['worldcupOpponent']+'1'
                match=next(m for p in result['projections'] for m in p['matches'] if m['seed_a']==seed)
                self.assertEqual(match['team_b'],row['teamId'])
        partial=self.simulate(entries[:-1])
        self.assertTrue(any(not g['complete'] for g in partial['tables']))

    def test_revision_changes_with_results_rules_and_roster_but_not_match_order(self):
        revision=lambda matches,cfg=None:tournament.simulation_revision(self.plan,matches,cfg or self.cfg,self.names)
        before=revision(self.matches)
        self.assertEqual(before,revision(list(reversed(self.matches))))
        changed=copy.deepcopy(self.matches)
        changed[0]['maps']=[dict(scoreA=13,scoreB=7)]
        self.assertNotEqual(before,revision(changed))
        changed=copy.deepcopy(self.matches);changed[0]['status']='finished'
        self.assertNotEqual(before,revision(changed))
        changed=copy.deepcopy(self.matches);changed[0]['team_a']=999
        self.assertNotEqual(before,revision(changed))
        self.assertNotEqual(before,revision(self.matches,dict(self.cfg,winPoints=9)))

    def test_finished_match_requires_unlock_and_restores_original(self):
        self.match.update(status='finished',maps=[dict(scoreA=13,scoreB=5)]*2)
        before=copy.deepcopy(self.matches)
        original=self.simulate([])
        with self.assertRaisesRegex(ValueError,'解锁'):
            self.simulate([self.entry(0,2,-18)])
        unlocked=self.simulate([dict(self.entry(0,2,-18),unlocked=True)])
        self.assertEqual(self.row(unlocked,self.match['team_a'])['rd'],-18)
        self.assertEqual(self.row(unlocked,self.match['team_a'])['l'],1)
        self.assertEqual(self.simulate([]),original)
        self.assertEqual(self.matches,before)

    def test_rejects_finished_partial_non_group_and_invalid_scores(self):
        for entry in [self.entry(3,0),self.entry(2,0,-1),self.entry(1,1,20),dict(self.entry(),roundDiff=1.2),dict(self.entry(),id=999999)]:
            with self.subTest(entry=entry),self.assertRaises(ValueError):self.simulate([entry])
        for change in [dict(status='finished'),dict(maps=[dict(scoreA=13,scoreB=8)])]:
            old=copy.deepcopy(self.match);self.match.update(change)
            with self.assertRaises(ValueError):self.simulate([self.entry()])
            self.match.clear();self.match.update(old)
        playoff=next(m for m in self.matches if m['stage']!='group')
        with self.assertRaises(ValueError):self.simulate([dict(self.entry(),id=playoff['id'])])

if __name__=='__main__':unittest.main()
