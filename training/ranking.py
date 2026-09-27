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
