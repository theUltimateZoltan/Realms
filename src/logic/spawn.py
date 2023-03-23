from __future__ import annotations
import logging
from models import *

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    realm = Realm("mock_realm")
    encounters: List[Encounter] = realm.get_encounters()
    for encounter in encounters:
        encounter.spawn_timer_tick()
        for enemy in encounter.get_enemy_instances():
            if 