"""Laya choice inference without four-decimal rounding before sequence decoding."""


def predict_precise(agent,state,questions):
    import torch
    from laya.common import QTYPES,build_sequence,collate_items,render_options,temp_bucket
    items=[];internal=[]
    for name,question in questions.items():
        q=agent._to_internal(question)
        if q['t']!='choice':raise ValueError('Ranked inference requires choice questions')
        ids,markers=build_sequence(agent.tok,state,q,agent.cfg.get('max_len',512),agent.cfg.get('head_max_len',192))
        if len(markers)!=len(render_options(q)):raise ValueError('Ranking options were truncated')
        items.append(dict(ids=ids,markers=markers,qtype=QTYPES[q['t']]));internal.append((name,q))
    batch=collate_items([items],agent.tok.pad_token_id)
    with torch.no_grad(),torch.autocast(device_type=agent.device.type,dtype=agent.dtype,enabled=agent.device.type=='cuda'):
        logits,_=agent.model(*(batch[key].to(agent.device) for key in ('input_ids','attention_mask','marker_pos','marker_mask','qtype')))
    logits=logits.float().cpu().double();answers={}
    for i,(name,q) in enumerate(internal):
        keys=list(q['crit']);temperature=agent.temperature_by_options.get(temp_bucket(QTYPES['choice'],len(keys)),agent.temperature[QTYPES['choice']])
        p=(logits[i,:len(keys)]/max(1e-3,float(temperature))).softmax(-1).tolist()
        probabilities=dict(zip(keys,p));choice=max(probabilities,key=probabilities.get)
        answers[name]=dict(type='choice',choice=choice,probabilities=probabilities,confidence=probabilities[choice])
    return dict(model='laya-rl-agent',answers=answers,usage=dict(input_tokens=int(batch['attention_mask'].sum()),output_tokens=0))
