"""Explicit category weighting for supervised training and model selection."""
import collections
import math


def parse_weights(specs):
    result={}
    for spec in specs:
        name,separator,value=spec.partition('=')
        if not separator or not name or name in result:raise ValueError('Expected unique CATEGORY=WEIGHT')
        value=float(value)
        if not math.isfinite(value) or value<=0:raise ValueError('Weights must be finite and positive')
        result[name]=value
    return result


def epoch_rows(rows,weights,rng):
    if weights:return rng.choices(rows,weights=[weights.get(r.get('category',''),1) for r in rows],k=len(rows))
    result=list(rows);rng.shuffle(result);return result


def selection_score(outcomes,category_weights,kind_weights):
    correct=collections.Counter();total=collections.Counter()
    for row,matched in outcomes:
        weight=category_weights.get(row.get('category',''),1)
        total[row['kind']]+=weight;correct[row['kind']]+=weight*bool(matched)
    return sum(correct[k]/count*kind_weights.get(k,1) for k,count in total.items())
