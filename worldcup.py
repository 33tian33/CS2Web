"""FIFA World Cup 2026 bracket (article 12 and Annexe C, May 2026)."""
import json
from pathlib import Path

RULES = json.loads((Path(__file__).parent / 'rules/worldcup2026.json').read_text())
THIRD_GROUPS = dict(A='CEFHI', B='EFGIJ', D='BEFIJ', E='ABCDF',
                    G='AEHIJ', I='CDFGH', K='DEIJL', L='EHIJK')
FIRST_ROUND = [('A2', 'B2'), ('E1', '3E'), ('F1', 'C2'), ('C1', 'F2'),
               ('I1', '3I'), ('E2', 'I2'), ('A1', '3A'), ('L1', '3L'),
               ('D1', '3D'), ('G1', '3G'), ('K2', 'L2'), ('H1', 'J2'),
               ('B1', '3B'), ('J1', 'H2'), ('K1', '3K'), ('D2', 'G2')]
ROUND_PAIRS = [[[1, 4], [0, 2], [3, 5], [6, 7], [10, 11], [8, 9], [13, 15], [12, 14]],
               [[0, 1], [4, 5], [2, 3], [6, 7]], [[0, 1], [2, 3]], [[0, 1]]]


def slots(stage_id, comparator_id):
    return [dict(kind='worldcupThird', stageId=stage_id, comparatorId=comparator_id, winnerGroup=s[1])
            if s[0] == '3' else dict(kind='rank', stageId=stage_id, group=ord(s[0])-65, rank=int(s[1]))
            for pair in FIRST_ROUND for s in pair]


def allocation(rows):
    qualifiers = {chr(65+r['group']): r['teamId'] for r in rows[:8]}
    groups = ''.join(sorted(qualifiers))
    return {winner: qualifiers[third] for winner, third in zip(RULES['columns'], RULES['allocations'][groups])}


def validate_stage(st, previous):
    source = previous.get(st.get('groupStageId'))
    c = next((c for c in source.get('comparators', []) if c['id'] == st.get('comparatorId')), None) if source else None
    if not source or source['type'] != 'group' or source['teamCount'] != 48 or source['groupCount'] != 12 or source['advance'] != 2:
        raise ValueError('世界杯赛制需要12组、每组4队、前2名直接晋级')
    if not c or c['inputs'] != [dict(group=g, rank=3) for g in range(12)] or c['outcomes'] != ['qualified']*8+['eliminated']*4:
        raise ValueError('世界杯赛制需要比较12个小组第三名，前8名晋级')
    if st['type'] != 'playoff' or st['teamCount'] != 32 or st.get('roundPairs') != ROUND_PAIRS or st['slots'] != slots(source['id'], c['id']):
        raise ValueError('世界杯淘汰赛必须保留官方32强来源与晋级路径')


def configure(plan):
    """Convert the existing four-school plan without touching group membership."""
    stages = {s['id']: s for s in plan['stages']}
    knockout = stages['knockout']
    knockout.update(bracket='worldcup2026', groupStageId='groups', comparatorId='thirds',
                    roundPairs=ROUND_PAIRS, slots=slots('groups', 'thirds'))
    stages['bronze']['slots'] = [dict(kind='loser', matchKey=f'knockout:r4:{i}') for i in range(2)]
    return plan
