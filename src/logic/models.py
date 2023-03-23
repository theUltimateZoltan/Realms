from __future__ import annotations
from random import Random
from typing import Callable, Dict, List, Union
import boto3
import yaml
import logging
import json
from itertools import chain, cycle

logger = logging.getLogger()
db_client = boto3.client('dynamodb')
repo_client = boto3.client('codecommit')
websocket_api_manager = boto3.client('apigatewaymanagementapi', endpoint_url="https://scb4tvmmu2.execute-api.us-west-2.amazonaws.com/develop/")

class Player:
    def __init__(self, connection_id: str) -> None:
        self.connection_id = connection_id
        if not self.get_attributes():
            player_attributes = {"connection_id" : {"S": self.connection_id}}
            player_attributes.update(Player.noob())
            db_client.put_item(
                TableName = "realms_state",
                Item = player_attributes
            )

    @staticmethod
    def connection_exists(connection_id: str) -> bool:
        query = db_client.get_item(
                TableName='realms_state',
                Key={"connection_id": {"S": connection_id}}
            )
        return "Item" in query.keys()

    @staticmethod
    def noob() -> dict:
        return {
            "type": {"S": "player"},
            "place": {"S": "noobville"},
            "att": {"N": "1"},
            "def": {"N": "0"},
            "dex": {"N": "1"},
            "acc": {"N": "2"},
            "hp": {"N": "6"},
            "maxhp": {"N": "6"},
            "inventory": {"M": {
                "gold": {"N": "1000"},
            }},
            "equipment": {"M": {
                
            }}
        }
    
    def get_attributes(self) -> Union[dict, None]:
        query = db_client.get_item(
                TableName='realms_state',
                Key={"connection_id": {"S": self.connection_id}}
            )
        if "Item" in query.keys():
            return query.get("Item")
        else:
            return None  # player doesn't exist
        
    def get_inventory(self):
        attributes = self.get_attributes()
        return attributes.get("inventory")["M"] if attributes else None
    
    def add_to_inventory(self, item_amounts: dict):
        inventory = self.get_inventory()
        for item, amount in item_amounts.items():
            if item in inventory.keys():
                inventory[item]["N"] = str(amount + int(inventory[item]["N"]))
            else:
                inventory[item] = {"N": str(amount)}
        db_client.update_item(
            TableName='realms_state',
            Key={"connection_id": {"S": self.connection_id}},
            UpdateExpression="SET inventory = :val",
            ExpressionAttributeValues={
                ":val": {"M": inventory}
            }
        )
        
    def location(self):
        attributes = self.get_attributes()
        return attributes.get("place")["S"] if attributes else None

    def disconnect(self) -> None:
        db_client.delete_item(
            TableName='realms_state',
            Key={"connection_id": {"S": self.connection_id}}
        )

    @staticmethod
    def get_all_players_details_in_place(place: str) -> List[dict]:
        return db_client.scan(
            TableName='realms_state',
            ConsistentRead=True,
            FilterExpression="place = :player_location",
            ExpressionAttributeValues= { ':player_location': {"S": place} }
        ).get("Items")

    def talk(self, content: str) -> None:
        players_nearby = Player.get_all_players_details_in_place(self.location())
        for player in players_nearby:
            player_conn_id = player.get("connection_id")["S"]
            logger.info(f"{ player_conn_id } attempts hearing { self.connection_id }")
            websocket_api_manager.post_to_connection(ConnectionId=player_conn_id ,Data=content)
            logger.info(f"{ player_conn_id } has heard { self.connection_id }")

    def travel(self, location: str) -> None:
        db_client.update_item(
            TableName='realms_state',
            Key={"connection_id": {"S": self.connection_id}},
            UpdateExpression="SET place = :val",
            ExpressionAttributeValues={
                ":val": {"S": location}
            }
        )
        # TODO deaggrevate enemies in previous location if aggro was on player
        logger.info(f"{ self.connection_id } has traveled to { location }")


class Encounter:
    def __init__(self, place: str, type: str) -> None:
        self.__place = place
        self.__type = type
        self.__enemies_details: dict = Realm.get_instance().get_encounter_details(self.__type).get("enemies")

    def get_enemy_instances(self) -> List[EnemyInstance]:
        return [ EnemyInstance(self, enemy, self.__place, i) for enemy, i in chain(
            zip(cycle(enemy) ,range(self.__enemies_details.get(enemy))) for enemy in self.__enemies_details) ]

    def spawn_timer_tick(self) -> None:
        for enemy in self.get_enemy_instances():
            enemy.spawn_timer_tick()

    def aggrevate_enemies(self) -> None:
        for enemy in self.get_enemy_instances():
            enemy.natural_aggrevation()

