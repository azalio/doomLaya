"""Offline correction: compare useful health/armor and keys by the same score."""
from training.route_resupply import labels as resupply_labels
from training.build_map3_resources import candidates


def labels(packet):
    result = resupply_labels(packet)
    items = packet.get('targets', {}).get('item', {})
    selected = next((value for kind, value, _ in result if kind == 'item'), None)
    if selected is None or items[selected]['category'] != 'Key':
        return result
    ranked, _ = candidates(packet)
    if not ranked:
        return result
    chosen = ranked[0][1]
    return [(kind, chosen, 'route_' + items[chosen]['category'].lower())
            if kind == 'item' else (kind, value, category)
            for kind, value, category in result]
