"""Request scheduling from elapsed time and observed inventory changes."""

def inventory_signature(state,episode=0,include_ammo=False):
    from doomlib.combat import AMMO_COST
    ownership=tuple(sorted((str(slot),int(item['owned'])) for slot,item in state['inventory'].items()))
    signature=(episode,ownership,tuple(sorted(state.get('keys',()))))
    if include_ammo:
        ready=tuple(sorted(str(slot) for slot,item in state['inventory'].items()
                           if item['owned'] and item['ammo']>=AMMO_COST[int(slot)]))
        signature+=(ready,)
    return signature


def request_reason(tick,last_request,interval_ticks,signature,last_signature,inventory_events=False):
    if tick-last_request>=interval_ticks:return 'interval'
    if inventory_events and signature!=last_signature:return 'inventory_changed'
    return None
