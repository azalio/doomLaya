"""Expose observed resource counts beside each candidate, without ranking it."""
from items import WEAPONS

AMMO_POOLS={2:('bullets','2'),3:('shells','3'),4:('bullets','2'),5:('rockets','5'),6:('cells','6'),7:('cells','6'),8:('shells','3')}


def ammo_pool(name):
    lower=name.lower()
    return ('shells','3') if 'shell' in lower else ('rockets','5') if 'rocket' in lower else ('cells','6') if 'cell' in lower else ('bullets','2')


def has_pool_weapon(inventory,slot):
    return any(inventory[str(weapon)]['owned'] for weapon,(_,pool) in AMMO_POOLS.items() if pool==slot)


def describe(item,observation):
    name=item['name'];category=item['category'];inventory=observation['inventory']
    parts=[name,f"{item['distance']:.1f}m"]
    if 'reachable' in item:parts.append('reachable' if item['reachable'] else 'unreachable')
    if category=='Health':parts.append(f"health={observation['hp']:g}")
    elif category=='Armor':parts.append(f"armor={observation['armor']:g}")
    elif category=='Ammo':
        pool,slot=ammo_pool(name)
        parts.append(f"{pool}={inventory[slot]['ammo']:g}" if has_pool_weapon(inventory,slot) else 'usable gun=no')
    elif category=='Weapon':
        slot=WEAPONS.get(name)
        if slot is not None:
            parts.append('owned' if inventory[str(slot)]['owned'] else 'unowned')
            if slot in AMMO_POOLS:
                pool,ammo_slot=AMMO_POOLS[slot]
                if has_pool_weapon(inventory,ammo_slot):parts.append(f"{pool}={inventory[ammo_slot]['ammo']:g}")
    return ' '.join(parts)


def with_resource_facts(packet):
    if 'item' in packet['questions']:
        packet['questions']['item']['criteria']={oid:describe(item,packet['observation']) for oid,item in packet['targets']['item'].items()}
    packet['item_resource_facts']=True
    return packet
