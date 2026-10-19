from functools import lru_cache
from itertools import product, permutations
from math import gcd


def integer_solutions(constraints, size):
    normalized = {}
    for coefficients, minimum in constraints:
        divisor = 0
        for value in coefficients:
            divisor = gcd(divisor, value)
        if not divisor:
            if minimum > 0:
                return
            continue
        coefficients = tuple(v // divisor for v in coefficients)
        minimum = -(-minimum // divisor)
        normalized[coefficients] = max(minimum, normalized.get(coefficients, minimum))
    constraints = tuple(normalized.items())
    if not size:
        yield ()
        return
    index = min(range(size), key=lambda i: sum(c[i] > 0 for c, _ in constraints) * sum(c[i] < 0 for c, _ in constraints))
    positive = [(c, b) for c, b in constraints if c[index] > 0]
    negative = [(c, b) for c, b in constraints if c[index] < 0]
    reduced = [(c[:index] + c[index+1:], b) for c, b in constraints if not c[index]]
    for p, pb in positive:
        for n, nb in negative:
            c = tuple(p[index]*nv - n[index]*pv for pv, nv in zip(p, n))
            reduced.append((c[:index] + c[index+1:], p[index]*nb - n[index]*pb))
    for rest in integer_solutions(reduced, size-1):
        values = rest[:index] + (0,) + rest[index:]
        low = max(-(-(b-sum(a*v for a, v in zip(c, values))) // c[index]) for c, b in positive)
        high = min((b-sum(a*v for a, v in zip(c, values))) // c[index] for c, b in negative)
        for value in range(low, high+1):
            yield rest[:index] + (value,) + rest[index:]


def feasible(constraints, bounds):
    needed = []
    for c, minimum in constraints:
        low = sum(v*(a if v >= 0 else b) for v, (a, b) in zip(c, bounds))
        high = sum(v*(b if v >= 0 else a) for v, (a, b) in zip(c, bounds))
        if high < minimum:
            return False
        if low < minimum:
            needed.append((c, minimum))
    if not needed:
        return True
    for i, (low, high) in enumerate(bounds):
        unit = tuple(int(j == i) for j in range(len(bounds)))
        needed.extend(((unit, low), (tuple(-v for v in unit), -high)))
    return next(integer_solutions(needed, len(bounds)), None) is not None


def possible_orders(rows, matches, outcomes, order):
    variables = [(a, b, low, high) for (a, b, *_), (_, _, low, high) in zip(matches, outcomes) if low != high]
    bounds = tuple((low, high) for _, _, low, high in variables)
    coefficients = {tid: tuple(int(tid == a)-int(tid == b) for a, b, _, _ in variables) for tid in rows}
    fixed = {tid: row['rdMin']-sum(v*(lo if v > 0 else hi) for v, (lo, hi) in zip(coefficients[tid], bounds))
             for tid, row in rows.items()}
    before, after = order[:order.index('round')], order[order.index('round')+1:]
    prefix = {tid: (r['pts'], *(r[k] for k in before)) for tid, r in rows.items()}
    suffix = {tid: tuple(r[k] for k in after) for tid, r in rows.items()}
    orders = []
    for ranked in permutations(rows):
        constraints = []
        for a, b in zip(ranked, ranked[1:]):
            if prefix[a] < prefix[b]:
                break
            if prefix[a] == prefix[b]:
                constraints.append((tuple(x-y for x, y in zip(coefficients[a], coefficients[b])),
                                    int(suffix[a] < suffix[b])-fixed[a]+fixed[b]))
        else:
            if feasible(constraints, bounds):
                orders.append(ranked)
    return tuple(orders)


def match_outcomes(bo, status, maps):
    a = sum(x > y for x, y in maps)
    b = len(maps) - a
    rd = sum(x - y for x, y in maps)
    if status == 'finished':
        return ((a, b, rd, rd),)
    scores = set()

    def finish(x, y):
        if (bo == 2 and x + y == 2) or (bo != 2 and max(x, y) == bo // 2 + 1):
            scores.add((x, y))
            return
        finish(x + 1, y)
        finish(x, y + 1)

    finish(a, b)
    return tuple((x, y, rd + (x - a) - 100 * (y - b), rd + 100 * (x - a) - (y - b))
                 for x, y in sorted(scores))


@lru_cache(maxsize=128)
def scenarios(ids, matches, points, order):
    choices = [(result,) if result is not None else match_outcomes(bo, status, maps)
               for _, _, bo, status, maps, result in matches]
    results = []
    for outcomes in product(*choices):
        rows = {tid: dict(teamId=tid, pts=0, map=0, rdMin=0, rdMax=0, h2h=0) for tid in ids}
        games = []
        for (a, b, *_), (x, y, low, high) in zip(matches, outcomes):
            pa, pb = (points[0], points[2]) if x > y else (points[2], points[0]) if x < y else (points[1], points[1])
            for tid, pts, md, lo, hi in ((a, pa, x-y, low, high), (b, pb, y-x, -high, -low)):
                r = rows[tid]
                r['pts'] += pts
                r['map'] += md
                r['rdMin'] += lo
                r['rdMax'] += hi
            games.append((a, b, pa, pb))
        for a, b, pa, pb in games:
            if rows[a]['pts'] == rows[b]['pts']:
                rows[a]['h2h'] += pa
                rows[b]['h2h'] += pb
        orders = possible_orders(rows, matches, outcomes, order)
        for tid, row in rows.items():
            row['orders'] = orders
            row['ranks'] = tuple(sorted({ranked.index(tid)+1 for ranked in orders}))
            row['bestRank'] = min(row['ranks'])
            row['worstRank'] = max(row['ranks'])
        results.append(rows)
    return results


def group_scenarios(ids, matches, cfg, results=None):
    results = results or {}
    def simulated(m):
        result = results.get(m.get('id'))
        return (result['scoreA'],result['scoreB'],result['roundDiff'],result['roundDiff']) if result else None
    signature = tuple((m['team_a'], m['team_b'], m['bo'], m['status'],
                       tuple((v['scoreA'], v['scoreB']) for v in m['maps']),simulated(m)) for m in matches)
    return scenarios(tuple(ids), signature, tuple(cfg[k] for k in ('winPoints', 'drawPoints', 'lossPoints')),
                     tuple(cfg['tieBreak'].split(',')))


def comparison_key(row, names, bound):
    return (-row['pts'], -row['map'], -row[bound], names[row['teamId']], row['teamId'])


def annotate(st, tables, comparisons, possibilities, names, plan):
    routes = {}
    limits = {}
    outcomes = {}
    for c in st.get('comparators', []):
        outcomes[c['id']] = [outcome == 'qualified' or any(
            src.get('kind') == 'comparison' and src['stageId'] == st['id'] and src['comparatorId'] == c['id'] and src['rank'] == i+1
            for stage in plan['stages'] for src in stage['slots']) for i, outcome in enumerate(c['outcomes'])]
        for i, src in enumerate(c['inputs']):
            if src is None:
                continue
            g, rank = src['group'], src['rank']
            routes[g, rank] = (c, i)
            if g in possibilities:
                candidates = [r for s in possibilities[g] for r in s.values() if rank in r['ranks']]
                limits[c['id'], i] = (min(comparison_key(r, names, 'rdMax') for r in candidates),
                                      max(comparison_key(r, names, 'rdMin') for r in candidates))
    statuses = {}
    for g, options in possibilities.items():
        for row in tables[st['id'], g]['rows']:
            tid = row['teamId']
            worst = max(s[tid]['worstRank'] for s in options)
            certain, possible = True, False
            for scenario in options:
                r = scenario[tid]
                for rank in r['ranks']:
                    route = routes.get((g, rank))
                    if route is None:
                        wins = (rank <= st['advance'],)
                    else:
                        c, source_index = route
                        best_rank, worst_rank = 1, 1
                        for i, src in enumerate(c['inputs']):
                            if i == source_index:
                                continue
                            if src is None or (c['id'], i) not in limits:
                                worst_rank += 1
                                continue
                            if src['group'] == g:
                                candidates = {ranked[src['rank']-1] for ranked in r['orders'] if ranked[rank-1] == tid}
                                best_key = min(comparison_key(scenario[t], names, 'rdMax') for t in candidates)
                                worst_key = max(comparison_key(scenario[t], names, 'rdMin') for t in candidates)
                            else:
                                best_key, worst_key = limits[c['id'], i]
                            best_rank += worst_key < comparison_key(r, names, 'rdMax')
                            worst_rank += best_key < comparison_key(r, names, 'rdMin')
                        wins = outcomes[c['id']][best_rank-1:worst_rank]
                    certain &= all(wins)
                    possible |= any(wins)
            row['qualification'] = 'eliminated' if not possible else 'qualified' if certain and worst <= st['advance'] else 'third' if worst <= st['advance']+1 else 'pending'
            statuses[tid] = 'qualified' if certain else 'eliminated' if not possible else row['qualification']
    for c in st.get('comparators', []):
        for row in comparisons[st['id'], c['id']]['rows']:
            if row['teamId'] in statuses:
                row['qualification'] = statuses[row['teamId']]
