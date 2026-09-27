"""Expose the latest accepted enemy choice without choosing or locking a target."""
import copy


class EnemyCommitment:
    def __init__(self):
        self.reset()

    def reset(self):
        self.target_id = None
        self.selected_tick = None

    def accept(self, directive, tick):
        target = (directive.get('target') or {}).get('id') if directive['action'] == 'attack' else None
        if target != self.target_id:
            self.target_id = target
            self.selected_tick = tick if target is not None else None

    def facts(self, tick):
        return dict(target_id=self.target_id,
                    age_seconds=round((tick-self.selected_tick)/35, 3) if self.selected_tick is not None else None)


def with_enemy_commitment(packet, facts):
    result = copy.deepcopy(packet)
    result['enemy_commitment'] = dict(facts)
    if 'enemy' not in result['questions']:
        return result
    q = result['questions']['enemy']
    target_id = facts['target_id']
    age = facts['age_seconds']
    current = str(target_id) if target_id is not None else None
    q['instructions'] += ' Consider the latest accepted attack target. Turning and firing take time; avoid changing target before completing the turn unless another enemy is an immediate threat.'
    for key, description in q['criteria'].items():
        selected = key == current
        prefix = f'Latest accepted attack target: {"yes" if selected else "no"}.'
        if selected:
            prefix += f' Selected {age:.1f}s ago.'
        q['criteria'][key] = prefix+' '+description
    return result


def recorded_facts(decisions):
    """Reconstruct only decisions accepted by the instant each request was sent."""
    accepted = sorted((d for d in decisions if d['applied']), key=lambda d: d['game_seconds'])
    history = EnemyCommitment()
    index = 0
    episode = None
    result = {}
    for row in sorted(decisions, key=lambda d: d['tick']):
        if row['episode'] != episode:
            history.reset()
            episode = row['episode']
        while index < len(accepted) and round(accepted[index]['game_seconds']*35) <= row['tick']:
            event = accepted[index]
            if event['episode'] == episode:
                history.accept(event['directive'], round(event['game_seconds']*35))
            index += 1
        result[row['directive']['decision_id']] = history.facts(row['tick'])
    return result
