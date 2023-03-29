from __future__ import annotations
import logging
from models import *
from random import random

logger = logging.getLogger()
logger.setLevel(logging.INFO)
Realm("mock_realm")

def lambda_handler(event, context):
    natural_aggrevation()

def natural_aggrevation():
    encounters: List[Encounter] = Realm.get_instance().get_encounters()
    for encounter in encounters:
        encounter.spawn_timer_tick()
        for enemy in encounter.get_enemy_instances():
            players_in_place = Player.get_all_players_details_in_place(encounter.get_location()):
            if len(players_in_place) > 0:
                victim = Random().choice(players_in_place)
                enemy.aggro(victim)