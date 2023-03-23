from __future__ import annotations
import logging
import json
from models import *

REALM_CACHED = False  # change to true to have lambda cache the realm

logger = logging.getLogger()
logger.setLevel(logging.INFO)
realm = Realm("mock_realm")

def lambda_handler(event, context):
    routekey = event.get("requestContext").get("routeKey")
    conn_id = event.get("requestContext").get("connectionId")
    player = Player(conn_id)

    if not REALM_CACHED:
        Realm("mock_realm")

    if routekey == "$connect":
        logger.info(f"Player connected with id {player.connection_id}")
    elif routekey == "$disconnect":
        player.disconnect()
        logger.info(f"Player with id {player.connection_id} disconnected")
    else: 
        request = InteractionRequest(event.get("body"), player)
        request.generate_action().execute()

    return {
                "isBase64Encoded": False,
                "statusCode": 200,
                "body": json.dumps({"event": str(event), "context": str(context)})
            }


def log(text: str) -> Callable:
    return lambda: logger.info(text)

def echo(message: dict, player: Player) -> Callable:
    return lambda: websocket_api_manager.post_to_connection(ConnectionId=player.connection_id ,Data=json.dumps(message))

class InteractionActionBuilder:
    def __init__(self) -> None:
        self.__actions: List[Callable] = list()

    def then(self, action: Callable) -> InteractionActionBuilder:
        self.__actions.append(action)
        return self
    
    def execute(self) -> None:
        for action in self.__actions:
            action()

class InteractionRequest:
    def __init__(self, request_text: str, player: Player) -> None:
        self.__base_action = request_text.split("#")[0]
        self.__parameters = request_text.split("#")[1:-1]
        self.__requesting_player = player
        logger.info(f"Request received for '{self.__base_action}' with parameters {self.trailing_options(0)}")
    
    def parameter(self, index: int) -> Union[str, None]:
        return self.__parameters[index] if index < len(self.__parameters) else None
    
    def trailing_options(self, from_index: int) -> List[str]:
        return self.__parameters[from_index:]
    
    def generate_action(self) -> InteractionActionBuilder:
        action_builder = InteractionActionBuilder()
        if self.__base_action == "talk":
            action_builder.then(log(f"Player with id {self.__requesting_player.connection_id} is talking.")).then(
                lambda: self.__requesting_player.talk(self.parameter(0)))
        elif self.__base_action == "travel":
            travel_location = self.parameter(0)
            if travel_location in realm.get_available_travel_locations(self.__requesting_player.location()):
                action_builder.then(
                    lambda: self.__requesting_player.travel(travel_location)).then(
                    echo(realm.get_place_description(travel_location), self.__requesting_player))
        elif self.__base_action == "spec":
            target_id = self.parameter(0)
            if Player.connection_exists(target_id):
                action_builder.then(
                    echo(Player(target_id).get_attributes(), self.__requesting_player))
            else:
                action_builder.then(echo({"SYS": "The user requested is not currently connected."}, self.__requesting_player))
        elif self.__base_action == "browse":
            details = realm.get_place_description(loc:=self.__requesting_player.location())
            action_builder.then(
                log(f"Player {self.__requesting_player.connection_id} is browsing its location at {loc}. details: {details}")).then(
                echo(details, self.__requesting_player))
        elif self.__base_action == "npc":
            nearby_npc = realm.get_npcs_details_in_location(self.__requesting_player.location())
            target, option = self.parameter(0), self.parameter(1)
            if target in nearby_npc.keys() and not option:
                action_builder.then(
                    echo(nearby_npc.get(target), self.__requesting_player))
            elif option:
                parameters = self.trailing_options(from_index=2)
                action_builder.then(
                    log(f"{self.__requesting_player.connection_id} attempts to perform {option} on {target} with parameters {parameters}")).then(
                    NpcOptionEffectFactory(nearby_npc.get(target), self.__requesting_player).get_effect(option, parameters))
        elif self.__base_action == "hit":
            target = self.parameter(0)
            # if there is a living target in the room, hit it

        return action_builder