class EnemyInstance:
    enemy_instances_table: str = "realms_enemies"

    def __init__(self, encounter: Encounter, type: str, place: str, index: int) -> None:
        self.__identifier = f"{place}_{encounter}_{type}_{index}"
        self.__type = type
        self.__place = place

    def spawn_timer_tick(self) -> None:
        enemy_db_object = db_client.get_item(
                TableName=EnemyInstance.enemy_instances_table,
                Key={"enemy_instance": {"S": self.__identifier}}
            )
        if enemy_db_object:
            db_client.update_item(
                TableName=EnemyInstance.enemy_instances_table,
                Key={"enemy_instance": {"S": self.__identifier}},
                UpdateExpression="SET spawn_cooldown = spawn_cooldown - 1",
                ConditionExpression="spawn_cooldown > 0"
            )
        else:
            db_client.put_item(
                TableName=EnemyInstance.enemy_instances_table, 
                Item={"enemy_instance": {"S": self.__identifier},
                    "type": {"S": self.__type }, 
                    "place": {"S": self.__place },
                    "spawn_cooldown": {"N": "0"}
                }
            )

    def natural_aggrevation(self) -> None:
        if Realm.get_instance().get_enemy_details(self.__type).get("agressive"):
            nearby_players: List[dict] = Player.get_all_players_details_in_place(self.__place)
            victim_details: dict = Random().choice(nearby_players)  # This choice should consider way more variables (damage taken from each player, level, etc) but its fine for now
            self.aggro(Player(victim_details.get("connection_id")["S"]))

    def aggro(self, player: Player) -> None:
        db_client.update_item(
            TableName=EnemyInstance.enemy_instances_table,
            Key={"type": {"S": self.__type}, "place": {"S": self.__place}},
            UpdateExpression="SET aggro = :val",
            ExpressionAttributeValues={
                ":val": {"S": player.connection_id}
            }
        )

class Realm:
    __instance: Union[Realm, None] = None

    def __init__(self, name: str) -> None:
        self.__realm_files: dict = Realm.__load_realm_files_from_repo(name)
        self.__places: dict = yaml.load(self.__realm_files.get(name), Loader=yaml.FullLoader)[name]["places"]
        self.__npc: dict = yaml.load(self.__realm_files.get("npc"), Loader=yaml.FullLoader)
        self.__items: dict = yaml.load(self.__realm_files.get("item"), Loader=yaml.FullLoader)
        self.__enemies: dict = yaml.load(self.__realm_files.get("enemy"), Loader=yaml.FullLoader)
        self.__encounters: dict = yaml.load(self.__realm_files.get("encounter"), Loader=yaml.FullLoader)
        Realm.__instance = self

    # Note to self: implement lazy loading for yaml attributes to reduce overhead.

    @staticmethod
    def get_instance():
        assert Realm.__instance, "Realm instance has not been created."
        return Realm.__instance

    def get_places_names(self) -> List[str]:
        return [place.key() for place in self.__places]
    
    def get_place_description(self, place_name: str) -> dict:
        return self.__places.get(place_name)
    
    def get_npcs_details_in_location(self, location: str) -> dict:
        npcs_names_in_loc = self.get_place_description(location).get("npc")
        return {npc: details for npc, details in self.__npc.items() if npc in npcs_names_in_loc}

    def get_npc_details(self, npc_name: str) -> dict:
        return self.__npc.get(npc_name)
    
    def get_item_details(self, item_name: str) -> dict:
        return self.__items.get(item_name)
    
    def get_enemy_details(self, enemy_type: str) -> dict:
        return self.__enemies.get(enemy_type)
    
    def get_available_travel_locations(self, current_location) -> List[str]:
        return self.__places[current_location].get("travel")
    
    def get_encounters(self) -> List[Encounter]:
        encounters = list()
        for place in self.__places:
            encounters_in_place = place.get("encounter") if "encounter" in place.keys() else []
            encounters.extend([Encounter(place, enc) for enc in encounters_in_place])
        return encounters
    
    def get_encounter_details(self, encounter_name) -> dict:
        return self.__encounters[encounter_name]

    @staticmethod
    def __load_realm_files_from_repo(realm_name: str) -> dict:
        def __get_realm_file_by_name(filename: str) -> str:
            contentbytes = repo_client.get_file(
                repositoryName='realms',
                commitSpecifier='master',
                filePath=f'realm_data/{filename}.yaml'
            ).get("fileContent")
            with open(f"/tmp/{filename}.yaml", 'wb') as f:
                f.write(contentbytes)
            with open(f"/tmp/{filename}.yaml", 'r') as f:
                realm_yaml = f.read()
            return realm_yaml

        realm_files = dict()
        for file_name in [realm_name, "npc", "encounter", "item", "enemy"]:
            realm_files[file_name] = __get_realm_file_by_name(file_name)
        return realm_files


class NpcOptionEffectFactory:
    def __init__(self, npc_properties: dict, player: Player) -> None:
        self.__npc_properties = npc_properties
        self.__player = player
    
    def get_effect(self, npc_option: str, parameters: list) -> Callable:
        assert npc_option in self.__npc_properties.keys(), f"{npc_option} does not exist for this NPC."
        if npc_option == "talk" or npc_option == "description":
            return lambda: self.__retrieve_data(npc_option)
        elif npc_option == "shop":
            logger.info(parameters)  #DEBUG
            return lambda: self.__buy(parameters[0], parameters[1])

    def __retrieve_data(self, data_property: str) -> None:
        data_template = json.dumps(self.__npc_properties.get(data_property))
        websocket_api_manager.post_to_connection(ConnectionId=self.__player.connection_id ,Data=data_template)

    def __buy(self, item, amount) -> None:
        assert item in self.__npc_properties.get("shop").keys()
        player_gold = int(self.__player.get_inventory().get("gold")["N"])
        item_value = Realm.get_instance().get_item_details(item).get("value")
        amount = int(amount)
        logger.info(f"player {self.__player.connection_id} has {player_gold} gold and attempts to buy {amount} {item} for {item_value} each.")
        if player_gold >= item_value * amount:
            self.__player.add_to_inventory({
                "gold": (-1 * item_value * amount),
                item: amount
            })
            websocket_api_manager.post_to_connection(ConnectionId=self.__player.connection_id ,
                                                     Data={"SYS": "successfully purchased."})
        else:
            websocket_api_manager.post_to_connection(ConnectionId=self.__player.connection_id ,
                                                     Data={"SYS":"insufficient funds."})