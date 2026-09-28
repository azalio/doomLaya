"""Listwise loss for a neural ranker over known targets and sequence termination."""

def validate_ranking(row):
    from doomlib.enemy_ranking import STOP
    order=row['target_ranking'];keys=list(row['question']['criteria'])
    if not 2<=len(order)<=len(keys) or order[-1]!=STOP or len(set(order))!=len(order) or not set(order)<=set(keys) or row['label']!=order[0]:raise ValueError('Invalid target ranking')


def ranking_loss(logits,rows):
    import torch
    from doomlib.enemy_ranking import STOP
    losses=[]
    for scores,row in zip(logits,rows):
        keys=list(row['question']['criteria']);remaining=list(range(len(keys)));loss=scores.sum()*0
        validate_ranking(row)
        for step,key in enumerate(row['target_ranking']):
            selected=keys.index(key);available=[i for i in remaining if step or keys[i]!=STOP]
            loss=loss+torch.logsumexp(scores[available],dim=0)-scores[selected]
            remaining.remove(selected)
        losses.append(loss)
    return torch.stack(losses).mean()


def ranking_match(row,probabilities):
    from doomlib.enemy_ranking import sequence_probabilities
    distribution=sequence_probabilities(dict(zip(row['question']['criteria'],probabilities)),row['enemy_sequences'])
    return max(distribution,key=distribution.get)==row['sequence_label']


def visible_first_loss(logits, rows, categories):
    """Offline auxiliary supervision over the visible subset, excluding STOP."""
    import re
    import torch
    from doomlib.enemy_ranking import STOP
    losses = []
    for scores, row in zip(logits, rows):
        if row.get('category') not in categories:
            losses.append(scores.sum() * 0)
            continue
        candidates, visible = [], []
        for index, (key, text) in enumerate(row['question']['criteria'].items()):
            if key == STOP:
                continue
            match = re.fullmatch(r'\w+; distance [0-9.]+m; bearing [+-]?[0-9]+ degrees; (visible|last seen); latest accepted target: (yes|no)\.', text)
            if not match:
                raise ValueError('Visibility supervision requires observed ranking facts')
            candidates.append(index)
            if match[1] == 'visible':
                visible.append(index)
        if not visible or len(visible) == len(candidates):
            raise ValueError('Visibility correction must contain both visible and remembered targets')
        losses.append(torch.logsumexp(scores[candidates], dim=0) - torch.logsumexp(scores[visible], dim=0))
    return torch.stack(losses).mean()
